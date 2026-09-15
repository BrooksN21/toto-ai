"""Production-shaped post-draw/replay bindings, without ignored report fixtures."""

import hashlib
import json
from pathlib import Path

import pytest

from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.finished_draw import (
    PostDrawState,
    _write_state,
    load_post_draw_plan,
    prepare_post_draw_scheduler_artifacts,
)
from toto_ai.operations.retrospective_integrity import validate_retrospective_primary


@pytest.fixture
def bound(tmp_path):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=12096,
                number=4996,
                name="baltbet-main",
                ended_at="2026-09-04T16:30:00+00:00",
            )
        )
    coupons = ["1" * 15, "X" * 15, "2" * 15]
    source = tmp_path / "source-package.csv"
    source.write_text(
        "rank,coupon,gross_ev\n"
        + "".join(f"{i},{coupon},1.2\n" for i, coupon in enumerate(coupons, 1))
    )
    baseline = tmp_path / "package.csv"
    baseline.write_bytes(source.read_bytes())
    state_path = tmp_path / "state.json"
    path, _, _ = prepare_post_draw_scheduler_artifacts(
        drawing_id=12096,
        drawing_number=None,
        ended_at="2026-09-04T16:30:00+00:00",
        package_file=source,
        paper_result_file=None,
        stake=30,
        db=db,
        state_file=state_path,
        output_dir=tmp_path / "post-draw",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=6,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )
    plan = load_post_draw_plan(path)
    _write_state(
        state_path,
        PostDrawState(
            schema_version=2,
            status="complete",
            drawing_id=12096,
            drawing_number=4996,
            attempts=1,
            max_attempts=6,
            updated_at="2026-09-05T09:03:38+00:00",
            package_sha256=plan["package_binding"]["package_sha256"],
            result_snapshot_sha256="a" * 64,
            settlement_sha256="b" * 64,
            reason="SETTLEMENT_COMPLETE",
        ),
    )
    return dict(
        state_path=state_path,
        post_draw_plan_path=path,
        expected_plan_sha256=plan["plan_sha256"],
        drawing_id=12096,
        drawing_number=4996,
        baseline_package=baseline,
        baseline_file_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        stake=30,
        coupon_count=3,
        cost=90,
    )


def resign(path, hash_key, **changes):
    document = json.loads(path.read_text())
    document.update(changes)
    document.pop(hash_key)
    document[hash_key] = hashlib.sha256(
        json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    path.write_text(json.dumps(document))


def test_real_producer_distinct_hash_namespaces(bound):
    state = validate_retrospective_primary(**bound)
    # CSV byte hash is NOT the canonical ordered-coupon hash.
    assert state["package_sha256"] != bound["baseline_file_sha256"]
    assert (
        state["package_sha256"]
        == hashlib.sha256(
            ("1" * 15 + "," + "X" * 15 + "," + "2" * 15).encode()
        ).hexdigest()
    )
    assert state["status"] == "complete"


def test_pending_and_missing_primary_are_not_completion(bound):
    resign(bound["state_path"], "state_sha256", status="pending", package_sha256=None)
    assert validate_retrospective_primary(**bound)["status"] == "pending"
    bound["state_path"].unlink()
    assert validate_retrospective_primary(**bound) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_sha256", "0" * 64),
        ("package_sha256", "csv_hash"),
        ("drawing_id", 12097),
        ("drawing_number", 4997),
        ("schema_version", 999),
    ],
)
def test_resigned_foreign_or_wrong_namespace_state_rejected(bound, field, value):
    if value == "csv_hash":
        value = bound["baseline_file_sha256"]
    resign(bound["state_path"], "state_sha256", **{field: value})
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)


def test_unresigned_state_corruption_rejected(bound):
    bound["state_path"].write_text(
        bound["state_path"].read_text().replace("complete", "pending")
    )
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)


def test_source_corruption_rejected(bound):
    plan = json.loads(bound["post_draw_plan_path"].read_text())
    Path(plan["package_binding"]["source_path"]).write_text("1" * 15 + "\n")
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)


def test_baseline_corruption_even_with_rebound_byte_hash_rejected(bound):
    bound["baseline_package"].write_text("2" * 15 + "\n")
    bound["baseline_file_sha256"] = hashlib.sha256(
        bound["baseline_package"].read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)


def test_state_path_substitution_rejected(bound, tmp_path):
    other = tmp_path / "foreign-state.json"
    other.write_bytes(bound["state_path"].read_bytes())
    bound["state_path"] = other
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stake", 60),
        ("coupon_count", 4),
        ("cost", 120),
        ("expected_plan_sha256", "0" * 64),
    ],
)
def test_expected_plan_or_cost_mismatch_rejected(bound, field, value):
    bound[field] = value
    with pytest.raises(ValueError):
        validate_retrospective_primary(**bound)
