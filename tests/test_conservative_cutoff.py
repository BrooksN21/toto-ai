from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai import cli
from toto_ai.runner.conservative_cutoff import (
    conservative_cutoff_evidence_sha256,
    derive_conservative_cutoff,
    load_conservative_cutoff_evidence,
    write_conservative_cutoff_evidence,
)
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningPreparedDrawing,
)
from toto_ai.runner.scheduler import (
    build_scheduler_plan,
    load_scheduler_plan,
    prepare_scheduler_artifacts,
)

UTC = timezone.utc


def _write_report(
    path: Path,
    *,
    starts_at: str = "2026-08-26T15:45:00Z",
    drawing_id: int = 12068,
    drawing_number: int = 4987,
    status: str = "timing_conflict",
) -> Path:
    record = {
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "event_order": 10,
        "status": status,
        "source_provider": "goal-api-v1",
        "source_role": "independent",
        "ledger_eligible": False,
        "starts_at": starts_at,
    }
    payload = {
        "schema_version": 2,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "records": [record],
    }
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def test_cutoff_can_only_tighten_totobrief_ended_at(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "source.json")

    evidence = derive_conservative_cutoff(
        report,
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )

    assert evidence.earliest_kickoff == datetime(2026, 8, 26, 15, 45, tzinfo=UTC)
    assert evidence.operational_cutoff == evidence.earliest_kickoff
    assert evidence.status == "tightened"
    assert evidence.event_orders == (10,)


def test_later_fixture_never_extends_totobrief_ended_at(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "source.json", starts_at="2026-08-26T20:00:00Z")

    evidence = derive_conservative_cutoff(
        report,
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )

    assert evidence.operational_cutoff == datetime(2026, 8, 26, 18, 45, tzinfo=UTC)
    assert evidence.status == "unchanged"


def test_cutoff_evidence_round_trip_is_bound_to_source_bytes(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "source.json")
    evidence = derive_conservative_cutoff(
        report,
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )
    evidence_path = write_conservative_cutoff_evidence(
        evidence, tmp_path / "cutoff.json"
    )

    loaded = load_conservative_cutoff_evidence(
        evidence_path,
        project_root=tmp_path,
        expected_drawing_id=12068,
        expected_drawing_number=4987,
        expected_source_ended_at=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
    )

    assert loaded.operational_cutoff == evidence.operational_cutoff
    assert loaded.source_report_path != report
    assert loaded.source_report_path.parent.name == "cutoff-source-snapshots"
    assert (
        conservative_cutoff_evidence_sha256(loaded)
        == hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    )

    report.write_text(report.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert load_conservative_cutoff_evidence(
        evidence_path,
        project_root=tmp_path,
        expected_drawing_id=12068,
        expected_drawing_number=4987,
        expected_source_ended_at=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
    ).operational_cutoff == evidence.operational_cutoff

    loaded.source_report_path.write_text(
        loaded.source_report_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="content hash mismatch"):
        load_conservative_cutoff_evidence(
            evidence_path,
            project_root=tmp_path,
            expected_drawing_id=12068,
            expected_drawing_number=4987,
            expected_source_ended_at=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        )


def test_cutoff_rejects_drawing_identity_drift(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "source.json")

    with pytest.raises(ValueError, match="drawing number mismatch"):
        derive_conservative_cutoff(
            report,
            source_ended_at="2026-08-26T18:45:00Z",
            expected_drawing_id=12068,
            expected_drawing_number=4988,
        )


def test_cutoff_rejects_non_independent_candidate_boundary(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "source.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["records"][0]["ledger_eligible"] = True
    payload.pop("report_sha256")
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="candidate-only boundary"):
        derive_conservative_cutoff(
            report,
            source_ended_at="2026-08-26T18:45:00Z",
            expected_drawing_id=12068,
            expected_drawing_number=4987,
        )


def test_scheduler_keeps_identity_deadline_but_uses_tighter_cutoff(
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    report = _write_report(tmp_path / "source.json")
    evidence = derive_conservative_cutoff(
        report,
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )
    evidence_path = write_conservative_cutoff_evidence(
        evidence, tmp_path / "cutoff.json"
    )

    plan = build_scheduler_plan(
        drawing=4987,
        drawing_id=12068,
        ended_at="2026-08-26T18:45:00Z",
        operational_cutoff=evidence.operational_cutoff,
        cutoff_evidence=evidence_path,
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    loaded = load_scheduler_plan(artifacts.plan_path)

    assert loaded.ended_at == datetime(2026, 8, 26, 18, 45, tzinfo=UTC)
    assert loaded.operational_cutoff == datetime(2026, 8, 26, 15, 45, tzinfo=UTC)
    assert loaded.publish_deadline == datetime(2026, 8, 26, 15, 35, tzinfo=UTC)
    assert loaded.deadlines["ended_at"] != loaded.deadlines["operational_cutoff"]


def test_scheduler_rejects_unproven_earlier_cutoff(tmp_path: Path) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)

    with pytest.raises(ValueError, match="requires cutoff evidence"):
        build_scheduler_plan(
            drawing=4987,
            drawing_id=12068,
            ended_at="2026-08-26T18:45:00Z",
            operational_cutoff="2026-08-26T15:45:00Z",
            bank=4980,
            output_dir=tmp_path / "scheduler",
            project_root=tmp_path,
            db=tmp_path / "toto.db",
            aliases=tmp_path / "aliases.json",
        )


def test_scheduler_rejects_cutoff_after_totobrief_ended_at(tmp_path: Path) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)

    with pytest.raises(ValueError, match="cannot extend"):
        build_scheduler_plan(
            drawing=4987,
            drawing_id=12068,
            ended_at="2026-08-26T18:45:00Z",
            operational_cutoff="2026-08-26T19:00:00Z",
            bank=4980,
            output_dir=tmp_path / "scheduler",
            project_root=tmp_path,
            db=tmp_path / "toto.db",
            aliases=tmp_path / "aliases.json",
        )


def test_morning_preparation_reuses_exact_persisted_cutoff(tmp_path: Path) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    config = MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "state",
        scheduler_root=tmp_path / "scheduler",
        env_file=tmp_path / ".env",
        bank=4980,
    )
    prepared = MorningPreparedDrawing(
        drawing_id=12068,
        drawing_number=4987,
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        drawing_fingerprint="a" * 64,
        detail_sha256="b" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="playable",
        span_days=1,
    )
    collector_dir = cli._morning_cutoff_directory(config, prepared)
    _write_report(collector_dir / "schedule-source-candidates.json")

    attached = cli._attach_persisted_conservative_cutoff(config, prepared)

    assert attached.operational_cutoff == datetime(2026, 8, 26, 15, 45, tzinfo=UTC)
    assert attached.cutoff_evidence == collector_dir / "conservative-cutoff.json"
    assert attached.cutoff_evidence_sha256 is not None


def test_morning_preparation_keeps_totobrief_deadline_without_cutoff_provider(
    tmp_path: Path,
) -> None:
    """Independent candidates from other providers must not abort preparation."""
    write_empty_schedule_evidence_ledger(tmp_path)
    config = MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "state",
        scheduler_root=tmp_path / "scheduler",
        env_file=tmp_path / ".env",
        bank=4980,
    )
    prepared = MorningPreparedDrawing(
        drawing_id=12081,
        drawing_number=4991,
        deadline=datetime(2026, 8, 30, 16, 0, tzinfo=UTC),
        drawing_fingerprint="a" * 64,
        detail_sha256="b" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="playable",
        span_days=1,
    )
    collector_dir = cli._morning_cutoff_directory(config, prepared)
    report = _write_report(
        collector_dir / "schedule-source-candidates.json",
        drawing_id=12081,
        drawing_number=4991,
        status="independent_candidate",
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["records"][0]["source_provider"] = "sofascore-search-v1"
    payload.pop("report_sha256")
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    report.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    attached = cli._attach_persisted_conservative_cutoff(config, prepared)

    assert attached == prepared
    assert not (collector_dir / "conservative-cutoff.json").exists()


def test_morning_retry_preserves_cutoff_when_latest_report_has_no_candidates(
    tmp_path: Path,
) -> None:
    """An unresolved-only retry cannot erase an earlier verified cutoff."""
    write_empty_schedule_evidence_ledger(tmp_path)
    config = MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "state",
        scheduler_root=tmp_path / "scheduler",
        env_file=tmp_path / ".env",
        bank=4980,
    )
    prepared = MorningPreparedDrawing(
        drawing_id=12068,
        drawing_number=4987,
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        drawing_fingerprint="a" * 64,
        detail_sha256="b" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
    )
    collector_dir = cli._morning_cutoff_directory(config, prepared)
    report = collector_dir / "schedule-source-candidates.json"
    _write_report(report)
    first = cli._attach_persisted_conservative_cutoff(config, prepared)

    _write_report(report, status="not_found")
    second = cli._attach_persisted_conservative_cutoff(config, prepared)

    assert second.operational_cutoff == first.operational_cutoff
    assert second.cutoff_evidence == first.cutoff_evidence
    assert second.cutoff_evidence_sha256 == first.cutoff_evidence_sha256


def test_persisted_cutoff_can_tighten_again_but_never_relax(tmp_path: Path) -> None:
    output = tmp_path / "cutoff.json"
    first = derive_conservative_cutoff(
        _write_report(tmp_path / "first.json", starts_at="2026-08-26T15:45:00Z"),
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )
    write_conservative_cutoff_evidence(first, output)
    later = derive_conservative_cutoff(
        _write_report(tmp_path / "later.json", starts_at="2026-08-26T16:00:00Z"),
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )

    write_conservative_cutoff_evidence(later, output)
    preserved = load_conservative_cutoff_evidence(
        output,
        project_root=tmp_path,
        expected_drawing_id=12068,
        expected_drawing_number=4987,
        expected_source_ended_at=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
    )
    assert preserved.operational_cutoff == datetime(
        2026, 8, 26, 15, 45, tzinfo=UTC
    )

    earlier = derive_conservative_cutoff(
        _write_report(tmp_path / "earlier.json", starts_at="2026-08-26T15:30:00Z"),
        source_ended_at="2026-08-26T18:45:00Z",
        expected_drawing_id=12068,
        expected_drawing_number=4987,
    )
    write_conservative_cutoff_evidence(earlier, output)

    assert json.loads(output.read_text(encoding="utf-8"))["operational_cutoff"] == (
        "2026-08-26T15:30:00Z"
    )
