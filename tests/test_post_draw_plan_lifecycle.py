import json
from datetime import datetime, timezone

from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.finished_draw import (
    load_post_draw_plan,
    prepare_post_draw_scheduler_artifacts,
    run_post_draw_plan,
)

ACTUAL = "1X22X222211X1XX"


class Client:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = 0

    def drawing_info(self, drawing_id):
        self.calls += 1
        payload = next(self.payloads)
        if isinstance(payload, BaseException):
            raise payload
        return payload


def _payload(actual=ACTUAL, *, status="finished"):
    return {
        "data": {
            "id": 12001,
            "number": 5001,
            "name": "baltbet-main",
            "status": status,
            "ended_at": "2026-08-13T18:00:00+00:00",
            "pool_sum": 1_000_000,
            "jackpot": 500_000,
            "payments": None,
            "events": [
                {
                    "id": 30_000 + order,
                    "order": order,
                    "result": result,
                    "score": f"{order}:0",
                }
                for order, result in enumerate(actual)
            ],
        }
    }


def _setup(tmp_path, *, package=True, attempts=3, void=False):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=12001,
                number=5001,
                name="baltbet-main",
                status="finished",
                ended_at="2026-08-13T18:00:00+00:00",
            )
        )
    package_file = None
    paper_result_file = None
    if package:
        package_file = tmp_path / "package.txt"
        package_file.write_text("30; " + "; ".join(ACTUAL) + "\n")
    else:
        paper_result_file = tmp_path / "paper-package-result.json"
        paper_result_file.write_text(
            '{"decision":"NO BET","actionable":false,"count":0}\n'
        )
    plan_path, _wrapper, _plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=12001,
        drawing_number=None,
        ended_at="2026-08-13T18:00:00+00:00",
        package_file=package_file,
        paper_result_file=paper_result_file,
        stake=30,
        db=db,
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=attempts,
        initial_delay_seconds=0,
        max_delay_seconds=0,
        void_event_orders=(15,) if void else (),
        void_source=("https://example.test/official-void" if void else None),
    )
    plan = load_post_draw_plan(plan_path)
    return factory, plan_path, plan


def _due(plan, index=0):
    return datetime.fromisoformat(plan["due_slots"][index]).astimezone(timezone.utc)


def test_plan_run_pending_results_then_restart_safe_complete(tmp_path):
    factory, plan_path, plan = _setup(tmp_path)
    partial = _payload()
    partial["data"]["events"][4]["result"] = None
    first = run_post_draw_plan(
        factory,
        Client([partial]),
        plan_path=plan_path,
        now=lambda: _due(plan, 0),
    )
    assert first.status == "pending"
    assert first.reason == "PENDING_RESULTS"
    assert first.attempted_slots == (plan["due_slots"][0],)

    client = Client([_payload()])
    complete = run_post_draw_plan(
        factory,
        client,
        plan_path=plan_path,
        now=lambda: _due(plan, 1),
    )
    assert complete.status == "complete"
    assert complete.reason == "SETTLEMENT_COMPLETE"
    assert complete.settlement_sha256 is not None
    assert complete.review_request_sha256 is not None

    repeated = run_post_draw_plan(
        factory,
        Client([]),
        plan_path=plan_path,
        now=lambda: _due(plan, 2),
    )
    assert repeated == complete
    assert client.calls == 1


def test_plan_run_transport_is_retryable_and_integrity_is_blocked(tmp_path):
    factory, plan_path, plan = _setup(tmp_path)
    transport = run_post_draw_plan(
        factory,
        Client([ConnectionError("offline")]),
        plan_path=plan_path,
        now=lambda: _due(plan, 0),
    )
    assert transport.status == "pending"
    assert transport.reason == "PENDING_TRANSPORT"
    assert transport.error_type == "ConnectionError"

    plan_data = json.loads(plan_path.read_text())
    plan_data["drawing_number"] = 9999
    plan_path.write_text(json.dumps(plan_data))
    blocked = run_post_draw_plan(
        factory,
        Client([]),
        plan_path=plan_path,
        now=lambda: _due(plan, 1),
    )
    assert blocked.status == "blocked"
    assert blocked.reason == "REVIEW_BLOCKED_INTEGRITY"


def test_authoritative_void_and_package_free_no_bet_complete(tmp_path):
    factory, plan_path, plan = _setup(tmp_path, void=True)
    payload = _payload()
    payload["data"]["events"][14]["result"] = ""
    payload["data"]["events"][14]["score"] = ""
    state = run_post_draw_plan(
        factory,
        Client([payload]),
        plan_path=plan_path,
        now=lambda: _due(plan),
    )
    assert state.status == "complete"
    assert state.reason == "SETTLEMENT_COMPLETE"

    no_bet_root = tmp_path / "no-bet"
    no_bet_root.mkdir()
    factory, plan_path, plan = _setup(no_bet_root, package=False)
    no_bet = run_post_draw_plan(
        factory,
        Client([_payload()]),
        plan_path=plan_path,
        now=lambda: _due(plan),
    )
    assert no_bet.status == "complete"
    assert no_bet.reason == "PACKAGE_FREE_NO_BET_COMPLETE"
    assert no_bet.package_sha256 is None
    assert no_bet.settlement_sha256 is None
    request = json.loads((plan_path.parent / "review-request.json").read_text())
    assert request["package_kind"] == "package_free_no_bet"
    assert request["best_hits"] is None


def test_postponed_without_authoritative_void_remains_pending(tmp_path):
    factory, plan_path, plan = _setup(tmp_path)
    payload = _payload()
    payload["data"]["events"][14]["result"] = ""
    payload["data"]["events"][14]["score"] = ""
    state = run_post_draw_plan(
        factory,
        Client([payload]),
        plan_path=plan_path,
        now=lambda: _due(plan),
    )
    assert state.status == "pending"
    assert state.reason == "PENDING_RESULTS"
