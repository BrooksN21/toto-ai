from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from toto_ai.external_odds.thesportsdb import (
    DEFAULT_BASE_URL,
    PUBLIC_V1_API_KEY,
    THESPORTSDB_API_KEY_ENV,
    THESPORTSDB_BASE_URL_ENV,
    TheSportsDBClient,
    TheSportsDBConfig,
    TheSportsDBDisabledError,
    TheSportsDBError,
    load_thesportsdb_config,
)

UTC = timezone.utc
SECRET = "test-secret-key"


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected network call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def events_payload() -> dict[str, object]:
    path = Path("tests/fixtures/thesportsdb_v1_events.json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def naive_timestamp_payload() -> dict[str, object]:
    path = Path("tests/fixtures/thesportsdb_v1_naive_timestamp.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> datetime:
    return datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


def test_config_uses_public_v1_key_by_default_and_redacts_env_override() -> None:
    default = load_thesportsdb_config({})
    configured = load_thesportsdb_config(
        {
            THESPORTSDB_API_KEY_ENV: SECRET,
            THESPORTSDB_BASE_URL_ENV: DEFAULT_BASE_URL,
        }
    )

    assert default.enabled is True
    assert default.api_key == PUBLIC_V1_API_KEY
    assert default.base_url == DEFAULT_BASE_URL
    assert configured.enabled is True
    assert configured.api_key == SECRET
    assert configured.base_url == DEFAULT_BASE_URL
    assert SECRET not in repr(configured)


def test_missing_key_fails_before_transport(tmp_path: Path) -> None:
    session = FakeSession([])

    with pytest.raises(TheSportsDBDisabledError, match=THESPORTSDB_API_KEY_ENV):
        TheSportsDBClient("", session=session, cache_dir=tmp_path)

    assert session.calls == []


def test_client_uses_public_v1_key_without_configuration(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    session = FakeSession([FakeResponse(events_payload)])
    client = TheSportsDBClient(session=session, cache_dir=tmp_path, now=_now)

    client.search_schedule_events(
        "Talleres de Córdoba",
        "Rosario Central",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    assert session.calls[0]["url"].endswith(
        f"/{PUBLIC_V1_API_KEY}/searchevents.php"
    )
    assert PUBLIC_V1_API_KEY not in "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )


def test_fixture_parses_identity_timezone_status_and_provenance(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    session = FakeSession([FakeResponse(events_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "Talleres de Córdoba",
        "Rosario Central",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    by_id = {item.provider_event_id: item for item in events}
    scheduled = by_id["1001"]
    assert scheduled.sport == "football"
    assert scheduled.competition == "Argentine Primera Division"
    assert scheduled.home_team == "Talleres de Córdoba"
    assert scheduled.away_team == "Rosario Central"
    assert scheduled.starts_at == datetime(2026, 8, 24, 18, 30, tzinfo=UTC)
    assert scheduled.status == "not_started"
    assert scheduled.eligible is True
    assert scheduled.provider_home_team_id == "501"
    assert scheduled.provider_away_team_id == "502"
    assert scheduled.source_url == "https://www.thesportsdb.com/event/1001"
    assert scheduled.captured_at == _now()
    assert scheduled.source_endpoint == "/searchevents.php"
    assert by_id["1002"].status == "finished"
    assert by_id["1002"].eligible is False
    assert by_id["1003"].status == "postponed"
    assert by_id["1003"].eligible is False
    assert by_id["1004"].starts_at == datetime(2026, 8, 25, 5, 0, tzinfo=UTC)
    assert by_id["1004"].sport == "hockey"
    assert session.calls[0]["params"] == {"e": "Talleres de Córdoba_vs_Rosario Central"}
    assert session.calls[0]["timeout"] == 10.0


def test_real_api_shape_interprets_naive_event_timestamp_as_utc(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
) -> None:
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert len(events) == 1
    assert events[0].starts_at == datetime(2026, 8, 25, 18, 30, tzinfo=UTC)
    assert events[0].starts_at.tzinfo is UTC
    assert events[0].status == "not_started"
    assert events[0].eligible is True


def test_event_timestamp_with_explicit_offset_remains_normalized_to_utc(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strTimestamp"] = "2026-08-25T21:30:00+03:00"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert events[0].starts_at == datetime(2026, 8, 25, 18, 30, tzinfo=UTC)


def test_malformed_event_timestamp_remains_fail_closed(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strTimestamp"] = "not-a-timestamp"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    with pytest.raises(TheSportsDBError, match="timestamp is invalid"):
        client.search_schedule_events(
            "UTC Home",
            "UTC Away",
            window_start=_now(),
            window_end=_now() + timedelta(days=2),
        )


@pytest.mark.parametrize(
    ("status", "event_time"),
    (
        ("Time TBD", "18:30:00"),
        ("Scheduled", "TBD"),
        ("Scheduled", "00:00:00"),
    ),
)
def test_tbd_or_placeholder_timing_is_never_event_eligible(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
    status: str,
    event_time: str,
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strStatus"] = status
    event["strTime"] = event_time
    if event_time == "00:00:00":
        event["strTimestamp"] = "2026-08-25T00:00:00"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert len(events) == 1
    assert events[0].starts_at.tzinfo is UTC
    assert events[0].status == "unknown"
    assert events[0].eligible is False


@pytest.mark.parametrize("status", ("NS", "Not Started"))
def test_not_started_midnight_placeholder_is_never_event_eligible(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
    status: str,
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strStatus"] = status
    event["strTime"] = "00:00:00"
    event["strTimestamp"] = "2026-08-25T00:00:00"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert len(events) == 1
    assert events[0].starts_at == datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
    assert events[0].status == "unknown"
    assert events[0].eligible is False


def test_non_midnight_not_started_event_remains_eligible(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strStatus"] = "Not Started"
    event["strTime"] = "18:30:00"
    event["strTimestamp"] = "2026-08-25T18:30:00"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert len(events) == 1
    assert events[0].starts_at == datetime(2026, 8, 25, 18, 30, tzinfo=UTC)
    assert events[0].status == "not_started"
    assert events[0].eligible is True


def test_tbd_time_without_timestamp_is_retained_only_as_ineligible_diagnostic(
    tmp_path: Path,
    naive_timestamp_payload: dict[str, object],
) -> None:
    event = naive_timestamp_payload["event"][0]
    assert isinstance(event, dict)
    event["strTimestamp"] = None
    event["strTime"] = "TBD"
    event["strStatus"] = "Scheduled"
    session = FakeSession([FakeResponse(naive_timestamp_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.search_schedule_events(
        "UTC Home",
        "UTC Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=2),
    )

    assert len(events) == 1
    assert events[0].starts_at == datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
    assert events[0].status == "unknown"
    assert events[0].eligible is False


def test_documented_eventsday_fetch_is_date_bounded_and_status_filtered(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    day_payload = {"events": events_payload["event"]}
    session = FakeSession([FakeResponse(day_payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    events = client.fetch_schedule("football", (date(2026, 8, 24),))

    assert tuple(item.provider_event_id for item in events) == ("1001",)
    assert session.calls[0]["url"].endswith(f"/{SECRET}/eventsday.php")
    assert session.calls[0]["params"] == {"d": "2026-08-24", "s": "Soccer"}
    with pytest.raises(ValueError, match="at most 5 days"):
        client.fetch_schedule(
            "football",
            (date(2026, 8, 24), date(2026, 8, 30)),
        )


def test_cache_snapshot_is_immutable_idempotent_and_secret_free(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    first_session = FakeSession([FakeResponse(events_payload)])
    first = TheSportsDBClient(
        SECRET,
        session=first_session,
        cache_dir=tmp_path,
        now=_now,
    )
    first_events = first.search_schedule_events(
        "Talleres de Córdoba",
        "Rosario Central",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    second_session = FakeSession([])
    second = TheSportsDBClient(
        SECRET,
        session=second_session,
        cache_dir=tmp_path,
        now=lambda: _now() + timedelta(minutes=1),
    )
    second_events = second.search_schedule_events(
        "Talleres de Córdoba",
        "Rosario Central",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    assert second_events == first_events
    assert second.cache_hits == 1
    assert second.requests_made == 0
    assert second_session.calls == []
    snapshots = tuple((tmp_path / "snapshots").glob("*.json"))
    assert len(snapshots) == 1
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )
    assert SECRET not in serialized


def test_http_provider_quota_diagnostic_is_bounded_and_redacted(
    tmp_path: Path,
) -> None:
    session = FakeSession(
        [FakeResponse({"error": f"api_key={SECRET} token={SECRET}"}, status_code=429)]
    )
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        max_retries=0,
        now=_now,
    )

    with pytest.raises(TheSportsDBError) as caught:
        client.search_schedule_events(
            "Home",
            "Away",
            window_start=_now(),
            window_end=_now() + timedelta(days=1),
        )

    diagnostic = caught.value.diagnostic_payload()
    assert diagnostic is not None
    assert diagnostic["category"] == "http_failure"
    assert diagnostic["endpoint"] == "/searchevents.php"
    assert diagnostic["http_status"] == 429
    assert diagnostic["quota_minute_limit"] == 30
    rendered = json.dumps(diagnostic, sort_keys=True) + str(caught.value)
    assert SECRET not in rendered
    assert len(str(caught.value)) <= 240


def test_timeout_retry_and_rate_limit_are_bounded(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            requests.ConnectionError("temporary"),
            FakeResponse(events_payload),
        ]
    )
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path,
        max_retries=1,
        requests_per_minute=30,
        now=_now,
        monotonic=lambda: 0.0,
        sleep=sleeps.append,
    )

    client.search_schedule_events(
        "Home",
        "Away",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    assert len(session.calls) == 2
    assert sleeps == [2.0]
    assert [item.category for item in client.request_diagnostics] == [
        "transport_retry",
        "success",
    ]


def test_config_rejects_non_https_or_unbounded_transport() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        TheSportsDBConfig(api_key=SECRET, base_url="http://example.com/api")
    with pytest.raises(ValueError, match="max_retries"):
        TheSportsDBConfig(api_key=SECRET, max_retries=4)
    with pytest.raises(ValueError, match="requests_per_minute"):
        TheSportsDBConfig(api_key=SECRET, requests_per_minute=31)


def test_arbitrary_host_fails_before_transport_even_with_injected_session(
    tmp_path: Path,
) -> None:
    session = FakeSession([])

    with pytest.raises(ValueError, match="official HTTPS host"):
        TheSportsDBClient(
            SECRET,
            base_url="https://collector.example/api/v1/json",
            session=session,
            cache_dir=tmp_path,
        )

    assert session.calls == []


def test_env_override_key_is_used_but_never_exposed(
    tmp_path: Path,
    events_payload: dict[str, object],
) -> None:
    config = load_thesportsdb_config({THESPORTSDB_API_KEY_ENV: SECRET})
    session = FakeSession([FakeResponse(events_payload)])
    client = TheSportsDBClient.from_config(
        config,
        session=session,
        cache_dir=tmp_path,
        now=_now,
    )

    client.search_schedule_events(
        "Talleres de Córdoba",
        "Rosario Central",
        window_start=_now(),
        window_end=_now() + timedelta(days=1),
    )

    assert session.calls[0]["url"].endswith(f"/{SECRET}/searchevents.php")
    assert SECRET not in repr(config)
    assert SECRET not in json.dumps(
        [item.payload() for item in client.request_diagnostics],
        sort_keys=True,
    )
    assert SECRET not in "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )
