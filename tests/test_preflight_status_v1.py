from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.cli import app
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    dispatch_morning,
)
from toto_ai.runner.preflight_status import _release_gate_status, build_preflight_status
from toto_ai.runner.scheduler import (
    authorize_experimental_manual_release,
    build_scheduler_plan,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 30, 16, tzinfo=UTC)
FINGERPRINT = "5dd516990e8f64d091a870ec0ee8981a3907e70b63674e6ecc1919abd7ec964b"


def _env(path: Path) -> Path:
    path.write_text("API_SPORTS_KEY=test-only\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _config(tmp_path: Path) -> MorningDispatchConfig:
    return MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "data" / "scheduler" / "morning-dispatch",
        scheduler_root=tmp_path / "reports" / "rehearsal",
        env_file=_env(tmp_path / ".env"),
        bank=4980,
        stake=30,
    )


def _unresolved() -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint=FINGERPRINT,
        detail_sha256="b" * 64,
        preparation_status="unresolved",
        mapped_count=13,
        eligibility_status="unknown",
        span_days=2,
        unresolved_events=(
            MorningUnresolvedEvent(
                event_order=12,
                target_event_id=178965,
                home_team="Каракас",
                away_team="Индепендьенте СФ",
                resolution_status="ambiguous",
                reason="candidate evidence is insufficient",
            ),
            MorningUnresolvedEvent(
                event_order=14,
                target_event_id=178967,
                home_team="Лидс",
                away_team="Сандерленд",
                resolution_status="source_missing_competition",
                reason="source schedule has no candidate",
            ),
        ),
    )


def _ready_with_unresolved_timing() -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint=FINGERPRINT,
        detail_sha256="b" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=2,
        external_coverage_count=14,
        baseline_only_event_orders=(8,),
        unresolved_events=(
            MorningUnresolvedEvent(
                event_order=8,
                target_event_id=178961,
                home_team="Эммен",
                away_team="Алкмаар(м)",
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
            ),
        ),
    )


def _db(path: Path) -> Path:
    engine = init_db(path)
    try:
        with get_session_factory(engine).begin() as session:
            session.add(
                Drawing(
                    id=11990,
                    number=4960,
                    name="baltbet-main",
                    status="active",
                    ended_at="2026-07-30T16:00:00+00:00",
                )
            )
    finally:
        engine.dispose()
    return path


def test_preflight_status_reports_open_drawing_and_passive_gates(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    db = _db(tmp_path / "data" / "toto.db")
    prepare_morning_preanalysis_artifacts(
        times=("08:00", "10:30", "12:00"),
        retry_count=0,
        retry_delay_seconds=0,
        output_dir=config.scheduler_root / "morning-dispatcher",
        env_file=config.env_file,
        project_root=config.project_root,
        bank=config.bank,
        stake=config.stake,
        python_command=sys.executable,
    )
    dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )

    status = build_preflight_status(
        db=db,
        community="baltbet-main",
        state_root=config.state_root,
        scheduler_root=config.scheduler_root,
        now=observed,
    )

    assert status["drawing_number"] == 4960
    assert status["drawing_id"] == 11990
    assert status["deadline_msk"] == "2026-07-30T19:00:00+03:00"
    assert status["preparation_status"] == "unresolved"
    assert status["mapped_count"] == 13
    assert status["pin_count"] == 0
    assert status["unresolved_count"] == 2
    assert Path(status["attention_path"]).is_file()
    assert Path(status["retry_plan_path"]).is_file()
    assert status["morning_activation_state"] == "passive"
    assert status["evening_activation_state"] == "not_requested"
    assert status["package_generation_state"] == "disabled"
    assert status["release_gate"]["state"] == "scheduler_not_activated"


def test_preflight_status_cli_is_concise_and_read_only(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    db = _db(tmp_path / "data" / "toto.db")
    before = db.read_bytes()

    result = CliRunner().invoke(
        app,
        [
            "preflight-status",
            "--open",
            "--db",
            str(db),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
            "--at",
            observed.isoformat(),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["drawing_number"] == 4960
    assert payload["preparation_status"] == "not_run"
    assert payload["morning_activation_state"] == "not_generated"
    assert payload["evening_activation_state"] == "not_requested"
    assert db.read_bytes() == before


def test_ready_mapping_with_unresolved_timing_keeps_retry_nonterminal(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    db = _db(tmp_path / "data" / "toto.db")
    dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _ready_with_unresolved_timing(),
        python_command=sys.executable,
    )
    terminal_values: list[bool] = []

    def fake_verify(*_args, terminal: bool, **_kwargs):
        terminal_values.append(terminal)
        return {"active": not terminal, "next_run": "2026-07-30T08:00:00Z"}

    monkeypatch.setattr(
        "toto_ai.runner.preflight_status.verify_preflight_retry_launch_agent",
        fake_verify,
    )

    status = build_preflight_status(
        db=db,
        community="baltbet-main",
        state_root=config.state_root,
        scheduler_root=config.scheduler_root,
        now=observed,
    )

    assert status["preparation_status"] == "ready"
    assert status["mapped_count"] == 15
    assert status["unresolved_count"] == 1
    assert status["retry_scheduler"]["active"] is True
    assert terminal_values == [False]


def test_release_gate_status_distinguishes_paper_only_and_authorized_plan(tmp_path):
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=datetime(2030, 1, 2, 12, tzinfo=UTC),
        bank=4980,
        stake=30,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    record = {
        "activation_status": "activated",
        "plan_path": str(artifacts.plan_path),
    }

    paper_only = _release_gate_status(record)
    assert paper_only["state"] == "paper_only_not_authorized"
    assert paper_only["profitability_proven"] is False

    authorize_experimental_manual_release(
        plan,
        acknowledged=True,
        now=datetime(2029, 12, 31, 12, tzinfo=UTC),
    )
    authorized = _release_gate_status(record)
    assert authorized["state"] == "experimental_manual_authorized"
    assert authorized["profitability_proven"] is False
    assert authorized["automatic_wagering"] is False
