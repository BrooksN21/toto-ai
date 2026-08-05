"""Deterministic, network-free acceptance rehearsal for preflight retries."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.api_sports import APISportsClient, APISportsError
from toto_ai.external_odds.preparation import (
    DrawingPreparationResult,
    load_local_schedule,
    prepare_drawing,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import seed_reviewed_alias_config
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningExpectedIdentity,
    MorningIdentityDriftError,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    dispatch_morning,
)
from toto_ai.runner.preflight_retry_scheduler import (
    install_preflight_retry_launch_agent,
    prepare_preflight_retry_artifacts,
    run_preflight_retry,
)

UTC = timezone.utc


@dataclass(frozen=True)
class PreflightRetryRehearsalConfig:
    source_db: Path
    target_cache: Path
    schedule_caches: tuple[Path, ...]
    aliases: Path
    reviewed_schedule_catalog: Path
    output_root: Path
    drawing_id: int
    drawing_number: int
    rehearsal_at: datetime
    failed_schedule_dates: tuple[date, ...] = ()
    bank: int = 4980
    stake: int = 30


@dataclass
class _Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _IsolatedLaunchctl:
    def __init__(self, morning: Sequence[_Result] = ()) -> None:
        self.loaded = False
        self.morning = list(morning)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str], **_kwargs: object) -> _Result:
        values = tuple(str(value) for value in command)
        self.commands.append(values)
        if values[0] != "launchctl":
            if not self.morning:
                raise ValueError("isolated retry executed an unexpected command")
            return self.morning.pop(0)
        if values[1] == "print":
            return _Result(0 if self.loaded else 113)
        if values[1] == "bootstrap":
            self.loaded = True
            return _Result(0)
        if values[1] == "bootout":
            self.loaded = False
            return _Result(0)
        raise ValueError("isolated launchctl received an unknown command")


class _FailingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise requests.ConnectionError("rehearsal transport failure")


def run_preflight_retry_rehearsal(
    config: PreflightRetryRehearsalConfig,
) -> dict[str, object]:
    """Prove the passive retry lifecycle without network or production writes."""
    _validate_config(config)
    main_before = _sha256(config.source_db)
    root = config.output_root.resolve()
    if root.exists():
        raise ValueError("rehearsal output root already exists")
    root.mkdir(parents=True)
    isolated_db = root / "toto.db"
    _backup_sqlite(config.source_db, isolated_db)
    _reset_drawing_state(isolated_db, config.drawing_id)
    isolated_aliases = root / "data/external-odds/team-aliases.json"
    isolated_aliases.parent.mkdir(parents=True)
    shutil.copyfile(config.aliases, isolated_aliases)
    isolated_reviewed_catalog = _copy_reviewed_catalog(
        config.reviewed_schedule_catalog,
        root / "data/reviewed-schedule" / str(config.drawing_number),
    )
    env_file = root / ".env"
    env_file.write_text("API_SPORTS_KEY=rehearsal-only\n", encoding="utf-8")
    env_file.chmod(0o600)

    payload = json.loads(config.target_cache.read_text(encoding="utf-8"))
    target = parse_target_drawing(payload, fetched_at=config.rehearsal_at)
    if (
        target.drawing_id != config.drawing_id
        or target.drawing_number != config.drawing_number
    ):
        raise ValueError("rehearsal target identity does not match configuration")
    candidates = _load_schedule_caches(config.schedule_caches)
    diagnostics = tuple(
        {
            "sport": "football",
            "date": _schedule_date(path),
            "status": "success",
            "reason": f"immutable local cache sha256={_sha256(path)}",
        }
        for path in config.schedule_caches
    ) + tuple(
        {
            "sport": "football",
            "date": requested_date.isoformat(),
            "status": "failed",
            "reason": "rehearsal injected unrelated provider plan-limit",
        }
        for requested_date in config.failed_schedule_dates
    )
    engine = init_db(isolated_db)
    try:
        session_factory = get_session_factory(engine)
        seed_reviewed_alias_config(
            session_factory, isolated_aliases, provider="api-sports"
        )
        initial = prepare_drawing(
            target,
            candidates,
            session_factory=session_factory,
            provider="api-sports",
            schedule_diagnostics=diagnostics,
            evaluated_at=config.rehearsal_at,
        )
        resolved_count = _resolved_count(initial)
        if initial.status != "unresolved" or resolved_count != 13:
            raise ValueError(
                "expected initial ACTION REQUIRED 13/15, got "
                f"{initial.status} {resolved_count}/15"
            )
        if _pin_count(isolated_db, config.drawing_id) != 0:
            raise ValueError("initial unresolved preparation published pins")
        initial_evidence = _morning_evidence(
            target, initial, detail_sha256=_payload_sha256(payload)
        )
        dispatch_config = MorningDispatchConfig(
            project_root=root,
            state_root=root / "runtime/morning-dispatch",
            scheduler_root=root / "runtime/schedulers",
            env_file=env_file,
            bank=config.bank,
            stake=config.stake,
            db=isolated_db,
            aliases=isolated_aliases,
            maintenance_lock=root / "runtime/global-maintenance.lock",
            reviewed_schedule_catalog=isolated_reviewed_catalog,
        )
        first_dispatch = dispatch_morning(
            dispatch_config,
            observed_at=config.rehearsal_at,
            now=lambda: config.rehearsal_at,
            prepare_current=lambda _now: initial_evidence,
            python_command=sys.executable,
        )
        if (
            first_dispatch.status != "deferred"
            or first_dispatch.attention_path is None
            or first_dispatch.retry_plan_path is None
        ):
            raise ValueError("initial dispatch did not create ACTION REQUIRED")

        retry_results = _exercise_retry_lifecycle(
            first_dispatch.retry_plan_path,
            root=root / "runtime/retry-branches",
        )
        drift_results = _exercise_identity_drift(
            dispatch_config,
            target=target,
            evidence=initial_evidence,
            observed_at=config.rehearsal_at,
        )

        ready = prepare_drawing(
            target,
            candidates,
            session_factory=session_factory,
            provider="api-sports",
            schedule_diagnostics=diagnostics,
            reviewed_schedule_catalog=isolated_reviewed_catalog,
            evaluated_at=config.rehearsal_at,
        )
        if ready.status != "ready" or len(ready.pins) != 15:
            raise ValueError(
                "strict reviewed evidence did not produce READY 15/15"
            )
        if _pin_count(isolated_db, config.drawing_id) != 15:
            raise ValueError("ready preparation did not publish exactly 15 pins")
        ready_evidence = _morning_evidence(
            target, ready, detail_sha256=_payload_sha256(payload)
        )
        ready_dispatch = dispatch_morning(
            dispatch_config,
            observed_at=config.rehearsal_at,
            now=lambda: config.rehearsal_at,
            prepare_current=lambda _now: ready_evidence,
            python_command=sys.executable,
            expected_identity=MorningExpectedIdentity(
                drawing_id=target.drawing_id,
                drawing_number=config.drawing_number,
                deadline=target.deadline,
                drawing_fingerprint=ready.drawing_fingerprint,
            ),
        )
        if (
            ready_dispatch.status != "scheduled"
            or ready_dispatch.activation_status != "generated"
        ):
            raise ValueError("ready dispatch did not remain generation-only")
    finally:
        engine.dispose()

    missing_key = _exercise_missing_key(
        first_dispatch.retry_plan_path,
        root=root / "runtime/missing-key",
    )
    transport = _exercise_transport_failure(root / "runtime/transport")
    forbidden = _forbidden_outputs(root)
    if forbidden:
        raise ValueError(f"rehearsal created forbidden outputs: {forbidden}")
    main_after = _sha256(config.source_db)
    if main_before != main_after:
        raise ValueError("main database checksum changed during rehearsal")
    summary: dict[str, object] = {
        "status": "PASS",
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "main_db_sha256_before": main_before,
        "main_db_sha256_after": main_after,
        "isolated_db_sha256": _sha256(isolated_db),
        "initial": {
            "status": "ACTION REQUIRED",
            "resolved_count": resolved_count,
            "pin_count": 0,
            "attention_path": str(first_dispatch.attention_path),
        },
        "reviewed": {
            "status": "READY",
            "resolved_count": 15,
            "pin_count": 15,
            "catalog_sha256": _sha256(isolated_reviewed_catalog),
        },
        "retry": retry_results,
        "identity_drift": drift_results,
        "missing_api_key": missing_key,
        "bounded_transport_failure": transport,
        "evening": {
            "activation_status": ready_dispatch.activation_status,
            "plan_path": str(ready_dispatch.plan_path),
        },
        "package_count": 0,
        "bet_ready_count": 0,
        "network_requests": 0,
    }
    _write_report(root, summary)
    return summary


def _exercise_retry_lifecycle(plan_path: Path, *, root: Path) -> dict[str, object]:
    due_plan = _copy_plan(plan_path, root / "due/retry-plan.json")
    due_runner = _IsolatedLaunchctl(
        (
            _Result(2, '{"status":"deferred","reason":"preparation_not_ready"}'),
            _Result(0, '{"status":"scheduled","reason":"ready"}'),
        )
    )
    due_artifacts = prepare_preflight_retry_artifacts(due_plan)
    due_launch_agents = root / "due/LaunchAgents"
    install_preflight_retry_launch_agent(
        due_artifacts,
        launch_agents_root=due_launch_agents,
        command_runner=due_runner,
    )
    first = run_preflight_retry(
        due_plan,
        now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=due_runner,
        launch_agents_root=due_launch_agents,
    )
    second = run_preflight_retry(
        due_plan,
        now=datetime(2026, 7, 31, 10, 2, tzinfo=UTC),
        command_runner=due_runner,
        launch_agents_root=due_launch_agents,
    )
    ready = run_preflight_retry(
        due_plan,
        now=datetime(2026, 7, 31, 12, 1, tzinfo=UTC),
        command_runner=due_runner,
        launch_agents_root=due_launch_agents,
    )
    command_count = sum(item[0] != "launchctl" for item in due_runner.commands)
    if (first, second, ready, command_count, due_runner.loaded) != (2, 0, 0, 2, False):
        raise ValueError("due/idempotent/READY retry lifecycle failed")

    hard_plan = _copy_plan(plan_path, root / "hard-stop/retry-plan.json")
    hard_runner = _IsolatedLaunchctl()
    hard_artifacts = prepare_preflight_retry_artifacts(hard_plan)
    hard_launch_agents = root / "hard-stop/LaunchAgents"
    install_preflight_retry_launch_agent(
        hard_artifacts,
        launch_agents_root=hard_launch_agents,
        command_runner=hard_runner,
    )
    hard_code = run_preflight_retry(
        hard_plan,
        now=datetime(2026, 7, 31, 15, 0, tzinfo=UTC),
        command_runner=hard_runner,
        launch_agents_root=hard_launch_agents,
    )
    if hard_code != 0 or hard_runner.loaded:
        raise ValueError("hard-stop cleanup failed")

    drift_plan = _copy_plan(plan_path, root / "drift/retry-plan.json")
    drift_runner = _IsolatedLaunchctl(
        (_Result(3, '{"status":"terminal","reason":"identity_drift"}'),)
    )
    drift_artifacts = prepare_preflight_retry_artifacts(drift_plan)
    drift_launch_agents = root / "drift/LaunchAgents"
    install_preflight_retry_launch_agent(
        drift_artifacts,
        launch_agents_root=drift_launch_agents,
        command_runner=drift_runner,
    )
    drift_code = run_preflight_retry(
        drift_plan,
        now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=drift_runner,
        launch_agents_root=drift_launch_agents,
    )
    if drift_code != 3 or drift_runner.loaded:
        raise ValueError("identity-drift cleanup failed")
    return {
        "due": "PASS",
        "idempotency": "PASS",
        "ready_cleanup": "PASS",
        "hard_stop_cleanup": "PASS",
        "drift_cleanup": "PASS",
    }


def _exercise_identity_drift(
    config: MorningDispatchConfig,
    *,
    target: object,
    evidence: MorningPreparedDrawing,
    observed_at: datetime,
) -> dict[str, str]:
    checks = {
        "drawing": MorningExpectedIdentity(
            evidence.drawing_id + 1,
            evidence.drawing_number,
            evidence.deadline,
            evidence.drawing_fingerprint,
        ),
        "fingerprint": MorningExpectedIdentity(
            evidence.drawing_id,
            evidence.drawing_number,
            evidence.deadline,
            "0" * 64,
        ),
    }
    results = {}
    for name, expected in checks.items():
        try:
            dispatch_morning(
                config,
                observed_at=observed_at,
                now=lambda: observed_at,
                prepare_current=lambda _now: evidence,
                expected_identity=expected,
            )
        except MorningIdentityDriftError:
            results[name] = "PASS"
        else:
            raise ValueError(f"{name} drift did not fail closed")
    return results


def _exercise_missing_key(plan_path: Path, *, root: Path) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    env_file = root / "missing-key.env"
    root.mkdir(parents=True, exist_ok=True)
    env_file.write_text("OTHER_VALUE=present\n", encoding="utf-8")
    env_file.chmod(0o600)
    for attempt in plan["attempts"]:
        command = attempt["command"]
        command[command.index("--env-file") + 1] = str(env_file)
    plan.pop("plan_sha256")
    plan["plan_sha256"] = hashlib.sha256(_canonical(plan)).hexdigest()
    isolated_plan = root / "retry-plan.json"
    isolated_plan.write_bytes(_canonical(plan) + b"\n")
    artifacts = prepare_preflight_retry_artifacts(isolated_plan)
    completed = subprocess.run(
        (str(artifacts.wrapper_path),),
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    if (
        completed.returncode != 78
        or "API_SPORTS_KEY is required" not in completed.stderr
    ):
        raise ValueError("missing API key did not fail before retry execution")
    return {"status": "PASS", "exit_code": completed.returncode}


def _exercise_transport_failure(root: Path) -> dict[str, object]:
    session = _FailingTransport()
    client = APISportsClient(
        "rehearsal-only",
        session=session,  # type: ignore[arg-type]
        cache_dir=root,
        max_retries=1,
    )
    try:
        client.fetch_schedule("football", (date(2099, 1, 1),))
    except APISportsError as error:
        if str(error) != "API-Sports transport connection failed":
            raise ValueError("transport failure was not sanitized") from error
    else:
        raise ValueError("bounded transport rehearsal unexpectedly succeeded")
    if session.calls != 2 or client.requests_made != 2:
        raise ValueError("transport retry was not bounded to two attempts")
    return {"status": "PASS", "attempts": session.calls}


def _morning_evidence(
    target: object,
    result: DrawingPreparationResult,
    *,
    detail_sha256: str,
) -> MorningPreparedDrawing:
    events = target.events  # type: ignore[attr-defined]
    unresolved = tuple(
        MorningUnresolvedEvent(
            event_order=item.event_order,
            target_event_id=item.target_event_id,
            home_team=events[item.event_order].home_team,
            away_team=events[item.event_order].away_team,
            resolution_status=item.status,
            reason=item.reason,
            candidate_evidence=item.candidate_evidence,
            provider_diagnostics=result.schedule_diagnostics,
        )
        for item in result.events
        if item.status != "matched"
    )
    return MorningPreparedDrawing(
        drawing_id=result.drawing_id,
        drawing_number=result.drawing_number,  # type: ignore[arg-type]
        deadline=target.deadline,  # type: ignore[attr-defined]
        drawing_fingerprint=result.drawing_fingerprint,
        detail_sha256=detail_sha256,
        preparation_status=result.status,
        mapped_count=_resolved_count(result),
        eligibility_status=result.eligibility.status,
        span_days=result.eligibility.span_days,
        unresolved_events=unresolved,
    )


def _load_schedule_caches(paths: Sequence[Path]) -> tuple[object, ...]:
    events = {}
    for path in paths:
        for event in load_local_schedule(path):
            events[(event.provider, event.provider_event_id)] = event
    return tuple(events[key] for key in sorted(events))


def _schedule_date(path: Path) -> str | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = payload.get("payload", payload)
    parameters = body.get("parameters", {})
    value = parameters.get("date")
    return value if isinstance(value, str) else None


def _copy_plan(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return destination


def _reset_drawing_state(db: Path, drawing_id: int) -> None:
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "DELETE FROM drawing_pin_set_items WHERE drawing_id = ?", (drawing_id,)
        )
        connection.execute(
            "DELETE FROM drawing_pin_sets WHERE drawing_id = ?", (drawing_id,)
        )
        connection.execute(
            "DELETE FROM drawing_event_pins WHERE drawing_id = ?", (drawing_id,)
        )
        connection.execute(
            "DELETE FROM drawing_preparations WHERE drawing_id = ?", (drawing_id,)
        )


def _pin_count(db: Path, drawing_id: int) -> int:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        legacy = connection.execute(
            "SELECT COUNT(*) FROM drawing_event_pins WHERE drawing_id = ? "
            "AND status = 'valid'",
            (drawing_id,),
        ).fetchone()[0]
        mixed = connection.execute(
            "SELECT COUNT(*) FROM drawing_pin_set_items WHERE drawing_id = ?",
            (drawing_id,),
        ).fetchone()[0]
    return int(legacy + mixed)


def _backup_sqlite(source: Path, destination: Path) -> None:
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)


def _copy_reviewed_catalog(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True)
    for item in source.parent.iterdir():
        if item.is_symlink() or not item.is_file():
            raise ValueError(f"reviewed schedule input is invalid: {item}")
        shutil.copyfile(item, destination / item.name)
    return destination / source.name


def _forbidden_outputs(root: Path) -> tuple[str, ...]:
    forbidden = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            "package" in name
            or name in {".bet-ready", ".no-bet", "bet", "coupons.csv"}
            or name.endswith((".bet-ready", ".no-bet"))
        ):
            forbidden.append(str(path))
    return tuple(sorted(forbidden))


def _write_report(root: Path, summary: Mapping[str, object]) -> None:
    (root / "rehearsal-summary.json").write_bytes(_canonical(summary) + b"\n")
    (root / "rehearsal-summary.md").write_text(
        "# Preflight retry E2E rehearsal\n\n"
        f"- Status: **{summary['status']}**\n"
        f"- Drawing: **{summary['drawing_number']}**\n"
        "- Initial: **ACTION REQUIRED 13/15, 0 pins**\n"
        "- Reviewed: **READY 15/15, 15 pins**\n"
        "- Package/bet-ready: **0/0**\n"
        "- Main database checksum: **unchanged**\n",
        encoding="utf-8",
    )


def _resolved_count(result: DrawingPreparationResult) -> int:
    return sum(item.status == "matched" for item in result.events)


def _payload_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _validate_config(config: PreflightRetryRehearsalConfig) -> None:
    if not isinstance(config, PreflightRetryRehearsalConfig):
        raise ValueError("config must be PreflightRetryRehearsalConfig")
    for path in (
        config.source_db,
        config.target_cache,
        config.aliases,
        config.reviewed_schedule_catalog,
        *config.schedule_caches,
    ):
        if not Path(path).is_file() or Path(path).is_symlink():
            raise ValueError(f"rehearsal input is not a regular file: {path}")
    if not config.schedule_caches:
        raise ValueError("at least one schedule cache is required")
    if config.rehearsal_at.tzinfo is None:
        raise ValueError("rehearsal_at must be timezone-aware")
    if len(set(config.failed_schedule_dates)) != len(
        config.failed_schedule_dates
    ):
        raise ValueError("failed_schedule_dates must be unique")
