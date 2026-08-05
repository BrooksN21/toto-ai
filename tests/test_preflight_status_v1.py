from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    dispatch_morning,
)
from toto_ai.runner.preflight_status import build_preflight_status
from toto_ai.runner.scheduler import prepare_morning_preanalysis_artifacts

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
