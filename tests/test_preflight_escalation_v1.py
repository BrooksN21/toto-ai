from __future__ import annotations

import json
import plistlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai import cli
from toto_ai.external_odds.schedule_evidence import (
    load_schedule_evidence_ledger,
)
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningExpectedIdentity,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    dispatch_morning,
)
from toto_ai.runner.preflight_retry_scheduler import (
    prepare_preflight_retry_artifacts,
    verify_preflight_retry_launch_agent,
)
from toto_ai.runner.scheduler import prepare_morning_preanalysis_artifacts

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 30, 16, tzinfo=UTC)
FINGERPRINT = "5dd516990e8f64d091a870ec0ee8981a3907e70b63674e6ecc1919abd7ec964b"


def _env(path: Path) -> Path:
    path.write_text("API_SPORTS_KEY=test-only\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _config(tmp_path: Path) -> MorningDispatchConfig:
    write_empty_schedule_evidence_ledger(tmp_path)
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
                candidate_evidence=(
                    {
                        "provider_event_id": "1547782",
                        "provider_home_team_id": "2808",
                        "provider_away_team_id": "1139",
                    },
                ),
                provider_diagnostics=(
                    {
                        "sport": "football",
                        "date": "2026-07-30",
                        "status": "success",
                        "reason": None,
                    },
                ),
            ),
            MorningUnresolvedEvent(
                event_order=14,
                target_event_id=178967,
                home_team="Лидс",
                away_team="Сандерленд",
                resolution_status="source_missing_competition",
                reason="source schedule has no candidate",
                candidate_evidence=(),
                provider_diagnostics=(
                    {
                        "sport": "football",
                        "date": "2026-07-30",
                        "status": "success",
                        "reason": None,
                    },
                ),
            ),
        ),
    )


def _ready() -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint=FINGERPRINT,
        detail_sha256="c" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="playable",
        span_days=2,
        unresolved_events=(),
    )


def _timing_unknown() -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint=FINGERPRINT,
        detail_sha256="c" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        external_coverage_count=13,
        baseline_only_event_orders=(7, 14),
        unresolved_events=(
            MorningUnresolvedEvent(
                event_order=7,
                target_event_id=178907,
                home_team="Home 7",
                away_team="Away 7",
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
            ),
            MorningUnresolvedEvent(
                event_order=14,
                target_event_id=178914,
                home_team="Home 14",
                away_team="Away 14",
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
            ),
        ),
    )


def _unresolved_count(count: int) -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        **{
            **_unresolved().__dict__,
            "mapped_count": 15 - count,
            "unresolved_events": tuple(
                MorningUnresolvedEvent(
                    event_order=order,
                    target_event_id=178900 + order,
                    home_team=f"Home {order}",
                    away_team=f"Away {order}",
                    resolution_status="source_missing_competition",
                    reason="source schedule has no candidate",
                    candidate_evidence=(),
                    provider_diagnostics=(),
                )
                for order in range(count)
            ),
        }
    )


def test_morning_preparation_materializes_baseline_only_missing_kickoffs():
    starts_at = DEADLINE + timedelta(hours=1)
    target = SimpleNamespace(
        events=tuple(
            SimpleNamespace(
                event_id=178900 + order,
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                starts_at=(starts_at if order == 7 else None),
            )
            for order in range(15)
        )
    )
    prepared = SimpleNamespace(
        events=tuple(
            SimpleNamespace(
                event_order=order,
                target_event_id=178900 + order,
                status=("baseline_only" if order in {7, 14} else "matched"),
                reason="prepared",
                candidate_evidence=(),
            )
            for order in range(15)
        ),
        baseline_only_event_orders=(7, 14),
        eligibility=SimpleNamespace(status="unknown"),
    )

    unresolved = cli._morning_unresolved_events(
        target=target,
        prepared=prepared,
        schedule_diagnostics=({"status": "success"},),
    )

    assert [item.event_order for item in unresolved] == [14]
    assert unresolved[0].target_event_id == 178914
    assert unresolved[0].resolution_status == "timing_unknown"
    assert unresolved[0].required_evidence_type == "reviewed_schedule"
    evidence = MorningPreparedDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint=FINGERPRINT,
        detail_sha256="e" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        external_coverage_count=13,
        baseline_only_event_orders=(7, 14),
        unresolved_events=unresolved,
    )
    assert evidence.unresolved_events == unresolved


def test_real_morning_dispatch_cli_passes_repository_schedule_evidence_ledger(
    tmp_path, monkeypatch
):
    env_file = _env(tmp_path / ".env")
    captured: list[Path] = []

    def fake_prepare(**kwargs):
        captured.append(kwargs["schedule_evidence_ledger"])
        return _unresolved()

    def fake_dispatch(_config, *, prepare_current, observed_at, **_kwargs):
        prepare_current(observed_at)
        return SimpleNamespace(
            status="scheduled",
            reason="READY 15/15",
            record_path=tmp_path / "record.json",
            plan_id="plan",
            plan_path=None,
            launch_agent_path=None,
            launch_agent_label=None,
            activation_status="not_requested",
            attention_path=None,
            retry_plan_path=None,
            review_queue_path=None,
        )

    monkeypatch.setattr(cli, "_prepare_current_for_morning", fake_prepare)
    monkeypatch.setattr(cli, "dispatch_morning", fake_dispatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == [tmp_path / "data/schedule-evidence/ledger.json"]


def test_morning_dispatch_accepts_contained_schedule_evidence_ledger_override(
    tmp_path, monkeypatch
):
    env_file = _env(tmp_path / ".env")
    custom_ledger = tmp_path / "evidence" / "ledger.json"
    custom_ledger.parent.mkdir()
    custom_ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-07-30T07:00:00Z",
                "observations": [],
            }
        ),
        encoding="utf-8",
    )
    captured: list[Path] = []

    def fake_prepare(**kwargs):
        captured.append(kwargs["schedule_evidence_ledger"])
        return _unresolved()

    def fake_dispatch(_config, *, prepare_current, observed_at, **_kwargs):
        prepare_current(observed_at)
        return SimpleNamespace(
            status="scheduled",
            reason="READY 15/15",
            record_path=tmp_path / "record.json",
            plan_id="plan",
            plan_path=None,
            launch_agent_path=None,
            launch_agent_label=None,
            activation_status="not_requested",
            attention_path=None,
            retry_plan_path=None,
            review_queue_path=None,
        )

    monkeypatch.setattr(cli, "_prepare_current_for_morning", fake_prepare)
    monkeypatch.setattr(cli, "dispatch_morning", fake_dispatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--schedule-evidence-ledger",
            str(custom_ledger),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == [custom_ledger]


def test_morning_dispatch_rejects_invalid_schedule_evidence_ledger(
    tmp_path, monkeypatch
):
    env_file = _env(tmp_path / ".env")
    ledger = tmp_path / "data" / "schedule-evidence" / "ledger.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"schema_version": 999}', encoding="utf-8")

    def fake_prepare(**kwargs):
        load_schedule_evidence_ledger(kwargs["schedule_evidence_ledger"])
        raise AssertionError("invalid ledger must fail before preparation")

    def fake_dispatch(_config, *, prepare_current, observed_at, **_kwargs):
        prepare_current(observed_at)
        raise AssertionError("invalid ledger must not produce a dispatch result")

    monkeypatch.setattr(cli, "_prepare_current_for_morning", fake_prepare)
    monkeypatch.setattr(cli, "dispatch_morning", fake_dispatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 2
    assert "schedule evidence ledger fields are invalid" in result.output


def test_real_morning_dispatch_wrapper_uses_ledger_kickoffs_for_eligibility(
    tmp_path, monkeypatch
):
    import hashlib

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from toto_ai.db.models import Base
    from toto_ai.external_odds.domain import (
        ProviderEvent,
        TargetDrawing,
        TargetEvent,
    )
    from toto_ai.external_odds.preparation import prepare_drawing
    from toto_ai.external_odds.team_registry import backfill_accepted_matches

    env_file = _env(tmp_path / ".env")
    starts_at = DEADLINE + timedelta(hours=2)
    target = TargetDrawing(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        fetched_at=DEADLINE - timedelta(hours=1),
        events=tuple(
            TargetEvent(
                drawing_id=11990,
                drawing_number=4960,
                event_id=178900 + order,
                event_order=order,
                sport="football",
                championship="Test Competition",
                starts_at=None,
                deadline=DEADLINE,
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                home_team_en=None,
                away_team_en=None,
                bk_probabilities=(0.4, 0.3, 0.3),
                pool_probabilities=(0.4, 0.3, 0.3),
            )
            for order in range(15)
        ),
    )
    candidate = ProviderEvent(
        provider="api-sports",
        provider_event_id="fixture-0",
        sport="football",
        league="Test Competition",
        starts_at=starts_at,
        home_team="Provider Home 0",
        away_team="Provider Away 0",
        fetched_at=target.fetched_at,
        payload_hash="fixture-hash-0",
        country="Test",
        provider_home_team_id="provider-home-0",
        provider_away_team_id="provider-away-0",
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    assert backfill_accepted_matches(
        session_factory,
        [
            {
                "drawing_id": target.drawing_id,
                "target_event_id": target.events[0].event_id,
                "provider_fixture_id": candidate.provider_event_id,
                "sport": "football",
                "target_home": target.events[0].home_team,
                "target_away": target.events[0].away_team,
                "provider_home": candidate.home_team,
                "provider_away": candidate.away_team,
                "provider_home_team_id": candidate.provider_home_team_id,
                "provider_away_team_id": candidate.provider_away_team_id,
                "country": "Test",
                "league": candidate.league,
                "reviewed": True,
            }
        ],
    ) == 2
    baseline = prepare_drawing(
        target,
        (candidate,),
        session_factory=session_factory,
    )
    assert baseline.eligibility.status == "unknown"

    evidence_root = tmp_path / "data" / "schedule-evidence"
    evidence_root.mkdir(parents=True)
    review = evidence_root / "review.md"
    review.write_text("reviewed official schedule", encoding="utf-8")
    review_hash = hashlib.sha256(review.read_bytes()).hexdigest()
    ledger = evidence_root / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": target.fetched_at.isoformat(),
                "observations": [
                    {
                        "observation_id": f"event-{order}",
                        "sport": "football",
                        "gender_age_class": "men-senior",
                        "competition_aliases": ["Test Competition"],
                        "home_entity": f"Home {order}",
                        "home_aliases": [f"Home {order}"],
                        "away_entity": f"Away {order}",
                        "away_aliases": [f"Away {order}"],
                        "starts_at": starts_at.isoformat(),
                        "status": "scheduled",
                        "conditional": False,
                        "reviewer": "test-reviewer",
                        "reviewed_at": target.fetched_at.isoformat(),
                        "review_document": review.name,
                        "review_document_sha256": review_hash,
                        "claims": [
                            {
                                "source_name": "official",
                                "role": "official",
                                "source_url": "https://example.test/schedule",
                            }
                        ],
                    }
                    for order in range(1, 15)
                ],
            }
        ),
        encoding="utf-8",
    )
    observed: list[MorningPreparedDrawing] = []

    def fake_prepare(**kwargs):
        refreshed = prepare_drawing(
            target,
            (candidate,),
            session_factory=session_factory,
            schedule_evidence_ledger=kwargs["schedule_evidence_ledger"],
            evaluated_at=target.fetched_at,
        )
        evidence = MorningPreparedDrawing(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            deadline=target.deadline,
            drawing_fingerprint=refreshed.drawing_fingerprint,
            detail_sha256="d" * 64,
            preparation_status=refreshed.status,
            mapped_count=refreshed.mapped_count,
            eligibility_status=refreshed.eligibility.status,
            span_days=refreshed.eligibility.span_days,
        )
        observed.append(evidence)
        return evidence

    def fake_dispatch(_config, *, prepare_current, observed_at, **_kwargs):
        prepare_current(observed_at)
        return SimpleNamespace(
            status="scheduled",
            reason="READY 15/15",
            record_path=tmp_path / "record.json",
            plan_id="plan",
            plan_path=None,
            launch_agent_path=None,
            launch_agent_label=None,
            activation_status="not_requested",
            attention_path=None,
            retry_plan_path=None,
            review_queue_path=None,
        )

    monkeypatch.setattr(cli, "_prepare_current_for_morning", fake_prepare)
    monkeypatch.setattr(cli, "dispatch_morning", fake_dispatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(observed) == 1
    assert observed[0].preparation_status == "ready"
    assert observed[0].eligibility_status == "playable"
    assert observed[0].span_days == 1
    engine.dispose()


def test_generated_attention_and_notification_refresh_without_stale_counts(
    tmp_path,
):
    config = _config(tmp_path)
    first_at = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)

    first = dispatch_morning(
        config,
        observed_at=first_at,
        now=lambda: first_at,
        prepare_current=lambda _now: _unresolved_count(5),
        python_command=sys.executable,
    )
    second = dispatch_morning(
        config,
        observed_at=first_at + timedelta(minutes=1),
        now=lambda: first_at + timedelta(minutes=1),
        prepare_current=lambda _now: _unresolved_count(2),
        python_command=sys.executable,
    )

    report = (second.attention_path.parent / "ACTION_REQUIRED.md").read_text()
    notify = (second.attention_path.parent / "notify.command").read_text()
    assert first.attention_path == second.attention_path
    assert "unresolved 2/15" in report
    assert "unresolved 5/15" not in report
    assert "unresolved 2/15" in notify
    assert "unresolved 5/15" not in notify
    attention = json.loads(second.attention_path.read_text())
    assert attention["status"] == "ACTION REQUIRED: unresolved 2/15"
    assert len(attention["unresolved"]) == 2


@pytest.mark.parametrize("artifact_name", ("ACTION_REQUIRED.md", "notify.command"))
@pytest.mark.parametrize("conflict_kind", ("foreign", "symlink"))
def test_generated_preflight_text_conflicts_still_fail_closed(
    tmp_path, artifact_name, conflict_kind
):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    first = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _unresolved_count(5),
        python_command=sys.executable,
    )
    artifact = first.attention_path.parent / artifact_name
    artifact.unlink()
    if conflict_kind == "foreign":
        artifact.write_text("foreign operator file\n")
    else:
        target = tmp_path / "foreign-target"
        target.write_text("foreign operator file\n")
        artifact.symlink_to(target)

    with pytest.raises(ValueError, match="text artifact conflicts"):
        dispatch_morning(
            config,
            observed_at=observed + timedelta(minutes=1),
            now=lambda: observed + timedelta(minutes=1),
            prepare_current=lambda _now: _unresolved_count(2),
            python_command=sys.executable,
        )


def test_4960_deferred_writes_attention_retry_and_reviewed_queue(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)

    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )

    assert result.status == "deferred"
    assert result.reason == "ACTION REQUIRED: unresolved 2/15"
    assert result.attention_path is not None
    attention = json.loads(result.attention_path.read_text(encoding="utf-8"))
    assert attention["status"] == "ACTION REQUIRED: unresolved 2/15"
    assert attention["identity"]["drawing_id"] == 11990
    assert attention["identity"]["drawing_number"] == 4960
    assert attention["identity"]["drawing_fingerprint"] == FINGERPRINT
    assert attention["attempts"] == 1
    assert [item["event_order"] for item in attention["unresolved"]] == [12, 14]
    assert attention["unresolved"][0]["required_evidence_type"] == "reviewed_alias"
    assert (
        attention["unresolved"][1]["required_evidence_type"]
        == "reviewed_schedule"
    )

    retry = json.loads(result.retry_plan_path.read_text(encoding="utf-8"))
    assert retry["passive"] is True
    assert retry["activate_evening"] is False
    assert retry["hard_stop"] == "2026-07-30T15:00:00Z"
    assert [item["scheduled_at"] for item in retry["attempts"]] == [
        "2026-07-30T10:00:00Z",
        "2026-07-30T12:00:00Z",
        "2026-07-30T13:00:00Z",
        "2026-07-30T14:00:00Z",
        "2026-07-30T14:30:00Z",
    ]
    for item in retry["attempts"]:
        command = item["command"]
        assert "--expected-drawing-id" in command
        assert "--expected-drawing-number" in command
        assert "--expected-fingerprint" in command
        assert "--expected-deadline" in command
        ledger_index = command.index("--schedule-evidence-ledger")
        assert command[ledger_index + 1] == str(config.schedule_evidence_ledger)
        assert "--activate" not in command

    queue = json.loads(result.review_queue_path.read_text(encoding="utf-8"))
    assert queue["schema_version"] == 1
    assert len(queue["records"]) == 1
    record = queue["records"][0]
    assert record["event_order"] == 14
    assert record["target_event_id"] == 178967
    assert record["source_fixture_id"] is None
    assert record["requirements"]["minimum_https_sources"] == 2
    assert record["template"]["claims"][0]["role"] == "official"
    assert record["template"]["claims"][1]["role"] == "independent"

    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))
    assert not tuple(tmp_path.rglob("package.csv"))
    assert not tuple(tmp_path.rglob(".bet-ready"))


def test_ready_baseline_only_without_kickoff_escalates_and_can_later_activate(
    tmp_path,
):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)

    unresolved = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _timing_unknown(),
        python_command=sys.executable,
    )

    assert unresolved.status == "deferred"
    assert unresolved.reason == "ACTION REQUIRED: timing unknown 2/15"
    attention = json.loads(unresolved.attention_path.read_text(encoding="utf-8"))
    assert attention["status"] == "ACTION REQUIRED: timing unknown 2/15"
    assert attention["activate_evening"] is True
    assert [item["event_order"] for item in attention["unresolved"]] == [7, 14]
    assert all(
        item["required_evidence_type"] == "reviewed_schedule"
        for item in attention["unresolved"]
    )
    retry = json.loads(unresolved.retry_plan_path.read_text(encoding="utf-8"))
    assert retry["activate_evening"] is True
    assert retry["attempts"]
    assert all("--activate" in item["command"] for item in retry["attempts"])
    queue = json.loads(unresolved.review_queue_path.read_text(encoding="utf-8"))
    assert [item["event_order"] for item in queue["records"]] == [7, 14]
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))

    ready_at = observed + timedelta(minutes=5)
    ready = dispatch_morning(
        config,
        observed_at=ready_at,
        now=lambda: ready_at,
        prepare_current=lambda _now: _ready(),
        python_command=sys.executable,
    )

    assert ready.status == "scheduled"
    assert ready.plan_path is not None and ready.plan_path.is_file()
    assert not unresolved.attention_path.exists()
    assert (unresolved.attention_path.parent / "RESOLVED.json").is_file()


def test_retry_artifacts_are_idempotent_and_attempts_are_append_only(tmp_path):
    config = _config(tmp_path)
    first_at = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    second_at = first_at + timedelta(minutes=20)

    first = dispatch_morning(
        config,
        observed_at=first_at,
        now=lambda: first_at,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )
    retry_before = first.retry_plan_path.read_bytes()
    second = dispatch_morning(
        config,
        observed_at=second_at,
        now=lambda: second_at,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )

    assert second.retry_plan_path.read_bytes() == retry_before
    attention = json.loads(second.attention_path.read_text(encoding="utf-8"))
    assert attention["attempts"] == 2
    attempts = tuple(second.attention_path.parent.glob("attempts/*.json"))
    reports = tuple(second.attention_path.parent.glob("attempts/*.md"))
    assert len(attempts) == 2
    assert len(reports) == 2


def test_expected_identity_rejects_drawing_or_fingerprint_drift(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    expected = MorningExpectedIdentity(
        drawing_id=11990,
        drawing_number=4960,
        deadline=DEADLINE,
        drawing_fingerprint="a" * 64,
    )

    with pytest.raises(ValueError, match="fingerprint drift"):
        dispatch_morning(
            config,
            observed_at=observed,
            now=lambda: observed,
            prepare_current=lambda _now: _unresolved(),
            expected_identity=expected,
            python_command=sys.executable,
        )

    assert not config.state_root.exists()


def test_attention_clears_only_when_same_fingerprint_is_ready(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    unresolved = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )
    attention = unresolved.attention_path
    assert attention.is_file()

    other = MorningPreparedDrawing(
        **{
            **_ready().__dict__,
            "drawing_fingerprint": "d" * 64,
        }
    )
    dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=5),
        now=lambda: observed + timedelta(minutes=5),
        prepare_current=lambda _now: other,
        python_command=sys.executable,
    )
    assert attention.is_file()

    dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=10),
        now=lambda: observed + timedelta(minutes=10),
        prepare_current=lambda _now: _ready(),
        python_command=sys.executable,
    )
    assert not attention.exists()
    assert (attention.parent / "RESOLVED.json").is_file()


def test_generic_morning_schedule_has_early_retry_and_remains_passive(tmp_path):
    config = _config(tmp_path)
    output = config.scheduler_root / "morning-dispatcher"

    artifacts = prepare_morning_preanalysis_artifacts(
        times=("08:00", "10:30", "12:00"),
        retry_count=0,
        retry_delay_seconds=0,
        output_dir=output,
        env_file=config.env_file,
        project_root=config.project_root,
        bank=config.bank,
        stake=config.stake,
        python_command=sys.executable,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert "--activate" not in wrapper
    assert "run-drawing" not in wrapper
    assert {"Hour": 12, "Minute": 0} in plist["StartCalendarInterval"]


def test_13_of_15_retry_plan_generates_verified_passive_launch_agent(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 7, 30, 7, 35, tzinfo=UTC)
    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _unresolved(),
        python_command=sys.executable,
    )

    artifacts = prepare_preflight_retry_artifacts(result.retry_plan_path)
    plist = plistlib.loads(artifacts.candidate_path.read_bytes())
    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")

    assert artifacts.label.startswith("com.totoai.preflight-retry.11990.")
    assert len(plist["StartCalendarInterval"]) == 6
    assert "preflight-retry-run" in wrapper
    assert "run-drawing" not in wrapper
    assert "--activate" not in wrapper
    assert ".bet-ready" not in wrapper
    installed = tmp_path / "Library" / "LaunchAgents" / (
        artifacts.label + ".plist"
    )
    installed.parent.mkdir(parents=True)
    installed.write_bytes(artifacts.candidate_path.read_bytes())
    status = verify_preflight_retry_launch_agent(
        artifacts, launch_agents_root=installed.parent,
        command_runner=lambda *a, **k: type("R", (), {"returncode": 0})(),
    )
    assert status["installed_verified"] is True
    assert status["loaded_verified"] is True
