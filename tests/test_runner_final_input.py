from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.package.audit import (
    canonical_probability_input_sha256,
    evaluate_package_safety,
)
from toto_ai.runner.final_input import capture_final_input, load_final_input
from toto_ai.runner.scheduler import build_scheduler_plan

NOW = datetime(2032, 1, 2, 10, 0, tzinfo=timezone.utc)


def _payload(*, probability: float = 40.0) -> dict[str, object]:
    return {
        "data": {
            "id": 12001,
            "number": 5001,
            "status": "active",
            "ended_at": (NOW + timedelta(hours=1)).isoformat(),
            "events": [
                {
                    "id": 30000 + order,
                    "order": order,
                    "name": f"Home {order} — Away {order}",
                    "championship": "Test League",
                    "quotes": {
                        "bk_win_1": probability if order == 0 else 40.0,
                        "bk_draw": 30.0,
                        "bk_win_2": 30.0,
                        "pool_win_1": 40.0,
                        "pool_draw": 30.0,
                        "pool_win_2": 30.0,
                    },
                }
                for order in range(15)
            ],
        }
    }


def _plan(tmp_path: Path):
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir()
    (root / "data" / "aliases.json").write_text("{}")
    write_empty_schedule_evidence_ledger(root)
    return build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=NOW + timedelta(hours=1),
        bank=4980,
        output_dir=root / "out",
        project_root=root,
        db=root / "data" / "test.db",
        aliases=root / "data" / "aliases.json",
    )


def test_capture_fetches_once_and_round_trips(tmp_path):
    plan = _plan(tmp_path)

    class Client:
        calls = 0

        def drawing_info(self, drawing_id):
            assert drawing_id == 12001
            self.calls += 1
            return _payload()

    client = Client()
    path = plan.output_dir / "attempts" / "one" / "final-input.json"
    snapshot = capture_final_input(
        client=client,
        plan=plan,
        attempt_id="one",
        now=lambda: NOW,
        destination=path,
        timing_override_sha256=None,
    )

    assert client.calls == 1
    assert load_final_input(path, expected_plan=plan) == snapshot
    assert len(snapshot.probability_input_sha256) == 64


def test_capture_timestamp_is_response_completion_time(tmp_path):
    plan = _plan(tmp_path)
    request_started_at = NOW
    request_completed_at = NOW + timedelta(seconds=9)
    observed_at = request_started_at

    class Client:
        def drawing_info(self, _drawing_id):
            nonlocal observed_at
            observed_at = request_completed_at
            return _payload()

    snapshot = capture_final_input(
        client=Client(),
        plan=plan,
        attempt_id="response-complete",
        now=lambda: observed_at,
        destination=plan.output_dir / "response-complete.json",
        timing_override_sha256=None,
    )

    assert snapshot.captured_at == request_completed_at


def test_final_input_and_package_safety_share_canonical_probability_hash(
    tmp_path,
):
    plan = _plan(tmp_path)

    class Client:
        def drawing_info(self, _drawing_id):
            return _payload()

    snapshot = capture_final_input(
        client=Client(),
        plan=plan,
        attempt_id="canonical",
        now=lambda: NOW,
        destination=plan.output_dir / "canonical.json",
        timing_override_sha256=None,
    )
    probabilities = ((0.4, 0.3, 0.3),) * 15
    safety = evaluate_package_safety(
        ("1X2" * 5, "X21" * 5, "21X" * 5),
        probabilities,
    )

    assert snapshot.probability_input_sha256 == (
        canonical_probability_input_sha256(probabilities)
    )
    assert safety.probability_input_sha256 == snapshot.probability_input_sha256


def test_probability_change_changes_detail_and_probability_hash(tmp_path):
    first_plan = _plan(tmp_path / "first")
    second_plan = _plan(tmp_path / "second")

    class Client:
        def __init__(self, payload):
            self.payload = payload

        def drawing_info(self, _drawing_id):
            return self.payload

    first = capture_final_input(
        client=Client(_payload()),
        plan=first_plan,
        attempt_id="one",
        now=lambda: NOW,
        destination=first_plan.output_dir / "input.json",
        timing_override_sha256=None,
    )
    second = capture_final_input(
        client=Client(_payload(probability=41.0)),
        plan=second_plan,
        attempt_id="one",
        now=lambda: NOW,
        destination=second_plan.output_dir / "input.json",
        timing_override_sha256=None,
    )

    assert first.detail_payload_sha256 != second.detail_payload_sha256
    assert first.probability_input_sha256 != second.probability_input_sha256


def test_load_rejects_post_snapshot_tamper(tmp_path):
    plan = _plan(tmp_path)

    class Client:
        def drawing_info(self, _drawing_id):
            return _payload()

    path = plan.output_dir / "input.json"
    capture_final_input(
        client=Client(),
        plan=plan,
        attempt_id="one",
        now=lambda: NOW,
        destination=path,
        timing_override_sha256=None,
    )
    document = json.loads(path.read_text())
    tampered = copy.deepcopy(document)
    tampered["payload"]["data"]["events"][0]["quotes"]["bk_win_1"] = 99
    path.write_text(json.dumps(tampered))

    with pytest.raises(ValueError, match="snapshot hash mismatch"):
        load_final_input(path, expected_plan=plan)


def test_capture_rejects_after_deadline(tmp_path):
    plan = _plan(tmp_path)

    class Client:
        def drawing_info(self, _drawing_id):
            return _payload()

    with pytest.raises(ValueError, match="after drawing deadline"):
        capture_final_input(
            client=Client(),
            plan=plan,
            attempt_id="late",
            now=lambda: plan.ended_at + timedelta(seconds=1),
            destination=plan.output_dir / "late.json",
            timing_override_sha256=None,
        )
