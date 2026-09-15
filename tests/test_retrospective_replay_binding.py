"""Replay reuse contract: resigned stale inputs and newest-result drift fail closed."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from toto_ai.db.models import Drawing, DrawingResultSnapshot
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.finished_draw import sync_finished_drawing
from toto_ai.operations.retrospective_replay_binding import (
    load_bound_result,
    validate_replay_contract,
)


def sign(report):
    report.pop("report_sha256", None)
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return report


@pytest.fixture
def bound(tmp_path):
    db = tmp_path / "results.db"
    factory = get_session_factory(init_db(db))
    deadline = "2026-09-04T16:30:00+00:00"
    with factory.begin() as session:
        session.add(
            Drawing(id=12096, number=4996, name="baltbet-main", ended_at=deadline)
        )
    hashes = []
    for actual in ("1" * 15, "2" * 15):
        payload = {
            "data": {
                "id": 12096,
                "number": 4996,
                "status": "finished",
                "ended_at": deadline,
                "events": [
                    {"id": 20000 + i, "order": i, "result": x, "score": "1:0"}
                    for i, x in enumerate(actual)
                ],
            }
        }
        client = SimpleNamespace(drawing_info=lambda _, payload=payload: payload)
        result = sync_finished_drawing(factory, client, drawing_id=12096)
        hashes.append(result.snapshot_sha256)
    result = load_bound_result(
        db, snapshot_sha256=hashes[0], drawing_id=12096, drawing_number=4996
    )
    coupons = ("1" * 15, "X" * 15, "2" * 15)
    inputs = {
        k: hashlib.sha256(k.encode()).hexdigest()
        for k in (
            "final_input_sha256",
            "probability_input_sha256",
            "sports_artifact_sha256",
            "sports_probability_input_sha256",
            "scheduler_plan_sha256",
        )
    }
    contract = dict(
        drawing_id=12096,
        drawing_number=4996,
        plan_id="frozen-plan",
        expected_input_hashes=inputs,
        result=result,
        bank=90,
        stake=30,
        baseline_coupons=coupons,
    )
    package_hash = hashlib.sha256(",".join(coupons).encode()).hexdigest()
    report = dict(
        schema_version=2,
        drawing_id=12096,
        drawing_number=4996,
        plan_id="frozen-plan",
        inputs=inputs.copy(),
        actual="1" * 15,
        result_snapshot_sha256=hashes[0],
        bank=90,
        effective_budget=90,
        stake=30,
        equal_coupon_count=3,
        equal_cost=90,
        quality_v2_reproduced_exactly=True,
        automatic_wagering=False,
        operator_compatible=False,
        scheduler_state_mutated=False,
        profitability_proven=False,
        strategies={
            name: dict(coupon_count=3, cost=90, package_sha256=package_hash)
            for name in ("quality-v2", "sports-v2", "quality-v3", "robust")
        },
    )
    return db, factory, hashes, contract, sign(report)


def test_exact_old_snapshot_not_newest_and_valid_reuse(bound):
    _, _, _, contract, report = bound
    assert contract["result"].actual == "1" * 15
    assert validate_replay_contract(report, **contract) is report


@pytest.mark.parametrize(
    "field",
    [
        "final_input_sha256",
        "probability_input_sha256",
        "sports_artifact_sha256",
        "sports_probability_input_sha256",
        "scheduler_plan_sha256",
    ],
)
def test_resigned_same_plan_wrong_input_rejected(bound, field):
    *_, contract, report = bound
    report["inputs"][field] = "0" * 64
    with pytest.raises(ValueError, match="input"):
        validate_replay_contract(sign(report), **contract)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bank", 120),
        ("stake", 60),
        ("equal_coupon_count", 4),
        ("equal_cost", 120),
        ("effective_budget", 120),
        ("actual", "2" * 15),
        ("result_snapshot_sha256", "0" * 64),
        ("result_snapshot_sha256", None),
        ("drawing_id", 12097),
    ],
)
def test_resigned_budget_or_result_substitution_rejected(bound, field, value):
    *_, contract, report = bound
    report[field] = value
    with pytest.raises(ValueError):
        validate_replay_contract(sign(report), **contract)


@pytest.mark.parametrize(
    "strategy,field,value",
    [
        ("quality-v2", "package_sha256", "0" * 64),
        ("sports-v2", "coupon_count", 4),
        ("quality-v3", "cost", 120),
        ("robust", "coupon_count", 1),
    ],
)
def test_each_strategy_equal_budget_and_control_hash(bound, strategy, field, value):
    *_, contract, report = bound
    report["strategies"][strategy][field] = value
    with pytest.raises(ValueError):
        validate_replay_contract(sign(report), **contract)


def test_old_minimal_smoke_report_is_rejected(bound):
    *_, contract, report = bound
    for key in ("inputs", "bank", "result_snapshot_sha256"):
        report.pop(key)
    with pytest.raises(ValueError):
        validate_replay_contract(sign(report), **contract)


def test_unresigned_corruption_rejected(bound):
    *_, contract, report = bound
    report["actual"] = "X" * 15
    with pytest.raises(ValueError, match="self-hash"):
        validate_replay_contract(report, **contract)


def test_wrong_drawing_missing_or_corrupt_snapshot_rejected(bound):
    db, factory, hashes, _, _ = bound
    for sha, drawing in [(hashes[0], 4997), ("0" * 64, 4996)]:
        with pytest.raises(ValueError):
            load_bound_result(
                db, snapshot_sha256=sha, drawing_id=12096, drawing_number=drawing
            )
    with factory.begin() as session:
        session.execute(
            update(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.snapshot_sha256 == hashes[0])
            .values(actual="X" * 15)
        )
    with pytest.raises(ValueError):
        load_bound_result(
            db, snapshot_sha256=hashes[0], drawing_id=12096, drawing_number=4996
        )


def test_explicit_legacy_binding_does_not_rewrite_archive_and_rejects_stale(bound):
    *_, contract, report = bound
    report.pop("result_snapshot_sha256")
    sign(report)
    original = json.dumps(report)
    binding = dict(
        report_sha256=report["report_sha256"],
        result_snapshot_sha256=contract["result"].snapshot_sha256,
        actual=contract["result"].actual,
    )
    validate_replay_contract(report, **contract, legacy_result_binding=binding)
    assert json.dumps(report) == original
    report["bank"] = 120
    sign(report)
    with pytest.raises(ValueError, match="legacy"):
        validate_replay_contract(report, **contract, legacy_result_binding=binding)
