from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from toto_ai.external_odds.prospective import (
    collect_fresh_open_external_odds,
    fresh_cache_session_dir,
    is_retryable_snapshot,
)

NOW = datetime(2026, 7, 15, 14, 45, tzinfo=timezone.utc)


def _snapshot(
    *,
    fallback_reasons: tuple[str | None, ...],
    requests: int,
    cache_hits: int,
    collection_id: str,
):
    reasons = fallback_reasons + (None,) * (15 - len(fallback_reasons))
    return SimpleNamespace(
        collection_id=collection_id,
        drawing_id=11953,
        drawing_number=4945,
        requests_made=requests,
        cache_hits=cache_hits,
        events=tuple(
            SimpleNamespace(fallback_reason=reason) for reason in reasons
        ),
    )


def test_retryable_snapshot_accepts_only_operational_provider_failures():
    retryable = (
        "quota reserve reached",
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


def test_fresh_collection_pins_target_reuses_cache_and_aggregates_passes(
    monkeypatch,
    tmp_path,
):
    target = SimpleNamespace(drawing_id=11953, drawing_number=4945)
    snapshots = [
        _snapshot(
            fallback_reasons=("quota reserve reached",),
            requests=10,
            cache_hits=0,
            collection_id="first",
        ),
        _snapshot(
            fallback_reasons=("0 exact candidates",),
            requests=5,
            cache_hits=10,
            collection_id="second",
        ),
    ]
    resolve_calls = []
    collection_calls = []
    provider_paths = []
    sleep_calls = []
    monotonic_values = iter((0.0, 1.0, 2.0, 3.0, 4.0, 5.0))

    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        lambda client, fetched_at: (
            resolve_calls.append((client, fetched_at)) or target
        ),
    )
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.collect_target_external_odds",
        lambda supplied_target, provider, session_factory, aliases: (
            collection_calls.append(
                (supplied_target, provider, session_factory, aliases)
            )
            or snapshots.pop(0)
        ),
    )

    def provider_factory(cache_dir):
        provider_paths.append(cache_dir)
        return SimpleNamespace(pass_number=len(provider_paths))

    result = collect_fresh_open_external_odds(
        totobrief_client="totobrief",
        provider_factory=provider_factory,
        session_factory="session-factory",
        aliases={"reviewed": "alias"},
        cache_root=tmp_path / "cache",
        max_passes=3,
        retry_delay_seconds=65.0,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic_values),
        sleep=sleep_calls.append,
    )

    assert resolve_calls == [("totobrief", NOW)]
    assert [call[0] for call in collection_calls] == [target, target]
    assert provider_paths == [result.cache_dir, result.cache_dir]
    assert sleep_calls == [65.0]
    assert result.snapshot.collection_id == "second"
    assert len(result.passes) == 2
    assert [item.elapsed_seconds for item in result.passes] == [1.0, 1.0]
    assert result.total_requests == 15
    assert result.total_cache_hits == 10
    assert result.elapsed_seconds == 5.0
    assert result.stop_reason == "no_retryable_fallbacks"


def test_fresh_collection_stops_without_sleep_for_non_retryable_fallback(
    monkeypatch,
    tmp_path,
):
    target = SimpleNamespace(drawing_id=11953, drawing_number=4945)
    snapshot = _snapshot(
        fallback_reasons=("0 exact candidates",),
        requests=15,
        cache_hits=0,
        collection_id="only",
    )
    sleep_calls = []
    monotonic_values = iter((0.0, 1.0, 2.0, 3.0))
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        lambda _client, fetched_at: target,
    )
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.collect_target_external_odds",
        lambda *_args: snapshot,
    )

    result = collect_fresh_open_external_odds(
        totobrief_client="totobrief",
        provider_factory=lambda cache_dir: SimpleNamespace(cache_dir=cache_dir),
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        max_passes=3,
        retry_delay_seconds=65.0,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic_values),
        sleep=sleep_calls.append,
    )

    assert len(result.passes) == 1
    assert sleep_calls == []
    assert result.stop_reason == "no_retryable_fallbacks"


def test_fresh_collection_reports_max_pass_exhaustion(monkeypatch, tmp_path):
    target = SimpleNamespace(drawing_id=11953, drawing_number=4945)
    snapshot = _snapshot(
        fallback_reasons=("quota reserve reached",),
        requests=10,
        cache_hits=0,
        collection_id="quota",
    )
    sleep_calls = []
    monotonic_values = iter((0.0, 1.0, 2.0, 3.0))
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.resolve_open_target",
        lambda _client, fetched_at: target,
    )
    monkeypatch.setattr(
        "toto_ai.external_odds.prospective.collect_target_external_odds",
        lambda *_args: snapshot,
    )

    result = collect_fresh_open_external_odds(
        totobrief_client="totobrief",
        provider_factory=lambda cache_dir: SimpleNamespace(cache_dir=cache_dir),
        session_factory="session-factory",
        aliases={},
        cache_root=tmp_path,
        max_passes=1,
        retry_delay_seconds=65.0,
        now=lambda: NOW,
        monotonic=lambda: next(monotonic_values),
        sleep=sleep_calls.append,
    )

    assert len(result.passes) == 1
    assert sleep_calls == []
    assert result.stop_reason == "max_passes"
