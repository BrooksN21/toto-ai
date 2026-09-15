from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.external_odds.goal_api import GoalAPIClient
from toto_ai.sports_stats import goal_probe_collection
from toto_ai.sports_stats.goal_probe_collection import (
    collect_goal_probe_input,
    ensure_goal_probe_input,
)
from toto_ai.sports_stats.goal_probe_research import load_goal_probe_shadow

UTC = timezone.utc


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(url)
        if "/teams/" in url:
            team_id = url.split("/teams/", 1)[1].split("/", 1)[0]
            order = int(team_id.rsplit("-", 1)[1])
            side = "home" if "home" in team_id else "away"
            opponent = f"opponent-{order}-{side}"
            return FakeResponse(
                {
                    "success": True,
                    "teamId": team_id,
                    "data": [
                        {
                            "id": f"history-{team_id}",
                            "matchStatus": "FINISHED",
                            "kickoffUtc": "2026-08-20T16:00:00Z",
                            "homeTeamId": team_id if side == "home" else opponent,
                            "awayTeamId": opponent if side == "home" else team_id,
                            "homeTeamScore": "2",
                            "awayTeamScore": "1",
                        }
                    ],
                },
                headers={"X-RateLimit-Remaining": "900"},
            )
        requested_date = url.rsplit("/", 1)[-1]
        fixtures = []
        if requested_date == "2026-08-27":
            fixtures = [
                {
                    "id": f"fixture-{order}",
                    "homeTeamName": f"Home {order + 1}",
                    "awayTeamName": f"Away {order + 1}",
                    "homeTeamId": f"home-{order}",
                    "awayTeamId": f"away-{order}",
                    "kickoffUtc": f"2026-08-27T16:{order:02d}:00Z",
                    "leagueName": "Test League",
                    "matchStatus": "SCHEDULED",
                }
                for order in range(15)
            ]
        return FakeResponse(
            {
                "success": True,
                "data": fixtures,
                "pagination": {"hasMore": False},
            },
            headers={"X-RateLimit-Remaining": "950"},
        )


class PartialFakeSession(FakeSession):
    missing_orders = frozenset({3, 7, 8, 11, 14})

    def get(self, url, *, params, headers, timeout):
        response = super().get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if "/fixtures/date/" in url and isinstance(response.payload, dict):
            values = response.payload.get("data")
            if isinstance(values, list):
                response.payload["data"] = [
                    row
                    for row in values
                    if int(str(row["id"]).rsplit("-", 1)[1]) not in self.missing_orders
                ]
        return response


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_inputs(root: Path) -> Path:
    deadline = "2026-08-27T19:00:00Z"
    events = []
    records = []
    for order in range(15):
        event_id = 200000 + order
        events.append(
            {
                "id": event_id,
                "order": order,
                "name": f"Home {order + 1} — Away {order + 1}",
                "championship": "Test football",
                "start_at": None,
                "quotes": {
                    "bk_win_1": 40,
                    "bk_draw": 30,
                    "bk_win_2": 30,
                    "pool_win_1": 40,
                    "pool_draw": 30,
                    "pool_win_2": 30,
                },
                "result": None,
                "score": None,
            }
        )
        records.append(
            {
                "status": "awaiting_review",
                "drawing_id": 12071,
                "drawing_number": 4988,
                "target_fingerprint": "a" * 64,
                "event_order": order,
                "target_event_id": event_id,
                "home_team": f"Home {order + 1}",
                "away_team": f"Away {order + 1}",
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        )
    write_drawing_detail_cache(
        {
            "version": "test",
            "data": {
                "id": 12071,
                "number": 4988,
                "name": "baltbet-main",
                "ended_at": deadline,
                "status": "open",
                "pool_sum": 1000,
                "jackpot": 0,
                "payments": [],
                "events": events,
            },
        },
        drawing_id=12071,
        cache_dir=root / "data" / "raw",
        fetched_at=datetime(2026, 8, 27, 7, 30, tzinfo=UTC),
        source="test",
        allowed_root=root,
    )
    queue = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-27T07:30:00Z",
        "identity": {
            "drawing_id": 12071,
            "drawing_number": 4988,
            "drawing_fingerprint": "a" * 64,
            "deadline": deadline,
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": records,
    }
    queue["queue_sha256"] = hashlib.sha256(_canonical(queue)).hexdigest()
    queue_path = root / "queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    return queue_path


def test_collect_goal_probe_builds_adapter_compatible_15_event_input(
    tmp_path: Path,
) -> None:
    queue = _write_inputs(tmp_path)
    session = FakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    client = GoalAPIClient(
        "test-secret",
        session=session,
        snapshot_dir=(
            tmp_path / "reports" / "goal-full-probe" / "schedule" / "goal-api-v1"
        ),
        request_budget=120,
        now=lambda: observed,
    )

    result = collect_goal_probe_input(
        drawing_id=12071,
        queue_path=queue,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_dir=tmp_path / "reports" / "goal-full-probe",
        client=client,
        project_root=tmp_path,
        captured_at=observed,
    )

    assert result.event_count == 15
    assert result.history_source_count == 30
    assert result.sports_eligible_count == 15
    assert result.request_count == 36
    coverage = json.loads(result.coverage_summary_path.read_text(encoding="utf-8"))
    assert len(coverage["events"]) == 15
    assert all(len(row["sources"]) == 2 for row in coverage["events"])
    frozen = "\n".join(
        path.read_text(encoding="utf-8")
        for path in result.coverage_summary_path.parent.glob("*.json")
    )
    assert "test-secret" not in frozen

    bundle = load_goal_probe_shadow(
        drawing_id=12071,
        as_of=result.captured_at,
        raw_cache_dir=tmp_path / "data" / "raw",
        coverage_summary_path=result.coverage_summary_path,
        project_root=tmp_path,
    )

    assert bundle.shadow.sports_coverage_count == 15
    assert bundle.shadow.fallback_count == 0


def test_collect_goal_probe_keeps_15_events_with_explicit_bk_fallback(
    tmp_path: Path,
) -> None:
    queue = _write_inputs(tmp_path)
    session = PartialFakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    client = GoalAPIClient(
        "test-secret",
        session=session,
        snapshot_dir=(
            tmp_path / "reports" / "goal-partial-probe" / "schedule" / "goal-api-v1"
        ),
        request_budget=120,
        now=lambda: observed,
    )

    result = collect_goal_probe_input(
        drawing_id=12071,
        queue_path=queue,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_dir=tmp_path / "reports" / "goal-partial-probe",
        client=client,
        project_root=tmp_path,
        captured_at=observed,
    )

    assert result.event_count == 15
    assert result.sports_eligible_count == 10
    assert result.history_source_count == 20
    coverage = json.loads(result.coverage_summary_path.read_text(encoding="utf-8"))
    assert len(coverage["events"]) == 15
    fallback = [row for row in coverage["events"] if not row["sports_eligible"]]
    assert [row["event_order"] for row in fallback] == [3, 7, 8, 11, 14]
    assert all(row["fallback_reason"] == "target_fixture_missing" for row in fallback)
    assert all(row["sources"] == [] for row in fallback)

    bundle = load_goal_probe_shadow(
        drawing_id=12071,
        as_of=result.captured_at,
        raw_cache_dir=tmp_path / "data" / "raw",
        coverage_summary_path=result.coverage_summary_path,
        project_root=tmp_path,
    )

    assert bundle.shadow.sports_coverage_count == 10
    assert bundle.shadow.fallback_count == 5
    assert [
        row.event_order
        for row in bundle.shadow.events
        if row.probability_source == "totobrief_bk_fallback"
    ] == [3, 7, 8, 11, 14]


def test_ensure_goal_probe_generates_full_queue_and_reuses_current_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)
    session = FakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    real_client = GoalAPIClient

    def client_factory(api_key, *, snapshot_dir, request_budget):
        return real_client(
            api_key,
            session=session,
            snapshot_dir=snapshot_dir,
            request_budget=request_budget,
            now=lambda: observed,
        )

    monkeypatch.setattr(goal_probe_collection, "GoalAPIClient", client_factory)
    output = tmp_path / "reports" / "sports-analytics" / "4988" / "goal-auto"
    first = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )
    calls_after_first = len(session.calls)
    second = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )

    assert first.reused is False
    assert second.reused is True
    assert calls_after_first == 36
    assert len(session.calls) == calls_after_first
    marker = json.loads((output / "current.json").read_text(encoding="utf-8"))
    assert marker["package_influence"] == "NONE"
    assert marker["automatic_wagering"] is False
    queue_paths = tuple((output / "captures").glob("*/goal-shadow-queue.json"))
    assert len(queue_paths) == 1
    queue = json.loads(queue_paths[0].read_text(encoding="utf-8"))
    assert len(queue["records"]) == 15
    assert "test-secret" not in (output / "current.json").read_text(encoding="utf-8")


def _cache_fixture(root, *, failed=True, eligible=0, exhausted=False, quota=900):
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    output = root / "reports" / "goal-auto"
    result = _cache_capture(
        root,
        output / "captures" / "original",
        observed,
        failed=failed,
        eligible=eligible,
        exhausted=exhausted,
        quota=quota,
    )
    marker = {
        "schema_version": 1,
        "status": "PAPER_ONLY_COVERAGE_PROBE_READY",
        "drawing_id": 12071,
        "captured_at": observed.isoformat(),
        "event_count": 15,
        "sports_eligible_count": eligible,
        "history_source_count": eligible * 2,
        "request_count": 7,
        "quota_daily_remaining": quota,
        "package_influence": "NONE",
        "automatic_wagering": False,
    }
    for name, path in (
        ("coverage_summary", result.coverage_summary_path),
        ("schedule_report", result.schedule_report_path),
    ):
        marker[name + "_path"] = path.relative_to(root).as_posix()
        marker[name + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "current.json").write_text(json.dumps(marker))
    return output


def _cache_capture(
    root, output, observed, *, failed=False, eligible=15, exhausted=False, quota=900
):
    output.mkdir(parents=True, exist_ok=True)
    coverage = output / "coverage-summary.json"
    report = output / "schedule-source-candidates.json"
    coverage.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PAPER_ONLY_COVERAGE_PROBE",
                "drawing_id": 12071,
                "event_count": 15,
                "sports_eligible_count": eligible,
                "history_source_count": eligible * 2,
                "captured_at": observed.isoformat(),
                "events": [],
            }
        )
    )
    report.write_text(
        json.dumps(
            {
                "providers": {
                    "goal-api-v1": {
                        "status": "source_failed" if failed else "collected",
                        "budget_exhausted": exhausted,
                    }
                },
                "records": [],
            }
        )
    )
    return goal_probe_collection.GoalProbeCollection(
        coverage,
        report,
        observed,
        15,
        eligible * 2,
        eligible,
        7,
        quota,
    )


def _cache_refresh_stub(monkeypatch, root, *, mode="success"):
    calls = []

    def client_factory(api_key, *, snapshot_dir, request_budget):
        return {"request_budget": request_budget}

    def collect(**kwargs):
        calls.append(kwargs)
        if mode == "exception":
            raise ValueError("synthetic request budget exhausted")
        return _cache_capture(
            root,
            kwargs["output_dir"],
            kwargs["captured_at"],
            failed=mode != "success",
            eligible=15 if mode == "success" else 0,
            exhausted=mode == "budget",
        )

    monkeypatch.setattr(goal_probe_collection, "GoalAPIClient", client_factory)
    monkeypatch.setattr(goal_probe_collection, "collect_goal_probe_input", collect)
    return calls


def _ensure_cached(root, output, minute=15, *, request_budget=120):
    return ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=root / "data" / "raw",
        output_root=output,
        api_key="synthetic-key",
        project_root=root,
        captured_at=datetime(2026, 8, 27, 8, minute, tzinfo=UTC),
        request_budget=request_budget,
    )


def test_failed_cache_gets_one_allowed_fresh_capture_without_overwriting_old(
    monkeypatch,
    tmp_path,
):
    output = _cache_fixture(tmp_path)
    original = {p: p.read_bytes() for p in output.rglob("*.json")}
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    fresh = _ensure_cached(tmp_path, output)
    reused = _ensure_cached(tmp_path, output, 31)
    assert len(calls) == 1
    assert calls[0]["client"]["request_budget"] == 120
    assert fresh.sports_eligible_count == 15 and not fresh.reused
    assert reused.reused and reused.coverage_summary_path == fresh.coverage_summary_path
    assert fresh.captured_at == datetime(2026, 8, 27, 8, 15, tzinfo=UTC)
    assert all(p.read_bytes() == content for p, content in original.items())


def test_failed_cache_cooldown_then_one_allowed_capture(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="cooldown"):
        _ensure_cached(tmp_path, output, 14)
    assert calls == []
    assert _ensure_cached(tmp_path, output, 15).sports_eligible_count == 15
    assert len(calls) == 1


@pytest.mark.parametrize("eligible", [0, 10, 15])
def test_valid_cache_including_no_matches_is_not_blindly_refreshed(
    monkeypatch,
    tmp_path,
    eligible,
):
    output = _cache_fixture(tmp_path, failed=False, eligible=eligible)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    reused = _ensure_cached(tmp_path, output, 45)
    assert reused.reused and reused.sports_eligible_count == eligible
    assert calls == []


@pytest.mark.parametrize("mode", ["source_failed", "exception"])
def test_failed_retry_recovers_after_latest_cooldown_without_erasing_evidence(
    monkeypatch,
    tmp_path,
    mode,
):
    output = _cache_fixture(tmp_path)
    before = (output / "current.json").read_bytes()
    calls = _cache_refresh_stub(monkeypatch, tmp_path, mode=mode)
    with pytest.raises(ValueError):
        _ensure_cached(tmp_path, output, request_budget=3)
    evidence = {p: p.read_bytes() for p in output.rglob("*.json")}
    with pytest.raises(ValueError, match="cooldown") as blocked:
        _ensure_cached(tmp_path, output, 29, request_budget=3)
    assert blocked.value.retryable
    assert blocked.value.next_retry_at == datetime(2026, 8, 27, 8, 30, tzinfo=UTC)
    assert len(calls) == 1
    recovered_calls = _cache_refresh_stub(monkeypatch, tmp_path)
    recovered = _ensure_cached(tmp_path, output, 30, request_budget=3)
    assert len(recovered_calls) == 1 and not recovered.reused
    assert recovered.captured_at == datetime(2026, 8, 27, 8, 30, tzinfo=UTC)
    assert all(p.read_bytes() == content for p, content in evidence.items())
    assert (output / "current.json").read_bytes() == before


@pytest.mark.parametrize("exhausted,quota", [(True, 900), (False, 0)])
def test_failed_cache_does_not_reset_exhausted_source_budget(
    monkeypatch,
    tmp_path,
    exhausted,
    quota,
):
    output = _cache_fixture(tmp_path, exhausted=exhausted, quota=quota)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="budget|quota"):
        _ensure_cached(tmp_path, output, 45)
    assert calls == []


def test_failed_cache_integrity_error_never_causes_refresh(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    (output / "captures" / "original" / "coverage-summary.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        _ensure_cached(tmp_path, output)
    assert calls == []


def test_first_failed_capture_is_retained_but_not_returned_as_ready(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "reports" / "goal-auto"
    calls = _cache_refresh_stub(monkeypatch, tmp_path, mode="source_failed")
    with pytest.raises(ValueError, match="source failed"):
        _ensure_cached(tmp_path, output, 0)
    assert len(calls) == 1
    assert (output / "current.json").is_file()
    with pytest.raises(ValueError, match="cooldown"):
        _ensure_cached(tmp_path, output, 14)
    assert len(calls) == 1


def test_failed_cache_invalid_retry_budget_does_not_spend_claim(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="request_budget"):
        _ensure_cached(tmp_path, output, request_budget=0)
    assert calls == []
    assert _ensure_cached(tmp_path, output).sports_eligible_count == 15
    assert len(calls) == 1


def test_failed_cache_retry_claim_blocks_reentrant_collection(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    collect = goal_probe_collection.collect_goal_probe_input

    def reentrant(**kwargs):
        with pytest.raises(ValueError, match="already claimed"):
            _ensure_cached(tmp_path, output, 16)
        return collect(**kwargs)

    monkeypatch.setattr(goal_probe_collection, "collect_goal_probe_input", reentrant)
    assert _ensure_cached(tmp_path, output).sports_eligible_count == 15
    assert len(calls) == 1


def test_failed_cache_retry_marker_is_bound_to_original(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    _ensure_cached(tmp_path, output)
    marker_path = next(
        (output / "failed-cache-retry").glob("*/attempts/*/current.json")
    )
    marker = json.loads(marker_path.read_text())
    marker["retry_of_sha256"] = "f" * 64
    marker_path.write_text(json.dumps(marker))
    with pytest.raises(ValueError, match="retry marker binding mismatch"):
        _ensure_cached(tmp_path, output, 31)
    assert len(calls) == 1


def test_crashed_attempt_lease_blocks_then_recovers(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    _cache_refresh_stub(monkeypatch, tmp_path)

    def crash(**kwargs):
        raise KeyboardInterrupt("synthetic process death")

    monkeypatch.setattr(goal_probe_collection, "collect_goal_probe_input", crash)
    with pytest.raises(KeyboardInterrupt):
        _ensure_cached(tmp_path, output, request_budget=3)
    claim = next((output / "failed-cache-retry").glob("*/attempts/*/attempt.json"))
    original_claim = claim.read_bytes()
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="cooldown"):
        _ensure_cached(tmp_path, output, 29, request_budget=3)
    assert calls == []
    assert (
        _ensure_cached(tmp_path, output, 30, request_budget=3).sports_eligible_count
        == 15
    )
    assert len(calls) == 1 and claim.read_bytes() == original_claim
    expired = json.loads((claim.parent / "expired.json").read_text())
    assert expired["status"] == "LEASE_EXPIRED"
    assert expired["reserved_requests"] == 3


def test_retry_window_spends_crashed_full_reservation_then_recovers(
    monkeypatch, tmp_path
):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path, mode="exception")
    with pytest.raises(ValueError):
        _ensure_cached(tmp_path, output, request_budget=120)
    with pytest.raises(ValueError, match="window budget") as blocked:
        _ensure_cached(tmp_path, output, 45, request_budget=1)
    assert len(calls) == 1 and blocked.value.retryable
    assert blocked.value.next_retry_at == datetime(2026, 8, 27, 9, 15, tzinfo=UTC)
    recovered_calls = _cache_refresh_stub(monkeypatch, tmp_path)
    result = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data/raw",
        output_root=output,
        api_key="synthetic",
        request_budget=120,
        project_root=tmp_path,
        captured_at=datetime(2026, 8, 27, 9, 15, tzinfo=UTC),
    )
    assert len(recovered_calls) == 1 and not result.reused


def test_quota_reservations_survive_unknown_interrupted_requests(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path, quota=5)
    calls = _cache_refresh_stub(monkeypatch, tmp_path, mode="exception")
    with pytest.raises(ValueError):
        _ensure_cached(tmp_path, output, request_budget=3)
    with pytest.raises(ValueError, match="quota") as blocked:
        _ensure_cached(tmp_path, output, 45, request_budget=3)
    assert len(calls) == 1
    status = goal_probe_collection.goal_probe_failure_status(blocked.value)
    assert status["retryable"] is False and status["next_retry_at"] is None


def test_failed_retry_budget_exhaustion_is_truthfully_terminal(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path, mode="budget")
    with pytest.raises(ValueError, match="budget") as first:
        _ensure_cached(tmp_path, output, request_budget=3)
    assert not first.value.retryable
    with pytest.raises(ValueError, match="budget") as later:
        _ensure_cached(tmp_path, output, 45, request_budget=3)
    assert not later.value.retryable and len(calls) == 1
    outcome = next((output / "failed-cache-retry").glob("*/attempts/*/outcome.json"))
    assert json.loads(outcome.read_text())["retryable"] is False


def test_active_lock_excludes_even_expired_lease(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    collect = goal_probe_collection.collect_goal_probe_input

    def overlapping(**kwargs):
        with pytest.raises(ValueError, match="already claimed"):
            _ensure_cached(tmp_path, output, 45, request_budget=3)
        return collect(**kwargs)

    monkeypatch.setattr(goal_probe_collection, "collect_goal_probe_input", overlapping)
    assert (
        _ensure_cached(tmp_path, output, request_budget=3).sports_eligible_count == 15
    )
    assert len(calls) == 1


def test_failure_status_and_cli_wiring_are_truthful():
    import ast

    error = goal_probe_collection.GoalProbeCacheError(
        "retry cooldown active",
        next_retry_at=datetime(2026, 8, 27, 8, 30, tzinfo=UTC),
    )
    assert goal_probe_collection.goal_probe_failure_status(error) == {
        "retryable": True,
        "retry_reason": "retry cooldown active",
        "next_retry_at": "2026-08-27T08:30:00Z",
    }
    assert not goal_probe_collection.goal_probe_failure_status(
        ValueError("hash mismatch")
    )["retryable"]
    cli_path = Path(goal_probe_collection.__file__).parents[1] / "cli.py"
    tree = ast.parse(cli_path.read_text())
    status_dicts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(
            isinstance(value, ast.Constant)
            and value.value == "PAPER_ONLY_COLLECTION_FAILED"
            for value in node.values
        )
    ]
    assert len(status_dicts) == 1
    status_dict = status_dicts[0]
    assert any(
        key is None
        and isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "goal_probe_failure_status"
        for key, value in zip(status_dict.keys, status_dict.values, strict=True)
    )
    for key, value in zip(status_dict.keys, status_dict.values, strict=True):
        if isinstance(key, ast.Constant) and key.value in {
            "automatic_wagering",
            "primary_scheduler_affected",
        }:
            assert isinstance(value, ast.Constant) and value.value is False


def test_concurrent_callers_have_one_collector(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    output = _cache_fixture(tmp_path)
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    collect = goal_probe_collection.collect_goal_probe_input
    entered, release = Event(), Event()

    def blocking_collect(**kwargs):
        entered.set()
        assert release.wait(2)
        return collect(**kwargs)

    monkeypatch.setattr(
        goal_probe_collection, "collect_goal_probe_input", blocking_collect
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_ensure_cached, tmp_path, output, request_budget=3)
        try:
            assert entered.wait(2)
            with pytest.raises(ValueError, match="already claimed"):
                _ensure_cached(tmp_path, output, 45, request_budget=3)
        finally:
            release.set()
        assert future.result(timeout=2).sports_eligible_count == 15
    assert len(calls) == 1


def test_deadline_failure_stays_terminal_after_cooldown(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    calls = []
    _cache_refresh_stub(monkeypatch, tmp_path)

    def expired(**kwargs):
        calls.append(kwargs)
        raise ValueError("GOAL probe collection must finish before drawing deadline")

    monkeypatch.setattr(goal_probe_collection, "collect_goal_probe_input", expired)
    for minute in (15, 45):
        with pytest.raises(
            goal_probe_collection.GoalProbeCacheError, match="deadline"
        ) as error:
            _ensure_cached(tmp_path, output, minute, request_budget=3)
        assert not error.value.retryable
    assert len(calls) == 1


def test_ensure_goal_probe_reuses_partial_marker_with_bk_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)
    session = PartialFakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    real_client = GoalAPIClient

    def client_factory(api_key, *, snapshot_dir, request_budget):
        return real_client(
            api_key,
            session=session,
            snapshot_dir=snapshot_dir,
            request_budget=request_budget,
            now=lambda: observed,
        )

    monkeypatch.setattr(goal_probe_collection, "GoalAPIClient", client_factory)
    output = tmp_path / "reports" / "sports-analytics" / "4988" / "goal-auto"
    first = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )
    calls_after_first = len(session.calls)
    second = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )

    assert first.sports_eligible_count == 10
    assert first.history_source_count == 20
    assert second.reused is True
    assert second.sports_eligible_count == 10
    assert second.history_source_count == 20
    assert len(session.calls) == calls_after_first


@pytest.mark.parametrize("interrupted_file", ["attempt.json", "outcome.json"])
def test_interrupted_metadata_publication_can_recover(
    monkeypatch, tmp_path, interrupted_file,
):
    output = _cache_fixture(tmp_path)
    _cache_refresh_stub(monkeypatch, tmp_path, mode="exception")
    real_open = Path.open
    interrupted = False

    def crash_open(path, mode="r", *args, **kwargs):
        nonlocal interrupted
        stream = real_open(path, mode, *args, **kwargs)
        target = path.name == interrupted_file or path.name.startswith(
            "." + interrupted_file + "."
        )
        if not interrupted and target and mode in {"xb", "wb"}:
            interrupted = True
            stream.close()
            raise KeyboardInterrupt("crash after create before write")
        return stream

    with monkeypatch.context() as crash:
        crash.setattr(Path, "open", crash_open)
        with pytest.raises(KeyboardInterrupt):
            _ensure_cached(tmp_path, output, 15, request_budget=3)
    assert interrupted
    calls = _cache_refresh_stub(monkeypatch, tmp_path)
    result = _ensure_cached(tmp_path, output, 45, request_budget=3)
    assert len(calls) == 1 and not result.reused
    status = goal_probe_collection.goal_probe_failure_status(ValueError("integrity"))
    assert status["retryable"] is False
def test_retry_directory_sync_order_before_collection(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    _cache_refresh_stub(monkeypatch, tmp_path)
    original_collect = goal_probe_collection._capture_goal_probe_input
    original_open = goal_probe_collection.os.open
    original_close = goal_probe_collection.os.close
    original_sync = goal_probe_collection.os.fsync
    original_link = goal_probe_collection.os.link
    descriptors = {}
    calls = []

    def open_directory(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        descriptors[fd] = Path(path)
        return fd

    def close_directory(fd):
        descriptors.pop(fd, None)
        return original_close(fd)

    def sync(fd):
        calls.append(("dir", descriptors[fd]) if fd in descriptors else ("file", None))
        return original_sync(fd)

    def link(src, dst):
        calls.append(("link", Path(dst)))
        return original_link(src, dst)

    def collect(**kwargs):
        calls.append(("collector", None))
        return original_collect(**kwargs)

    monkeypatch.setattr(goal_probe_collection.os, "open", open_directory)
    monkeypatch.setattr(goal_probe_collection.os, "close", close_directory)
    monkeypatch.setattr(goal_probe_collection.os, "fsync", sync)
    monkeypatch.setattr(goal_probe_collection.os, "link", link)
    monkeypatch.setattr(goal_probe_collection, "_capture_goal_probe_input", collect)
    _ensure_cached(tmp_path, output, 15, request_budget=3)
    marker = calls.index(("collector", None))
    claim = next(path for kind, path in calls if kind == "link")
    expected_dirs = []
    directory = claim.parent
    while True:
        expected_dirs.append(("dir", directory))
        if directory == output:
            break
        directory = directory.parent
    assert calls[:marker] == [("file", None), ("link", claim), *expected_dirs]
    assert calls[marker + 1 :] == [
        ("file", None),
        ("link", claim.parent / "outcome.json"),
        *expected_dirs,
    ]


@pytest.mark.parametrize("failure_phase", ["attempt.json", "outcome.json"])
def test_directory_sync_error_does_not_acknowledge(
    monkeypatch, tmp_path, failure_phase
):
    import stat

    output = _cache_fixture(tmp_path)
    collections = _cache_refresh_stub(monkeypatch, tmp_path)
    original_sync = goal_probe_collection.os.fsync
    original_link = goal_probe_collection.os.link
    phase = None

    def link(src, dst):
        nonlocal phase
        phase = Path(dst).name
        return original_link(src, dst)

    def sync(fd):
        if phase == failure_phase and stat.S_ISDIR(
            goal_probe_collection.os.fstat(fd).st_mode
        ):
            raise OSError("injected directory fsync failure")
        return original_sync(fd)

    monkeypatch.setattr(goal_probe_collection.os, "link", link)
    monkeypatch.setattr(goal_probe_collection.os, "fsync", sync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        _ensure_cached(tmp_path, output, 15, request_budget=3)
    assert len(collections) == (0 if failure_phase == "attempt.json" else 1)
    claims = list(output.glob("failed-cache-retry/*/attempts/*/attempt.json"))
    assert len(claims) == 1
    assert json.loads(claims[0].read_text())["request_budget"] == 3
