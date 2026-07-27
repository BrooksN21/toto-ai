import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.db.models import Drawing, Event
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.preparation import (
    load_local_schedule,
    preparation_probability_sha256,
    prepare_drawing,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import load_ready_drawing_pins
from toto_ai.operations.sync_prepare import synchronize_open_drawing

FIXTURES = Path(__file__).parent / "fixtures"


class PageOnlyClient:
    def __init__(self, target_payload):
        self.target_payload = target_payload
        self.page_calls = 0
        self.detail_calls = 0

    def drawings(self, name="baltbet-main", page=1):
        self.page_calls += 1
        data = self.target_payload["data"]
        return {
            "data": [
                {
                    "id": data["id"],
                    "number": data["number"],
                    "name": "baltbet-main",
                    "status": "active",
                    "pool_sum": data.get("pool_sum"),
                    "jackpot": data.get("jackpot"),
                    "ended_at": data["ended_at"],
                }
            ]
        }

    def drawing_info(self, drawing_id):
        self.detail_calls += 1
        raise AssertionError(f"unexpected detail request for {drawing_id}")


class RateLimitedDetailClient(PageOnlyClient):
    def drawing_info(self, drawing_id):
        self.detail_calls += 1
        raise TotoBriefRequestError(
            "TotoBrief request returned HTTP 429 after 4 attempt(s)",
            endpoint=f"/drawing-info/{drawing_id}",
            attempts=4,
            status_code=429,
        )


class FreshDetailClient(PageOnlyClient):
    def drawing_info(self, drawing_id):
        self.detail_calls += 1
        assert drawing_id == self.target_payload["data"]["id"]
        return json.loads(json.dumps(self.target_payload))


def test_sync_prepare_refreshes_stale_probability_cache_before_ready_pins(
    tmp_path,
):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    fresh_payload = target_cache["payload"]
    stale_payload = json.loads(json.dumps(fresh_payload))
    stale_payload["data"]["events"][14]["quotes"].update(
        {
            "bk_win_1": 40,
            "bk_draw": 31,
            "bk_win_2": 30,
        }
    )
    schedule_payload = json.loads(
        (FIXTURES / "drawing_4951_api_sports_schedule.json").read_text()
    )
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        stale_payload,
        drawing_id=11968,
        cache_dir=tmp_path / "raw",
        fetched_at=now - timedelta(seconds=1618),
        source="stale-morning-cache",
        allowed_root=tmp_path,
    )
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = FreshDetailClient(fresh_payload)

    synchronized = synchronize_open_drawing(
        client,
        factory,
        now=now,
        raw_cache_dir=tmp_path / "raw",
        storage_root=tmp_path,
    )
    assert synchronized.ready is True
    assert synchronized.detail.source == "network"
    assert synchronized.detail.cache_age_seconds is None
    assert client.page_calls == 1
    assert client.detail_calls == 1

    target = parse_target_drawing(
        synchronized.detail.payload,
        fetched_at=now,
    )
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule_payload))
    prepared = prepare_drawing(
        target,
        load_local_schedule(schedule_path),
        session_factory=factory,
    )
    assert prepared.status == "ready"

    fresh_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    assert len(
        load_ready_drawing_pins(
            factory,
            drawing_id=target.drawing_id,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            expected_probability_sha256=fresh_hash,
            as_of=now,
        )
    ) == 15

    changed_payload = json.loads(json.dumps(fresh_payload))
    changed_payload["data"]["events"][14]["quotes"].update(
        {
            "bk_win_1": 42,
            "bk_draw": 30,
            "bk_win_2": 28,
        }
    )
    changed_target = parse_target_drawing(
        changed_payload,
        fetched_at=now + timedelta(seconds=1),
    )
    changed_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in changed_target.events)
    )
    with pytest.raises(
        ValueError,
        match="preparation_fail:probability_input_changed_or_missing",
    ):
        load_ready_drawing_pins(
            factory,
            drawing_id=target.drawing_id,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            expected_probability_sha256=changed_hash,
            as_of=now + timedelta(seconds=1),
        )
    engine.dispose()


def test_sync_prepare_fails_closed_when_only_stale_probability_cache_exists(
    tmp_path,
):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        target_payload,
        drawing_id=11968,
        cache_dir=tmp_path / "raw",
        fetched_at=now - timedelta(seconds=61),
        source="stale-morning-cache",
        allowed_root=tmp_path,
    )
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = RateLimitedDetailClient(target_payload)

    synchronized = synchronize_open_drawing(
        client,
        factory,
        now=now,
        raw_cache_dir=tmp_path / "raw",
        storage_root=tmp_path,
    )

    assert synchronized.ready is False
    assert synchronized.detail.status == "deferred"
    assert synchronized.detail.payload is None
    assert client.page_calls == 1
    assert client.detail_calls == 1
    assert "network=TotoBrief request returned HTTP 429" in (
        synchronized.detail.error or ""
    )
    assert "cache=drawing detail cache is stale" in (
        synchronized.detail.error or ""
    )
    engine.dispose()


def test_prepare_after_sync_uses_cached_exact_target_without_second_detail_call(
    tmp_path,
):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    schedule_payload = json.loads(
        (FIXTURES / "drawing_4951_api_sports_schedule.json").read_text()
    )
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        target_payload,
        drawing_id=11968,
        cache_dir=tmp_path / "raw",
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = PageOnlyClient(target_payload)

    synchronized = synchronize_open_drawing(
        client,
        factory,
        now=now,
        raw_cache_dir=tmp_path / "raw",
        storage_root=tmp_path,
    )
    target = parse_target_drawing(
        synchronized.detail.payload,
        fetched_at=now,
    )
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule_payload))
    prepared = prepare_drawing(
        target,
        load_local_schedule(schedule_path),
        session_factory=factory,
    )

    assert synchronized.ready is True
    assert synchronized.detail.source == "cache:inspect-api"
    assert client.page_calls == 1
    assert client.detail_calls == 0
    assert prepared.status == "ready"
    assert prepared.mapped_count == 15
    engine.dispose()


def test_sync_prepare_rejects_cache_identity_mismatch_before_persistence(tmp_path):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    mismatched_payload = json.loads(json.dumps(target_payload))
    mismatched_payload["data"]["number"] += 1
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        mismatched_payload,
        drawing_id=11968,
        cache_dir=tmp_path / "raw",
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = RateLimitedDetailClient(target_payload)

    synchronized = synchronize_open_drawing(
        client,
        factory,
        now=now,
        raw_cache_dir=tmp_path / "raw",
        storage_root=tmp_path,
    )

    assert synchronized.ready is False
    assert synchronized.detail.status == "deferred"
    assert "cache=drawing detail number does not match page summary" in (
        synchronized.detail.error or ""
    )
    assert client.page_calls == 1
    assert client.detail_calls == 1
    with factory() as session:
        stored = session.get(Drawing, 11968)
        assert stored is not None
        assert stored.number == target_payload["data"]["number"]
    engine.dispose()


def test_fresh_page_without_open_candidate_never_falls_back_to_stale_sqlite(
    tmp_path,
):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=target_payload["data"]["id"],
                number=target_payload["data"]["number"],
                name="baltbet-main",
                status="active",
                ended_at=target_payload["data"]["ended_at"],
            )
        )

    class EmptyPageClient:
        detail_calls = 0

        def drawings(self, name="baltbet-main", page=1):
            return {"data": []}

        def drawing_info(self, drawing_id):
            self.detail_calls += 1
            raise AssertionError(f"unexpected detail request {drawing_id}")

    client = EmptyPageClient()
    with pytest.raises(ValueError, match="fresh API page one"):
        synchronize_open_drawing(
            client,
            factory,
            now=now,
            raw_cache_dir=tmp_path / "raw",
            storage_root=tmp_path,
        )

    assert client.detail_calls == 0
    engine.dispose()


def test_expected_visible_number_mismatch_stops_before_detail_fetch(tmp_path):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = PageOnlyClient(target_payload)

    with pytest.raises(ValueError, match="expected drawing 4953.*selected 4951"):
        synchronize_open_drawing(
            client,
            factory,
            now=now,
            expected_drawing_number=4953,
            raw_cache_dir=tmp_path / "raw",
            storage_root=tmp_path,
        )

    assert client.page_calls == 1
    assert client.detail_calls == 0
    with factory() as session:
        assert session.scalar(
            select(Event).where(Event.drawing_id == target_payload["data"]["id"])
        ) is None
    engine.dispose()


def test_finished_detail_mismatch_fails_before_events_or_pins(tmp_path):
    target_cache = json.loads(
        (FIXTURES / "drawing_4951_totobrief_target_cache.json").read_text()
    )
    target_payload = target_cache["payload"]
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)

    class FinishedDetailClient(PageOnlyClient):
        def drawing_info(self, drawing_id):
            self.detail_calls += 1
            payload = json.loads(json.dumps(self.target_payload))
            payload["data"]["status"] = "finished"
            return payload

    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    client = FinishedDetailClient(target_payload)

    synchronized = synchronize_open_drawing(
        client,
        factory,
        now=now,
        raw_cache_dir=tmp_path / "raw",
        storage_root=tmp_path,
    )

    assert synchronized.ready is False
    assert "status does not match" in (synchronized.detail.error or "")
    assert client.detail_calls == 1
    with factory() as session:
        stored = session.get(Drawing, target_payload["data"]["id"])
        assert stored is not None
        assert stored.status == "active"
        assert session.scalar(
            select(Event).where(Event.drawing_id == target_payload["data"]["id"])
        ) is None
    engine.dispose()
