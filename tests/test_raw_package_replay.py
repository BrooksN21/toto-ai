"""The RAW adapter must not turn absent operational evidence into a model run."""

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from toto_ai.collector.lifecycle import RawArchive
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import validate_selection_provenance
from toto_ai.optimizer.strategy_historical_benchmark import historical_ev_config
from toto_ai.research.raw_package_replay import (
    DOMAIN,
    admit_generation,
    load_replay_input,
    prepare_report,
)


def payload():
    return {
        "data": {
            "id": 12107,
            "number": 5000,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": "2026-09-08T18:00:00.000Z",
            "pool_sum": 78748,
            "jackpot": 1000000,
            "payments": None,
            "events": [
                {
                    "id": 180708 + i,
                    "order": i,
                    "name": f"Home {i} — Away {i}",
                    "championship": "Football league",
                    "result": "",
                    "score": "",
                    "start_at": None,
                    "quotes": {
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                        "pool_win_1": 50,
                        "pool_draw": 25,
                        "pool_win_2": 25,
                    },
                }
                for i in range(15)
            ],
        }
    }


def fixture_manifest(tmp_path, value=None, *, captured=None):
    record = RawArchive(tmp_path / "raw").archive(
        payload() if value is None else value,
        captured_at=datetime.fromisoformat(
            captured or "2026-09-07T16:32:08.195493+00:00"
        ),
        source="network",
        lifecycle_status="active",
        source_endpoint="/drawing-info/12107",
    )
    manifest = {
        "schema_version": 1,
        "evidence_domain": DOMAIN,
        "drawing_id": 12107,
        "drawing_number": 5000,
        "requested_bank": 4980,
        "stake": 30,
        "raw": {
            "payload_path": str(record.payload_path),
            "metadata_path": str(record.metadata_path),
            "snapshot_sha256": record.snapshot_sha256,
            "payload_sha256": record.payload_sha256,
            "metadata_sha256": record.metadata_sha256,
            "captured_at": record.captured_at,
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, record


def test_native_raw_input_has_correct_moscow_deadline_and_native_pool_cap(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    replay = load_replay_input(path)
    assert replay.frozen.bank == 780
    assert replay.frozen.max_coupons == 26
    assert replay.frozen.stake == 30
    assert replay.frozen.ended_at.startswith("2026-09-08T15:00:00")
    assert replay.requested_bank == 4980
    assert len(replay.frozen.events) == 15
    assert (
        replay.seed_material_sha256
        == hashlib.sha256(replay.probability_input_sha256.encode("ascii")).hexdigest()
    )
    assert replay.config.mode == "playable"
    assert replay.config.package_safety_enabled is True
    assert replay.config.package_provenance_required is True


@pytest.mark.parametrize("field", ["result", "score", "result_status"])
def test_rejects_target_outcomes_even_from_a_validly_hashed_archive(tmp_path, field):
    value = payload()
    value["data"]["events"][0][field] = "1"
    path, _ = fixture_manifest(tmp_path, value)
    with pytest.raises(ValueError, match="post-result"):
        load_replay_input(path)


@pytest.mark.parametrize("field", ["result", "score"])
def test_missing_outcome_sentinel_is_not_treated_as_empty(tmp_path, field):
    value = payload()
    del value["data"]["events"][0][field]
    path, _ = fixture_manifest(tmp_path, value)
    with pytest.raises(ValueError, match="missing.*sentinel"):
        load_replay_input(path)


@pytest.mark.parametrize("field", ["bk_draw", "pool_draw"])
def test_missing_probabilities_are_not_imputed(tmp_path, field):
    value = payload()
    del value["data"]["events"][0]["quotes"][field]
    path, _ = fixture_manifest(tmp_path, value)
    with pytest.raises(ValueError):
        load_replay_input(path)


@pytest.mark.parametrize("field", ["jackpot", "pool_sum", "ended_at"])
def test_missing_financial_and_time_fields_fail_closed(tmp_path, field):
    value = payload()
    del value["data"][field]
    path, _ = fixture_manifest(tmp_path, value)
    with pytest.raises(ValueError):
        load_replay_input(path)


def test_target_payments_are_rejected(tmp_path):
    value = payload()
    value["data"]["payments"] = {"13": 100}
    path, _ = fixture_manifest(tmp_path, value)
    with pytest.raises(ValueError, match="post-result"):
        load_replay_input(path)


def test_late_capture_rejected_without_reinterpreting_moscow_z(tmp_path):
    path, _ = fixture_manifest(tmp_path, captured="2026-09-08T14:50:00+00:00")
    with pytest.raises(ValueError, match="T-10"):
        load_replay_input(path)


@pytest.mark.parametrize("which", ["payload_path", "metadata_path"])
def test_tampered_bytes_rejected(tmp_path, which):
    path, record = fixture_manifest(tmp_path)
    target = getattr(record, which)
    obj = json.loads(target.read_text())
    if which == "payload_path":
        obj["data"]["jackpot"] += 1
    else:
        obj["captured_at"] = "2026-09-01T00:00:00+00:00"
    target.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="hash|capture binding"):
        load_replay_input(path)


def test_research_input_is_immutable_and_matrices_are_normalized(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    replay = load_replay_input(path)
    with pytest.raises(FrozenInstanceError):
        replay.operator_compatible = True
    with pytest.raises(FrozenInstanceError):
        replay.frozen.bank = 4980
    for event in replay.frozen.events:
        assert sum(event.bk_probabilities) == pytest.approx(1)
        assert sum(event.crowd_probabilities) == pytest.approx(1)


def test_foreign_identity_and_unknown_manifest_fields_fail(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    obj = json.loads(path.read_text())
    obj["drawing_number"] = 5001
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="identity"):
        load_replay_input(path)
    obj["actual_result"] = "1" * 15
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="manifest fields"):
        load_replay_input(path)


def test_generators_receive_no_unknown_payload_fields(tmp_path):
    value = payload()
    value["data"]["analysis_after_match"] = "MUST_NOT_ESCAPE"
    path, _ = fixture_manifest(tmp_path, value)
    replay = load_replay_input(path)
    assert "MUST_NOT_ESCAPE" not in repr(replay)
    assert not hasattr(replay, "payload")


def test_native_quality_v2_blocks_missing_provenance_without_running_ev(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    replay = load_replay_input(path)
    native = validate_selection_provenance(
        None,
        replay.frozen.bk_probability_matrix,
        config=replay.config,
        required=True,
    )
    assert native[1] == ("selection_provenance_missing",)
    result = admit_generation(replay)
    assert result["status"] == "BLOCKED_NATIVE_QUALITY_V2_PROVENANCE"
    assert result["packages_generated"] == 0
    assert result["native_reasons"] == list(native[1])
    assert result["models"]["quality-v2"]["status"] == "NOT_RUN"
    assert result["models"]["sports-shadow"]["status"] == "SKIPPED_NO_SPORTS"
    assert result["models"]["Sports-v3"]["status"] == "SKIPPED_NO_SPORTS"
    assert result["roi"] is None


def test_legacy_historical_helper_is_not_an_equivalent_quality_v2_engine():
    config = EVConfig(bank=780, mode="playable", package_safety_enabled=True)
    old = historical_ev_config(config, bank=780, stake=30)
    assert old.mode == "research"  # It takes EV top-N, not safety-aware qv2.
    assert old.package_provenance_required is False


def test_output_is_exclusive_hash_bound_and_has_no_wagering_file(tmp_path):
    manifest, _ = fixture_manifest(tmp_path)
    first = tmp_path / "a"
    second = tmp_path / "b"
    report = prepare_report(manifest, first)
    again = prepare_report(manifest, second)
    assert report == again
    sealed = first / "research-input.json"
    assert (
        hashlib.sha256(sealed.read_bytes()).hexdigest() == report["input_file_sha256"]
    )
    assert report["operator_compatible"] is False
    assert report["automatic_wagering"] is False
    assert {p.name for p in first.iterdir()} == {
        "research-input.json",
        "generation-blocked.json",
    }
    with pytest.raises(FileExistsError):
        prepare_report(manifest, first)


def test_symlink_archive_rejected(tmp_path):
    path, record = fixture_manifest(tmp_path)
    alias = record.payload_path.with_name("alias.json")
    alias.symlink_to(record.payload_path)
    obj = json.loads(path.read_text())
    obj["raw"]["payload_path"] = str(alias)
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError):
        load_replay_input(path)
