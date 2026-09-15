"""Research-only finished-source admission; direct label isolation and binding."""

import copy
import json
from dataclasses import replace
from datetime import datetime

import pytest

from toto_ai.collector.lifecycle import RawArchive
from toto_ai.research import closed_market_scenario_replay as scenario


def source(tmp_path, mutate=None):
    data = {
        "data": {
            "id": 12107,
            "number": 5000,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": "2026-09-08T18:00:00Z",
            "pool_sum": 78748,
            "jackpot": 1000000,
            "events": [
                {
                    "id": 180708 + i,
                    "order": i,
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
    data["data"].update(status="finished", pool_sum=6_000_000)
    for e in data["data"]["events"]:
        e.update(result="1", score="2:0")
    if mutate:
        mutate(data)
    r = RawArchive(tmp_path / "raw").archive(
        data,
        captured_at=datetime.fromisoformat("2026-09-15T13:32:00+00:00"),
        source="totobrief-network",
        lifecycle_status="finished",
        source_endpoint="/drawing-info/12107",
    )
    return {
        "id": 12107,
        "number": 5000,
        "latest_raw_path": str(r.payload_path),
        "latest_metadata_path": str(r.metadata_path),
        "file_sha256": r.payload_sha256,
        "db_payload_sha256": r.payload_sha256,
        "latest_capture": r.captured_at,
    }


def test_finished_source_is_explicit_scenario_and_has_no_labels(tmp_path):
    doc = scenario.extract(source(tmp_path))
    assert doc["evidence_domain"] == scenario.DOMAIN
    assert doc["quote_available_at"] is None
    assert doc["captured_at"].startswith("2026-09-15")
    assert all(doc[k] is False for k in scenario.FALSE_FLAGS)
    assert not any(
        k in json.dumps(doc["market"]) for k in ('"result"', '"score"', '"payments"')
    )
    i = scenario.validate_input(doc)
    assert i.config.max_coupons == 166
    assert len(i.ev.true_probabilities) == 15


def test_result_mutation_does_not_change_input_or_seed(tmp_path):
    a = scenario.extract(source(tmp_path / "a"))

    def mutate(d):
        for e in d["data"]["events"]:
            e.update(result="2", score="0:7", result_status="settled")
        d["data"]["payments"] = {"15": 999}

    b = scenario.extract(source(tmp_path / "b", mutate))
    assert a == b


@pytest.mark.parametrize("kind", ["nan", "missing", "negative", "order", "id", "pool"])
def test_invalid_numeric_and_identity_fields_rejected(tmp_path, kind):
    def mutate(d):
        e = d["data"]["events"][1]
        if kind == "nan":
            e["quotes"]["bk_draw"] = float("nan")
        elif kind == "missing":
            del e["quotes"]["pool_draw"]
        elif kind == "negative":
            e["quotes"]["bk_draw"] = -1
        elif kind == "order":
            e["order"] = 0
        elif kind == "id":
            e["id"] = d["data"]["events"][0]["id"]
        elif kind == "pool":
            d["data"]["pool_sum"] = 78748

    with pytest.raises((ValueError, TypeError)):
        scenario.extract(source(tmp_path, mutate))


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_domain", "FROZEN_HISTORICAL_INPUT"),
        ("quote_available_at", "2026-09-07T00:00:00Z"),
        ("operator_compatible", True),
        ("fit_eligible", True),
        ("bank", 780),
    ],
)
def test_resealed_unsafe_contract_rejected(tmp_path, field, value):
    d = scenario.extract(source(tmp_path))
    d[field] = value
    d = scenario.seal({k: v for k, v in d.items() if k != "sha256"})
    with pytest.raises(ValueError):
        scenario.validate_input(d)


def test_wrong_raw_hash_rejected(tmp_path):
    ref = source(tmp_path)
    ref["file_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        scenario.extract(ref)


def test_wrong_metadata_identity_rejected(tmp_path):
    ref = source(tmp_path)
    ref["id"] += 1
    with pytest.raises(ValueError):
        scenario.extract(ref)


def test_market_changes_input_and_seed(tmp_path):
    a = scenario.validate_input(scenario.extract(source(tmp_path / "a")))
    b = scenario.validate_input(
        scenario.extract(
            source(
                tmp_path / "b",
                lambda d: d["data"]["events"][0]["quotes"].update(bk_draw=35),
            )
        )
    )
    assert a.input_sha256 != b.input_sha256 and a.seed != b.seed


def test_surface_cannot_be_swapped_between_inputs(tmp_path):
    a = scenario.validate_input(scenario.extract(source(tmp_path)))
    bound = scenario.build_surface(a)
    with pytest.raises(ValueError):
        scenario.validate_surface(replace(bound, input_sha256="0" * 64), a)
    with pytest.raises(ValueError):
        scenario.validate_surface(replace(bound, config_sha256="0" * 64), a)
    with pytest.raises(ValueError):
        scenario.validate_surface(replace(bound, surface_sha256="0" * 64), a)


def test_unfrozen_outputs_cannot_load_labels(tmp_path):
    called = []
    with pytest.raises(ValueError):
        scenario.score_frozen(tmp_path, lambda: called.append(True))
    assert called == []


def test_scoring_identifies_reordered_control_as_same_set(tmp_path, monkeypatch):
    doc = scenario.extract(source(tmp_path / "source"))
    out = tmp_path / "frozen"
    out.mkdir()
    coupons = []
    for n in range(166):
        chars = []
        for _ in range(15):
            chars.append("1X2"[n % 3])
            n //= 3
        coupons.append("".join(chars))
    hashes = {}
    for arm, values in (("quality-v2", coupons), ("quality-v3", coupons[::-1])):
        hashes[arm] = scenario._write_exclusive(
            out / (arm + ".json"),
            {
                "evidence_domain": scenario.DOMAIN,
                **scenario.FLAGS,
                "input_sha256": doc["sha256"],
                "bank": 4980,
                "stake": 30,
                "arm": arm,
                "coupons": values,
            },
        )
    ih = scenario._write_exclusive(out / "input.json", doc)
    scenario._write_exclusive(
        out / "frozen.json",
        scenario.seal(
            {
                "evidence_domain": scenario.DOMAIN,
                **scenario.FLAGS,
                "frozen_before_labels": True,
                "drawing": 5000,
                "input_sha256": doc["sha256"],
                "input_file_sha256": ih,
                "packages": hashes,
                "error": None,
            }
        ),
    )
    monkeypatch.setattr(
        scenario, "exact_category_probabilities", lambda *args: (0.1, 0.02, 0.001)
    )
    result = scenario.score_frozen(
        out, lambda: {"drawing": 5000, "drawing_id": 12107, "actual": "1" * 15}
    )
    row = next(r for r in result["rows"] if r["arm"] == "quality-v3")
    assert row["same_as_control"] is True
    assert row["same_order_as_control"] is False
    assert scenario.file_hash(out / "quality-v3.json") == hashes["quality-v3"]


def test_reporting_revision_preserves_generation_code_guard(tmp_path):
    code = scenario.code_hashes()
    code["research/closed_market_scenario_replay.py"] = "0" * 64
    m = scenario.seal(
        {
            "evidence_domain": scenario.DOMAIN,
            **scenario.FLAGS,
            "code": code,
            "config": scenario.asdict(scenario._config()),
            "options": scenario.OPTIONS,
            "seed_protocol": scenario.SEED,
            "roster": [{"drawing": n} for n in range(4999, 5007)],
        }
    )
    p = tmp_path / "manifest.json"
    scenario._write_exclusive(p, m)
    with pytest.raises(ValueError):
        scenario.load_manifest(p)
    assert scenario.load_manifest(p, for_scoring=True)["code"] == code
    code["ev/ternary.py"] = "0" * 64
    p.write_text(
        json.dumps(scenario.seal({k: v for k, v in m.items() if k != "sha256"}))
    )
    with pytest.raises(ValueError):
        scenario.load_manifest(p, for_scoring=True)


def test_unknown_extra_field_rejected(tmp_path):
    d = copy.deepcopy(scenario.extract(source(tmp_path)))
    d["market"]["events"][0]["result"] = "1"
    d = scenario.seal({k: v for k, v in d.items() if k != "sha256"})
    with pytest.raises(ValueError):
        scenario.validate_input(d)


def test_backdated_capture_rejected(tmp_path):
    d = scenario.extract(source(tmp_path))
    d["captured_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(ValueError, match="backdated"):
        scenario.validate_input(
            scenario.seal({k: v for k, v in d.items() if k != "sha256"})
        )


@pytest.mark.parametrize("tamper", ["coupon", "reorder", "input", "budget"])
def test_frozen_tampering_rejected_before_label_callback(tmp_path, tamper):
    doc = scenario.extract(source(tmp_path / "source"))
    out = tmp_path / "out"
    out.mkdir()
    coupons = []
    for n in range(166):
        digits = []
        for _ in range(15):
            digits.append("1X2"[n % 3])
            n //= 3
        coupons.append("".join(digits))
    package = {
        "evidence_domain": scenario.DOMAIN,
        **scenario.FLAGS,
        "input_sha256": doc["sha256"],
        "bank": 4980,
        "stake": 30,
        "arm": "quality-v2",
        "coupons": coupons,
    }
    ih = scenario._write_exclusive(out / "input.json", doc)
    ph = scenario._write_exclusive(out / "quality-v2.json", package)
    frozen = scenario.seal(
        {
            "evidence_domain": scenario.DOMAIN,
            **scenario.FLAGS,
            "frozen_before_labels": True,
            "drawing": 5000,
            "input_sha256": doc["sha256"],
            "input_file_sha256": ih,
            "packages": {"quality-v2": ph},
        }
    )
    scenario._write_exclusive(out / "frozen.json", frozen)
    scenario.verify_frozen(out)
    if tamper == "coupon":
        package["coupons"][0] = "2" * 15
    if tamper == "reorder":
        package["coupons"].reverse()
    if tamper == "budget":
        package["bank"] = 780
    if tamper == "input":
        package["input_sha256"] = "0" * 64
    (out / "quality-v2.json").write_text(json.dumps(package))
    called = []
    with pytest.raises(ValueError):
        scenario.score_frozen(out, lambda: called.append(True))
    assert called == []
