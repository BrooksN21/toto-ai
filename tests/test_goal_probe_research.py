from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.sports_stats import goal_probe_research
from toto_ai.sports_stats.goal_probe_research import (
    ARTIFACT_CLASS,
    load_goal_probe_shadow,
    run_goal_probe_package_comparison,
)

_AS_OF = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 8, 26, 18, 45, tzinfo=timezone.utc)
_SECRET = "NEVER-LEAK-THIS-GOAL-KEY"


def test_goal_probe_validates_binding_and_maps_all_terminal_statuses(tmp_path):
    paths = _write_probe(tmp_path / "valid", terminal_variants=True)

    bundle = _load(paths)

    assert bundle.shadow.sports_coverage_count == 15
    assert bundle.shadow.fallback_count == 0
    assert tuple(event.event_order for event in bundle.shadow.events) == tuple(
        range(15)
    )
    assert bundle.analytics[0]["home_history"]["accepted_status_counts"] == {
        "AFTER_ET": 1
    }
    assert bundle.analytics[0]["away_history"]["accepted_status_counts"] == {
        "AFTER_PEN": 1
    }
    assert bundle.analytics[0]["orientation"] == "same"


def test_goal_probe_rejects_order_and_orientation_drift(tmp_path):
    order_paths = _write_probe(tmp_path / "order")
    coverage = _read_json(order_paths.coverage)
    coverage["events"][1]["event_order"] = 0
    _write_json(order_paths.coverage, coverage)

    with pytest.raises(ValueError, match="15 ordered events"):
        _load(order_paths)

    orientation_paths = _write_probe(tmp_path / "orientation")
    schedule = _read_json(orientation_paths.schedule)
    schedule["records"][4]["orientation"] = "reversed"
    _seal_schedule(schedule)
    _write_json(orientation_paths.schedule, schedule)

    with pytest.raises(ValueError, match="schedule orientation mismatch"):
        _load(orientation_paths)


def test_goal_probe_filters_history_strictly_before_as_of(tmp_path):
    paths = _write_probe(tmp_path / "future", at_as_of_order=0)

    bundle = _load(paths)

    event = bundle.shadow.events[0]
    assert bundle.shadow.sports_coverage_count == 14
    assert event.probability_source == "totobrief_bk_fallback"
    assert event.fallback_reason == "sports_history_missing"
    assert (
        bundle.analytics[0]["home_history"]["excluded_counts"][
            "at_or_after_as_of"
        ]
        == 1
    )
    assert bundle.analytics[0]["home_history"]["accepted_count"] == 0


def test_goal_probe_no_coverage_falls_back_to_bk(tmp_path):
    paths = _write_probe(tmp_path / "empty", empty_order=3)

    bundle = _load(paths)

    event = bundle.shadow.events[3]
    assert bundle.shadow.sports_coverage_count == 14
    assert bundle.shadow.fallback_count == 1
    assert event.sports_probabilities == event.bk_probabilities
    assert event.candidate_blend_probabilities == event.bk_probabilities
    assert event.fallback_reason == "sports_history_missing"


def test_research_reports_are_equal_budget_secret_safe_and_scheduler_isolated(
    tmp_path,
    monkeypatch,
):
    paths = _write_probe(tmp_path / "reports", include_secret=True)
    scheduler = paths.root / "reports" / "rehearsal" / "evening-4987"
    scheduler.mkdir(parents=True)
    protected = {
        scheduler / "scheduler-plan.json": b'{"sentinel":"plan"}\n',
        scheduler / "operator-result.json": b'{"sentinel":"operator"}\n',
        scheduler / ".bet-ready": b"sentinel\n",
    }
    for path, payload in protected.items():
        path.write_bytes(payload)

    coupons = tuple(_coupon(index) for index in range(166))

    def fake_package(_ev_input, _config):
        return SimpleNamespace(
            coupons=tuple(SimpleNamespace(coupon=coupon) for coupon in coupons),
            cost=4_980,
            unused_bank=0,
            expected_payout=0.0,
            modeled_roi=0.0,
        )

    monkeypatch.setattr(goal_probe_research, "_package", fake_package)
    monkeypatch.setattr(
        goal_probe_research,
        "package_quality_metrics",
        lambda *_args, **_kwargs: _Quality(),
    )
    output = paths.root / "reports" / "research" / "dual-package"

    report, report_paths = run_goal_probe_package_comparison(
        drawing_id=12068,
        bank=4_980,
        stake=30,
        as_of=_AS_OF,
        raw_cache_dir=paths.raw,
        coverage_summary_path=paths.coverage,
        output_dir=output,
        project_root=paths.root,
        monte_carlo_samples=1,
    )

    assert report["status"] == "PAPER_ONLY_NOT_ACTIVATED"
    assert report["coupon_limit"] == 166
    assert report["baseline"]["coupon_count"] == 166
    assert report["sports_candidate"]["coupon_count"] == 166
    assert report["baseline"]["cost"] == 4_980
    assert report["sports_candidate"]["cost"] == 4_980
    for path in (report_paths.baseline_csv, report_paths.sports_csv):
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 166
        assert len({row["coupon_compact"] for row in rows}) == 166
        assert {row["artifact_class"] for row in rows} == {ARTIFACT_CLASS}
        assert {row["operator_compatible"] for row in rows} == {"false"}
    upload_pattern = re.compile(r"^30(?:; [1X2]){15}$")
    for path in (report_paths.baseline_txt, report_paths.sports_txt):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert "RESEARCH ONLY" in lines[0]
        assert "NOT A BALTBet UPLOAD FILE" in lines[1]
        assert not any(upload_pattern.fullmatch(line) for line in lines)
    for artifact in output.iterdir():
        if artifact.is_file():
            assert _SECRET not in artifact.read_text(encoding="utf-8")
    manifest = _read_json(report_paths.manifest)
    assert manifest["safety"]["operator_compatible"] is False
    assert manifest["safety"]["scheduler_paths_written"] == []
    assert manifest["safety"]["live_provider_requests_made"] == 0
    for path, payload in protected.items():
        assert path.read_bytes() == payload

    with pytest.raises(ValueError, match="inside reports/research"):
        run_goal_probe_package_comparison(
            drawing_id=12068,
            bank=4_980,
            stake=30,
            as_of=_AS_OF,
            raw_cache_dir=paths.raw,
            coverage_summary_path=paths.coverage,
            output_dir=scheduler,
            project_root=paths.root,
            monte_carlo_samples=1,
        )


@dataclass(frozen=True)
class _Paths:
    root: Path
    raw: Path
    coverage: Path
    schedule: Path


@dataclass(frozen=True)
class _Quality:
    probability_at_least_13: float = 0.0
    probability_at_least_14: float = 0.0
    probability_at_least_15: float = 0.0


def _write_probe(
    root: Path,
    *,
    terminal_variants: bool = False,
    at_as_of_order: int | None = None,
    empty_order: int | None = None,
    include_secret: bool = False,
) -> _Paths:
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    probe = root / "reports" / "sports-analytics" / "4987" / "goal-full-probe"
    probe.mkdir(parents=True)
    schedule_dir = root / "reports" / "canary" / "goal-api-4987"
    schedule_dir.mkdir(parents=True)
    schedule_path = schedule_dir / "schedule-source-candidates.json"
    coverage_path = probe / "coverage-summary.json"

    events = []
    coverage_events = []
    schedule_records = []
    for order in range(15):
        event_id = 180123 + order
        home_name = f"Home {order + 1}"
        away_name = f"Away {order + 1}"
        fixture_id = f"target-fixture-{order}"
        home_id = f"home-team-{order}"
        away_id = f"away-team-{order}"
        target_start = datetime(2026, 8, 26, 16, order, tzinfo=timezone.utc)
        events.append(
            {
                "id": event_id,
                "order": order,
                "name": f"{home_name} — {away_name}",
                "name_en": None,
                "championship": "Test football",
                "start_at": None,
                "quotes": {
                    "bk_win_1": 40,
                    "bk_draw": 30,
                    "bk_win_2": 30,
                    "pool_win_1": 38,
                    "pool_draw": 32,
                    "pool_win_2": 30,
                },
                "result": None,
                "score": None,
            }
        )
        sources = []
        for side, team_id in (("home", home_id), ("away", away_id)):
            snapshot_path = probe / f"event-{order:02d}-{side}.json"
            if empty_order == order:
                rows = []
            else:
                kickoff = (
                    _AS_OF
                    if at_as_of_order == order and side == "home"
                    else _AS_OF - timedelta(days=order + 1)
                )
                status = "FINISHED"
                if terminal_variants and order == 0:
                    status = "AFTER_ET" if side == "home" else "AFTER_PEN"
                rows = [
                    {
                        "id": f"history-{order}-{side}",
                        "matchStatus": status,
                        "kickoffUtc": _iso(kickoff),
                        "homeTeamId": (
                            home_id if side == "home" else f"opponent-{order}"
                        ),
                        "awayTeamId": (
                            f"opponent-{order}" if side == "home" else away_id
                        ),
                        "homeTeamScore": "2" if side == "home" else "1",
                        "awayTeamScore": "0",
                    }
                ]
            snapshot = {
                "schema_version": 1,
                "provider": "goal-api-v1",
                "endpoint": f"/teams/{team_id}/results",
                "fetched_at": _iso(_AS_OF - timedelta(minutes=30)),
                "http_status": 200,
                "params": {"limit": 10},
                "payload": {
                    "success": True,
                    "teamId": team_id,
                    "data": rows,
                },
            }
            if include_secret:
                snapshot["apiKey"] = _SECRET
            _write_json(snapshot_path, snapshot)
            sources.append(
                {
                    "side": side,
                    "success": True,
                    "http_status": 200,
                    "history_count": len(rows),
                    "venue_count": len(rows),
                    "snapshot_path": snapshot_path.relative_to(root).as_posix(),
                }
            )
        coverage_events.append(
            {
                "event_order": order,
                "event_number": order + 1,
                "target_event_id": event_id,
                "home_team": home_name,
                "away_team": away_name,
                "provider_fixture_id": fixture_id,
                "provider_home_team_id": home_id,
                "provider_away_team_id": away_id,
                "target_starts_at": _iso(target_start),
                "sports_eligible": True,
                "sources": sources,
            }
        )
        schedule_records.append(
            {
                "event_order": order,
                "target_event_id": event_id,
                "target_home_team": home_name,
                "target_away_team": away_name,
                "orientation": "same",
                "source_provider": "goal-api-v1",
                "source_event_id": fixture_id,
                "source_home_team_id": home_id,
                "source_away_team_id": away_id,
                "starts_at": _iso(target_start),
                "source_status": "scheduled",
                "ledger_eligible": False,
            }
        )

    payload = {
        "version": "test",
        "data": {
            "id": 12068,
            "number": 4987,
            "name": "baltbet-main",
            "ended_at": _iso(_DEADLINE),
            "status": "open",
            "pool_sum": 100_000,
            "jackpot": 0,
            "payments": [],
            "events": events,
        },
    }
    write_drawing_detail_cache(
        payload,
        drawing_id=12068,
        cache_dir=raw,
        fetched_at=_AS_OF,
        source="test-frozen",
        allowed_root=root,
    )
    schedule = {
        "schema_version": 2,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "drawing_id": 12068,
        "drawing_number": 4987,
        "captured_at": _iso(_AS_OF - timedelta(hours=1)),
        "ledger_mutated": False,
        "records": schedule_records,
    }
    _seal_schedule(schedule)
    _write_json(schedule_path, schedule)
    coverage = {
        "schema_version": 1,
        "status": "PAPER_ONLY_COVERAGE_PROBE",
        "captured_at": _iso(_AS_OF - timedelta(minutes=45)),
        "drawing_id": 12068,
        "drawing_number": 4987,
        "event_count": 15,
        "sports_eligible_count": 15,
        "package_influence": "NONE",
        "automatic_wagering": False,
        "source_schedule_report": schedule_path.relative_to(root).as_posix(),
        "events": coverage_events,
    }
    _write_json(coverage_path, coverage)
    return _Paths(
        root=root,
        raw=raw,
        coverage=coverage_path,
        schedule=schedule_path,
    )


def _load(paths: _Paths):
    return load_goal_probe_shadow(
        drawing_id=12068,
        as_of=_AS_OF,
        raw_cache_dir=paths.raw,
        coverage_summary_path=paths.coverage,
        project_root=paths.root,
    )


def _seal_schedule(payload: dict[str, object]) -> None:
    payload.pop("report_sha256", None)
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _coupon(value: int) -> str:
    outcomes = "1X2"
    digits = []
    for _ in range(15):
        value, remainder = divmod(value, 3)
        digits.append(outcomes[remainder])
    return "".join(reversed(digits))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
