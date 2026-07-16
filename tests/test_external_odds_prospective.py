from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from toto_ai.external_odds.prospective import (
    collect_fresh_open_external_odds,
    fresh_cache_session_dir,
    is_retryable_snapshot,
)

NOW = datetime(2026, 7, 15, 14, 45, tzinfo=timezone.utc)
DEADLINE = datetime(2026, 7, 16, 15, tzinfo=timezone.utc)
T_MINUS_6 = DEADLINE - timedelta(minutes=6)
T_MINUS_5 = DEADLINE - timedelta(minutes=5)


def _target(*, missing_orders: tuple[int, ...] = ()):
    return SimpleNamespace(
        drawing_id=11953,
        drawing_number=4945,
        events=tuple(
            SimpleNamespace(
                event_order=order,
                starts_at=None if order in missing_orders else NOW,
            )
            for order in range(15)
        ),
    )


def _eligibility(
    status: str = "unknown",
    *,
    missing_orders: tuple[int, ...] = (0,),
):
    return SimpleNamespace(
        status=status,
        span_days=None if status == "unknown" else 1,
        missing_event_orders=missing_orders,
        totobrief_count=15 - len(missing_orders),
        provider_count=0,
    )


def _snapshot(
    *,
    fallback_reasons: tuple[str | None, ...],
    requests: int,
    cache_hits: int,
    collection_id: str,
    horizon_days: int = 2,
    requested_dates: int = 2,
    successful_dates: int = 2,
    failed_dates: int = 0,
    eligibility=None,
):
    reasons = fallback_reasons + (None,) * (15 - len(fallback_reasons))
    return SimpleNamespace(
        collection_id=collection_id,
        drawing_id=11953,
        drawing_number=4945,
        requests_made=requests,
        cache_hits=cache_hits,
        missing_start_horizon_days=horizon_days,
        requested_schedule_dates=tuple(range(requested_dates)),
        successful_schedule_dates=tuple(range(successful_dates)),
        failed_schedule_dates=tuple(range(failed_dates)),
        eligibility=eligibility or _eligibility(),
        events=tuple(
            SimpleNamespace(
                event_order=order,
                match_status="missing" if reason is not None else "matched",
                match_candidate_ids=(),
                fallback_reason=reason,
            )
            for order, reason in enumerate(reasons)
        ),
    )


def _run(
    monkeypatch,
    tmp_path,
    *,
    target,
    snapshots,
    max_passes: int = 3,
    expand_missing_starts: bool = True,
    expansion_horizon_days: int = 5,
    max_expansion_passes: int = 3,
):
    collection_calls = []
    provider_paths = []
    sleep_calls = []
    remaining = list(snapshots)
    monotonic_values = iter(float(value) for value in range(100))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        lambda _client, fetched_at: target,
    )

    def collect_pass(
        supplied_target,
        provider,
        session_factory,
        aliases,
        *,
        missing_start_horizon_days,
    ):
        collection_calls.append(
            (
                supplied_target,
                provider,
                session_factory,
                aliases,
                missing_start_horizon_days,
            )
        )
        return remaining.pop(0)

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        collect_pass,
    )

    def provider_factory(cache_dir):
        provider_paths.append(cache_dir)
        return SimpleNamespace(cache_dir=cache_dir)

    result = collect_fresh_open_external_odds(
        totobrief_client="totobrief",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={"reviewed": "alias"},
        cache_root=tmp_path / "cache",
        max_passes=max_passes,
        expand_missing_starts=expand_missing_starts,
        expansion_horizon_days=expansion_horizon_days,
        max_expansion_passes=max_expansion_passes,
        retry_delay_seconds=65.0,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic_values),
        sleep=sleep_calls.append,
    )
    return result, collection_calls, provider_paths, sleep_calls


def test_retryable_snapshot_accepts_only_operational_provider_failures():
    retryable = (
        "quota reserve reached",
        "partial schedule",
        "provider schedule failure: transport",
        "provider odds failure: transport",
    )
    non_retryable = (
        "0 exact candidates",
        "2 exact candidates",
        "unknown sport",
        "fewer than 3 eligible bookmakers",
        "external consensus unavailable: stale prices",
        "external consensus unavailable: not full-time three-way",
    )

    for reason in retryable:
        assert is_retryable_snapshot(
            _snapshot(
                fallback_reasons=(reason,),
                requests=1,
                cache_hits=0,
                collection_id=reason,
            )
        )
    for reason in non_retryable:
        assert not is_retryable_snapshot(
            _snapshot(
                fallback_reasons=(reason,),
                requests=1,
                cache_hits=0,
                collection_id=reason,
            )
        )

    assert is_retryable_snapshot(
        _snapshot(
            fallback_reasons=(),
            requests=1,
            cache_hits=0,
            collection_id="failed-date-with-complete-events",
            successful_dates=1,
            failed_dates=1,
        )
    )


def test_fresh_cache_sessions_are_drawing_scoped_and_unique():
    target = SimpleNamespace(drawing_id=11953, drawing_number=4945)

    first = fresh_cache_session_dir(Path("cache"), target, NOW)
    second = fresh_cache_session_dir(
        Path("cache"),
        target,
        NOW + timedelta(microseconds=1),
    )

    assert first.parent == Path("cache/runs")
    assert first.name.startswith("4945-")
    assert first != second


def test_supplied_target_bypasses_open_resolution(monkeypatch, tmp_path):
    target = _target()
    snapshot = _snapshot(
        fallback_reasons=(),
        requests=1,
        cache_hits=0,
        collection_id="pinned-target",
    )
    provider_calls = []
    monotonic = iter((0.0, 1.0, 2.0, 3.0))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        lambda *_args, **_kwargs: pytest.fail("must not resolve another target"),
    )
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        lambda *_args, **_kwargs: snapshot,
    )

    def provider_factory(cache_dir):
        provider_calls.append(cache_dir)
        return SimpleNamespace(cache_dir=cache_dir)

    result = collect_fresh_open_external_odds(
        target=target,
        totobrief_client="unused",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic),
        sleep=lambda _seconds: pytest.fail("must not sleep"),
    )

    assert result.snapshot.drawing_id == target.drawing_id
    assert len(provider_calls) == 1


def test_existing_path_resolves_open_target_once(monkeypatch, tmp_path):
    target = _target()
    snapshot = _snapshot(
        fallback_reasons=(),
        requests=1,
        cache_hits=0,
        collection_id="resolved-target",
    )
    resolved = []
    monotonic = iter((0.0, 1.0, 2.0, 3.0))

    def resolve(client, *, fetched_at):
        resolved.append((client, fetched_at))
        return target

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        resolve,
    )
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        lambda *_args, **_kwargs: snapshot,
    )

    collect_fresh_open_external_odds(
        totobrief_client="totobrief",
        provider_factory=lambda cache_dir: SimpleNamespace(cache_dir=cache_dir),
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic),
        sleep=lambda _seconds: pytest.fail("must not sleep"),
    )

    assert resolved == [("totobrief", NOW)]


def test_safety_stop_prevents_retry_after_first_pass(monkeypatch, tmp_path):
    target = _target()
    snapshot = _snapshot(
        fallback_reasons=("quota reserve reached",),
        requests=1,
        cache_hits=0,
        collection_id="retryable",
    )
    times = iter((T_MINUS_6, T_MINUS_5))
    provider_calls = []
    sleep_calls = []
    monotonic = iter((0.0, 1.0, 2.0, 3.0))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        lambda *_args, **_kwargs: snapshot,
    )

    def provider_factory(cache_dir):
        provider_calls.append(cache_dir)
        return SimpleNamespace(cache_dir=cache_dir)

    result = collect_fresh_open_external_odds(
        target=target,
        stop_at=T_MINUS_5,
        totobrief_client="unused",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        now=lambda: next(times),
        monotonic=lambda: next(monotonic),
        sleep=sleep_calls.append,
        max_passes=3,
        retry_delay_seconds=65.0,
    )

    assert result.stop_reason == "safety_stop"
    assert result.base_pass_count == 1
    assert len(provider_calls) == 1
    assert sleep_calls == []


def test_retry_sleep_is_limited_to_remaining_safe_duration(monkeypatch, tmp_path):
    target = _target()
    snapshot = _snapshot(
        fallback_reasons=("quota reserve reached",),
        requests=1,
        cache_hits=0,
        collection_id="retryable",
    )
    times = iter(
        (
            T_MINUS_6,
            T_MINUS_5 - timedelta(seconds=10),
            T_MINUS_5 - timedelta(seconds=10),
            T_MINUS_5,
        )
    )
    provider_calls = []
    sleep_calls = []
    monotonic = iter((0.0, 1.0, 2.0, 3.0))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        lambda *_args, **_kwargs: snapshot,
    )

    def provider_factory(cache_dir):
        provider_calls.append(cache_dir)
        return SimpleNamespace(cache_dir=cache_dir)

    result = collect_fresh_open_external_odds(
        target=target,
        stop_at=T_MINUS_5,
        totobrief_client="unused",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        now=lambda: next(times),
        monotonic=lambda: next(monotonic),
        sleep=sleep_calls.append,
        max_passes=3,
        retry_delay_seconds=65.0,
    )

    assert result.stop_reason == "safety_stop"
    assert len(provider_calls) == 1
    assert sleep_calls == [10.0]


def test_safety_stop_prevents_expansion_after_completed_base_pass(
    monkeypatch,
    tmp_path,
):
    target = _target(missing_orders=(0,))
    snapshot = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=1,
        cache_hits=0,
        collection_id="base-miss",
    )
    times = iter((T_MINUS_6, T_MINUS_6, T_MINUS_5))
    provider_calls = []
    monotonic = iter((0.0, 1.0, 2.0, 3.0))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective._collect_target_pass",
        lambda *_args, **_kwargs: snapshot,
    )

    def provider_factory(cache_dir):
        provider_calls.append(cache_dir)
        return SimpleNamespace(cache_dir=cache_dir)

    result = collect_fresh_open_external_odds(
        target=target,
        stop_at=T_MINUS_5,
        totobrief_client="unused",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        now=lambda: next(times),
        monotonic=lambda: next(monotonic),
        sleep=lambda _seconds: pytest.fail("must not sleep"),
        max_passes=1,
    )

    assert result.stop_reason == "safety_stop"
    assert result.base_pass_count == 1
    assert result.expansion_pass_count == 0
    assert len(provider_calls) == 1


@pytest.mark.parametrize(
    "stop_at",
    (
        datetime(2026, 7, 16, 15),
        datetime(2026, 7, 16, 18, tzinfo=timezone(timedelta(hours=3))),
    ),
)
def test_stop_at_must_be_utc_aware(tmp_path, stop_at):
    with pytest.raises(ValueError, match="stop_at must be timezone-aware UTC"):
        collect_fresh_open_external_odds(
            target=_target(),
            stop_at=stop_at,
            totobrief_client="unused",
            provider_factory=lambda _path: pytest.fail("must not collect"),
            session_factory="unused",
            aliases={},
            cache_root=tmp_path,
        )


def test_safety_stop_before_first_pass_raises_stable_error(tmp_path):
    with pytest.raises(
        ValueError,
        match="safety stop reached before first collection pass",
    ):
        collect_fresh_open_external_odds(
            target=_target(),
            stop_at=T_MINUS_5,
            totobrief_client="unused",
            provider_factory=lambda _path: pytest.fail("must not collect"),
            session_factory="unused",
            aliases={},
            cache_root=tmp_path,
            now=lambda: T_MINUS_5,
        )


def test_clean_two_day_result_does_not_expand(monkeypatch, tmp_path):
    snapshot = _snapshot(
        fallback_reasons=(),
        requests=4,
        cache_hits=0,
        collection_id="base-clean",
        eligibility=_eligibility("playable", missing_orders=()),
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(),
        snapshots=(snapshot,),
    )

    assert [call[4] for call in calls] == [2]
    assert result.expanded is False
    assert result.final_horizon_days == 2
    assert len(result.base_passes) == 1
    assert result.expansion_passes == ()
    assert result.passes[0].phase == "base"
    assert result.passes[0].phase_pass_number == 1
    assert result.passes[0].horizon_days == 2
    assert result.eligibility.status == "playable"
    assert sleep_calls == []


def test_stable_null_start_exact_miss_expands_immediately(monkeypatch, tmp_path):
    base = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=4,
        cache_hits=0,
        collection_id="base-miss",
    )
    expanded = _snapshot(
        fallback_reasons=(),
        requests=3,
        cache_hits=4,
        collection_id="expanded-clean",
        horizon_days=5,
        requested_dates=5,
        successful_dates=5,
        eligibility=_eligibility("playable", missing_orders=()),
    )

    result, calls, provider_paths, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(base, expanded),
    )

    assert [call[4] for call in calls] == [2, 5]
    assert provider_paths == [result.cache_dir, result.cache_dir]
    assert result.snapshot is expanded
    assert result.expanded is True
    assert result.final_horizon_days == 5
    assert len(result.base_passes) == 1
    assert len(result.expansion_passes) == 1
    assert result.expansion_passes[0].phase == "expansion"
    assert result.expansion_passes[0].phase_pass_number == 1
    assert result.expansion_passes[0].horizon_days == 5
    assert sleep_calls == []


def test_known_start_exact_miss_never_expands(monkeypatch, tmp_path):
    base = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=4,
        cache_hits=0,
        collection_id="known-start-miss",
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(),
        snapshots=(base,),
    )

    assert [call[4] for call in calls] == [2]
    assert result.expanded is False
    assert result.final_horizon_days == 2
    assert sleep_calls == []


def test_operational_base_retry_completes_before_expansion(monkeypatch, tmp_path):
    operational = _snapshot(
        fallback_reasons=("partial schedule",),
        requests=2,
        cache_hits=0,
        collection_id="base-operational",
        successful_dates=1,
        failed_dates=1,
    )
    stable_miss = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=2,
        cache_hits=2,
        collection_id="base-stable",
    )
    expanded = _snapshot(
        fallback_reasons=(),
        requests=3,
        cache_hits=4,
        collection_id="expanded",
        horizon_days=5,
        requested_dates=5,
        successful_dates=5,
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(operational, stable_miss, expanded),
    )

    assert [call[4] for call in calls] == [2, 2, 5]
    assert len(result.base_passes) == 2
    assert len(result.expansion_passes) == 1
    assert sleep_calls == [65.0]


def test_quota_retry_stays_inside_expansion(monkeypatch, tmp_path):
    base = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=4,
        cache_hits=0,
        collection_id="base",
    )
    quota = _snapshot(
        fallback_reasons=("quota reserve reached",),
        requests=2,
        cache_hits=4,
        collection_id="expanded-quota",
        horizon_days=5,
        successful_dates=2,
        failed_dates=3,
    )
    stable = _snapshot(
        fallback_reasons=(),
        requests=3,
        cache_hits=6,
        collection_id="expanded-stable",
        horizon_days=5,
        requested_dates=5,
        successful_dates=5,
        eligibility=_eligibility("playable", missing_orders=()),
    )

    result, calls, provider_paths, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(base, quota, stable),
    )

    assert [call[4] for call in calls] == [2, 5, 5]
    assert provider_paths == [result.cache_dir] * 3
    assert len(result.base_passes) == 1
    assert len(result.expansion_passes) == 2
    assert sleep_calls == [65.0]


def test_expansion_exhaustion_is_independently_bounded(monkeypatch, tmp_path):
    base = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=4,
        cache_hits=0,
        collection_id="base",
    )
    expansion_failures = tuple(
        _snapshot(
            fallback_reasons=("quota reserve reached",),
            requests=1,
            cache_hits=index,
            collection_id=f"expansion-{index}",
            horizon_days=5,
            successful_dates=2,
            failed_dates=3,
        )
        for index in range(3)
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(base, *expansion_failures),
        max_passes=1,
        max_expansion_passes=3,
    )

    assert [call[4] for call in calls] == [2, 5, 5, 5]
    assert len(result.base_passes) == 1
    assert len(result.expansion_passes) == 3
    assert result.stop_reason == "max_expansion_passes"
    assert sleep_calls == [65.0, 65.0]


def test_expansion_can_be_disabled(monkeypatch, tmp_path):
    base = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=4,
        cache_hits=0,
        collection_id="base",
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(base,),
        expand_missing_starts=False,
    )

    assert [call[4] for call in calls] == [2]
    assert result.expanded is False
    assert result.expansion_passes == ()
    assert result.final_horizon_days == 2
    assert sleep_calls == []


def test_result_aggregates_all_phase_counters_timing_and_eligibility(
    monkeypatch,
    tmp_path,
):
    final_eligibility = _eligibility("multi_day", missing_orders=())
    snapshots = (
        _snapshot(
            fallback_reasons=("partial schedule",),
            requests=2,
            cache_hits=0,
            collection_id="base-retry",
            requested_dates=2,
            successful_dates=1,
            failed_dates=1,
        ),
        _snapshot(
            fallback_reasons=("0 exact candidates",),
            requests=3,
            cache_hits=1,
            collection_id="base-stable",
            requested_dates=2,
            successful_dates=2,
        ),
        _snapshot(
            fallback_reasons=(),
            requests=4,
            cache_hits=3,
            collection_id="expanded-failed-date",
            horizon_days=5,
            requested_dates=5,
            successful_dates=4,
            failed_dates=1,
        ),
        _snapshot(
            fallback_reasons=(),
            requests=1,
            cache_hits=5,
            collection_id="expanded-stable",
            horizon_days=5,
            requested_dates=5,
            successful_dates=5,
            eligibility=final_eligibility,
        ),
    )

    result, _, _, _ = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=snapshots,
    )

    assert [item.elapsed_seconds for item in result.passes] == [1.0] * 4
    assert result.elapsed_seconds == 9.0
    assert result.total_requests == 10
    assert result.total_cache_hits == 9
    assert result.total_requested_schedule_dates == 14
    assert result.total_successful_schedule_dates == 12
    assert result.total_failed_schedule_dates == 2
    assert result.eligibility is final_eligibility


def test_base_max_pass_exhaustion_never_enters_expansion(monkeypatch, tmp_path):
    operational = _snapshot(
        fallback_reasons=("quota reserve reached",),
        requests=1,
        cache_hits=0,
        collection_id="quota",
    )

    result, calls, _, sleep_calls = _run(
        monkeypatch,
        tmp_path,
        target=_target(missing_orders=(0,)),
        snapshots=(operational,),
        max_passes=1,
    )

    assert [call[4] for call in calls] == [2]
    assert result.stop_reason == "max_passes"
    assert result.expanded is False
    assert sleep_calls == []


@pytest.mark.parametrize("expansion_horizon_days", (1, 2, 6, True))
def test_expansion_horizon_must_be_above_base_and_at_most_five(
    tmp_path,
    expansion_horizon_days,
):
    with pytest.raises(ValueError, match="expansion_horizon_days"):
        collect_fresh_open_external_odds(
            totobrief_client="unused",
            provider_factory=lambda _path: None,
            session_factory="unused",
            aliases={},
            cache_root=tmp_path,
            expansion_horizon_days=expansion_horizon_days,
        )


@pytest.mark.parametrize("max_expansion_passes", (0, -1, True, 1.5))
def test_max_expansion_passes_must_be_a_positive_integer(
    tmp_path,
    max_expansion_passes,
):
    with pytest.raises(ValueError, match="max_expansion_passes"):
        collect_fresh_open_external_odds(
            totobrief_client="unused",
            provider_factory=lambda _path: None,
            session_factory="unused",
            aliases={},
            cache_root=tmp_path,
            max_expansion_passes=max_expansion_passes,
        )
