import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from tests.test_external_event_matching_drawing_4951 import (
    EXPECTED_PROVIDER_IDS,
    _provider_events,
    _target_drawing,
)
from toto_ai import cli
from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import ArchivedPackage, Drawing, DrawingEventPin
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import QuotaState
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.preparation import prepare_drawing
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import load_ready_drawing_pins
from toto_ai.runner.models import DrawingRunnerConfig, pin_drawing
from toto_ai.runner.scheduler import (
    SchedulerPhaseResult,
    VirtualSchedulerClock,
    build_scheduler_plan,
    execute_scheduler_plan,
)

PACKAGE = b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.10,0.10\n"
CLI_RUNNER = CliRunner()


class ReplayProvider:
    provider_name = "api-sports"
    quota_state = QuotaState(100, 100, 10, 10)
    requests_made = 0
    cache_hits = 0

    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        requested = set(dates)
        return tuple(
            replace(
                event,
                home_team=f"unrelated display {event.provider_event_id}",
                away_team=f"other display {event.provider_event_id}",
            )
            for event in _provider_events()
            if event.starts_at.date() in requested
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        return ()


def _plan(tmp_path: Path, *, suffix: str):
    write_empty_schedule_evidence_ledger(tmp_path)
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")
    db = tmp_path / "toto.sqlite"
    return build_scheduler_plan(
        drawing=4951,
        drawing_id=11968,
        ended_at=_target_drawing().deadline,
        bank=4980,
        output_dir=tmp_path / suffix,
        project_root=tmp_path,
        db=db,
        aliases=aliases,
    )


def _target_cache_payload(*, deadline=None):
    target = _target_drawing()
    deadline = deadline or target.deadline
    return {
        "data": {
            "id": target.drawing_id,
            "number": target.drawing_number,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": deadline.isoformat(),
            "events": [
                {
                    "id": event.event_id,
                    "order": event.event_order,
                    "name": f"{event.home_team} - {event.away_team}",
                    "name_en": None,
                    "championship": event.championship,
                    "sport": event.sport,
                    "start_at": None,
                    "quotes": {
                        "bk_win_1": event.bk_probabilities[0],
                        "bk_draw": event.bk_probabilities[1],
                        "bk_win_2": event.bk_probabilities[2],
                        "pool_win_1": event.bk_probabilities[0],
                        "pool_draw": event.bk_probabilities[1],
                        "pool_win_2": event.bk_probabilities[2],
                    },
                }
                for event in target.events
            ],
        }
    }


def test_morning_4953_zero_mapped_is_terminal_fail_without_package(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    deadline = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    target_payload = _target_cache_payload(deadline=deadline)
    target_payload["data"]["id"] = 11971
    target_payload["data"]["number"] = 4953
    target_cache = write_drawing_detail_cache(
        target_payload,
        drawing_id=11971,
        cache_dir=tmp_path / "raw",
        fetched_at=datetime.now(timezone.utc),
        source="test-fixture",
        allowed_root=tmp_path,
    )
    schedule_cache = tmp_path / "schedule.json"
    schedule_cache.write_text(
        '{"fetched_at":"2026-07-21T12:00:00+00:00","events":[]}\n',
        encoding="utf-8",
    )
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")
    schedule_evidence_ledger = (
        tmp_path / "data" / "schedule-evidence" / "ledger.json"
    )
    schedule_evidence_ledger.parent.mkdir(parents=True)
    schedule_evidence_ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-06T00:00:00Z",
                "observations": [],
            }
        ),
        encoding="utf-8",
    )
    db = tmp_path / "unresolved.sqlite"
    engine = init_db(db)
    with get_session_factory(engine)() as session:
        session.add(
            Drawing(
                id=11971,
                number=4953,
                name="baltbet-main",
                status="active",
                ended_at=deadline.isoformat(),
            )
        )
        session.commit()
    engine.dispose()

    result = CLI_RUNNER.invoke(
        cli.app,
        [
            "prepare-drawing",
            "--drawing-id",
            "11971",
            "--db",
            str(db),
            "--aliases",
            str(aliases),
            "--target-cache",
            str(target_cache.path),
            "--schedule-cache",
            str(schedule_cache),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "unresolved"
    assert payload["mapped_count"] == 0
    assert payload["unresolved_event_orders"] == list(range(15))
    engine = init_db(db)
    with get_session_factory(engine)() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0
    engine.dispose()

    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4953,
        drawing_id=11971,
        ended_at=deadline,
        bank=4980,
        output_dir=tmp_path / "morning-4953",
        project_root=tmp_path,
        db=db,
        aliases=aliases,
    )
    clock = VirtualSchedulerClock(plan.preflight_at)
    pinned = pin_drawing(
        parse_target_drawing(target_payload, fetched_at=datetime.now(timezone.utc))
    )

    def production_preflight(_context):
        try:
            cli._prepare_runner_resources(
                config=DrawingRunnerConfig(bank=4980),
                target=pinned,
                preflight_at=_context.started_at,
                db=db,
                aliases=aliases,
                report_dir=tmp_path / "runner-reports",
                cache_root=tmp_path / "provider-cache",
                provider_factory=lambda _path: object(),
            )
        except ValueError as error:
            return SchedulerPhaseResult.failed(str(error))
        raise AssertionError("zero-mapped preparation unexpectedly passed preflight")

    scheduled = execute_scheduler_plan(
        plan,
        phase_runner=production_preflight,
        now=clock.now,
        sleep=clock.sleep,
        run_id="4953-zero-mapped",
    )

    assert scheduled.outcome == "failed"
    assert scheduled.decision == "FAILED"
    assert scheduled.package_path is None
    assert scheduled.marker_path.name == ".failed"
    assert not (scheduled.run_dir / ".bet-ready").exists()
    assert not (scheduled.run_dir / "package.csv").exists()


def test_scheduler_prepare_final_pin_use_and_stale_fail_closed(tmp_path: Path):
    plan = _plan(tmp_path, suffix="ready")
    engine = init_db(plan.db)
    session_factory = get_session_factory(engine)
    target = _target_drawing()
    candidates = _provider_events()
    final_snapshots = []

    def ready_runner(context):
        if context.phase == "preflight":
            prepared = prepare_drawing(
                target, candidates, session_factory=session_factory
            )
            assert prepared.status == "ready"
            assert prepared.mapped_count == 15
            return SchedulerPhaseResult.completed("15/15 preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("fallback retained for audit")
        fingerprint = target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        )
        pins = load_ready_drawing_pins(
            session_factory,
            drawing_id=target.drawing_id,
            drawing_fingerprint=fingerprint,
            provider="api-sports",
        )
        snapshot = build_external_collection(
            target,
            ReplayProvider(),
            aliases={},
            prepared_pins=pins,
            now=lambda: context.started_at.astimezone(timezone.utc),
        )
        final_snapshots.append(snapshot)
        assert tuple(event.provider_event_id for event in snapshot.events) == (
            EXPECTED_PROVIDER_IDS
        )
        assert {event.matcher_version for event in snapshot.events} == {
            "systematic-team-pin-v1"
        }
        return SchedulerPhaseResult.play(
            PACKAGE,
            effective_bank=4980,
            selected_count=1,
            selected_cost=30,
            override_sha256=context.override_sha256,
        )

    clock = VirtualSchedulerClock(plan.preflight_at)
    result = execute_scheduler_plan(
        plan,
        phase_runner=ready_runner,
        now=clock.now,
        sleep=clock.sleep,
        run_id="ready-e2e-shared-clock",
    )
    assert result.outcome == "bet-ready"
    assert result.marker_path.name == ".bet-ready"
    assert result.marker_path.is_file()
    assert final_snapshots
    with session_factory() as session:
        stored_drawing = session.get(Drawing, target.drawing_id)
        assert stored_drawing is not None
        assert stored_drawing.number == target.drawing_number
        assert datetime.fromisoformat(stored_drawing.ended_at) == target.deadline
        archived = session.scalar(select(ArchivedPackage))
        assert archived is not None
        assert archived.drawing_id == target.drawing_id
        assert archived.drawing_number == target.drawing_number

    stale_plan = _plan(tmp_path, suffix="stale")
    stale_target = replace(
        target,
        events=(replace(target.events[0], home_team="changed"), *target.events[1:]),
    )

    def stale_runner(context):
        if context.phase == "preflight":
            prepare_drawing(target, candidates, session_factory=session_factory)
            return SchedulerPhaseResult.completed("original preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback package")
        stale_fingerprint = target_fingerprint(
            stale_target.drawing_id,
            stale_target.drawing_number,
            stale_target.deadline,
            stale_target.events,
        )
        load_ready_drawing_pins(
            session_factory,
            drawing_id=stale_target.drawing_id,
            drawing_fingerprint=stale_fingerprint,
            provider="api-sports",
        )
        raise AssertionError("stale fingerprint must fail before PLAY")

    stale_clock = VirtualSchedulerClock(stale_plan.preflight_at)
    stale_result = execute_scheduler_plan(
        stale_plan,
        phase_runner=stale_runner,
        now=stale_clock.now,
        sleep=stale_clock.sleep,
        run_id="stale-e2e",
    )
    assert stale_result.outcome == "failed"
    assert stale_result.decision == "FAILED"
    assert not (stale_result.run_dir / ".bet-ready").exists()
    engine.dispose()
