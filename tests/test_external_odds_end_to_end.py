from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

import toto_ai.cli as cli_module
import toto_ai.external_odds.collection as collection_module
from toto_ai.cli import app
from toto_ai.db.models import Base
from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.external_odds.api_sports import APISportsClient, APISportsError
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.collection import collect_open_external_odds
from toto_ai.external_odds.domain import ProviderEvent, ProviderMarket, QuotaState
from toto_ai.external_odds.reports import write_external_coverage_reports
from toto_ai.external_odds.storage import load_latest_complete_collections

FETCHED_AT = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
SECRET = "task7-secret-api-key"


def test_open_collection_records_all_events_and_never_changes_ev_input(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    payload = drawing_info_payload()
    original_ev = ev_input_from_payload(
        payload,
        fetched_at=FETCHED_AT.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    provider = MixedCoverageProvider(consensus_events=9)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(payload),
        provider=provider,
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    after_ev = ev_input_from_payload(
        payload,
        fetched_at=FETCHED_AT.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )

    assert len(result.events) == 15
    assert tuple(event.event_order for event in result.events) == tuple(range(15))
    assert (
        sum(row.probability_source == "external_consensus" for row in result.events)
        == 9
    )
    assert (
        sum(row.probability_source == "totobrief_bk_fallback" for row in result.events)
        == 6
    )
    assert all(row.fallback_reason for row in result.events[9:])
    assert after_ev.true_probabilities == original_ev.true_probabilities
    assert after_ev.probability_sources == ("totobrief_bk",) * 15


def test_provider_failure_still_records_fifteen_explicit_fallbacks(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=ProviderFailureProvider(),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)

    assert len(result.events) == 15
    assert all(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    assert all(
        row.fallback_reason.startswith("provider schedule failure")
        for row in result.events
    )
    assert audit.total.explicit_dispositions == 15
    assert audit.total.provider_error_count == 15
    assert audit.gate.decision == "PENDING"


def test_quota_failure_after_five_events_still_records_fifteen(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    provider = QuotaAfterProvider(after=5)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=provider,
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )

    assert len(result.events) == 15
    assert (
        sum(row.probability_source == "external_consensus" for row in result.events)
        == 5
    )
    assert all(
        row.fallback_reason == "quota reserve reached" for row in result.events[5:]
    )
    assert provider.market_calls == tuple(f"football-{order}" for order in range(6))


def test_interrupted_collection_publishes_no_complete_run(monkeypatch, tmp_path):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)

    with pytest.raises(KeyboardInterrupt, match="operator interrupted"):
        collect_open_external_odds(
            totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
            provider=InterruptingProvider(),
            session_factory=factory,
            aliases={},
            fetched_at=FETCHED_AT,
        )

    assert load_latest_complete_collections(factory, last=1) == ()


def test_report_integrity_includes_required_evidence(monkeypatch, tmp_path):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)
    collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=MixedCoverageProvider(consensus_events=9),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)
    loaded = load_latest_complete_collections(factory, last=1)[0]

    first_paths = write_external_coverage_reports(audit, report_dir=tmp_path)
    first_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in first_paths
    )
    second_paths = write_external_coverage_reports(audit, report_dir=tmp_path)
    second_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in second_paths
    )

    assert second_hashes == first_hashes
    assert loaded.daily_limit == 100
    assert loaded.daily_remaining == 78
    assert loaded.requests_made == 16
    assert loaded.cache_hits == 0
    assert loaded.target_fetched_at == FETCHED_AT.isoformat()
    assert all(
        event.provider_event_fetched_at == FETCHED_AT.isoformat()
        for event in loaded.events
    )
    assert all(
        quote.fetched_at == FETCHED_AT.isoformat()
        and quote.updated_at == (FETCHED_AT - timedelta(hours=1)).isoformat()
        for event in loaded.events[:9]
        for quote in event.bookmaker_quotes
    )
    with first_paths[0].open(newline="") as source:
        reader = csv.DictReader(source)
        report_rows = list(reader)
    assert {
        "provider_schedule_fetched_at",
        "provider_schedule_payload_hash",
        "market_fetched_at",
        "market_updated_at",
        "market_payload_hashes",
        "requests_made",
        "cache_hits",
        "target_fetched_at",
        "daily_limit",
        "daily_remaining",
        "minute_remaining",
        "consensus_minimum_bookmakers",
        "consensus_maximum_age_hours",
        "gate_decision",
        "gate_predicate",
        "gate_operator",
        "gate_threshold",
        "gate_actual",
        "gate_passed",
    } <= set(reader.fieldnames or ())
    disposition_rows = [row for row in report_rows if row["row_type"] == "disposition"]
    gate_rows = [row for row in report_rows if row["row_type"] == "gate_predicate"]
    assert len(disposition_rows) == 15
    assert [int(row["event_order"]) for row in disposition_rows] == list(range(15))
    assert [row["probability_source"] for row in disposition_rows[:10]] == [
        *("external_consensus" for _ in range(9)),
        "totobrief_bk_fallback",
    ]
    assert disposition_rows[9]["fallback_reason"] == "fewer than 3 eligible bookmakers"
    first_disposition = disposition_rows[0]
    assert first_disposition["provider_schedule_fetched_at"] == FETCHED_AT.isoformat()
    assert first_disposition["provider_schedule_payload_hash"] == "schedule-hash-0"
    assert (
        json.loads(first_disposition["market_fetched_at"])
        == [FETCHED_AT.isoformat()] * 3
    )
    assert (
        json.loads(first_disposition["market_updated_at"])
        == [(FETCHED_AT - timedelta(hours=1)).isoformat()] * 3
    )
    assert json.loads(first_disposition["market_payload_hashes"]) == [
        "market-hash-0-0",
        "market-hash-0-1",
        "market-hash-0-2",
    ]
    assert {
        (
            row["requests_made"],
            row["cache_hits"],
            row["target_fetched_at"],
            row["daily_limit"],
            row["daily_remaining"],
            row["minute_remaining"],
            row["consensus_minimum_bookmakers"],
            row["consensus_maximum_age_hours"],
            row["gate_decision"],
        )
        for row in disposition_rows
    } == {
        (
            "16",
            "0",
            FETCHED_AT.isoformat(),
            "100",
            "78",
            "8",
            "3",
            "36.000000",
            "PENDING",
        )
    }
    assert [
        (
            row["gate_predicate"],
            row["gate_operator"],
            row["gate_threshold"],
            row["gate_actual"],
            row["gate_passed"],
        )
        for row in gate_rows
    ] == [
        ("minimum_drawings", ">=", "30", "1", "false"),
        ("minimum_events", ">=", "450", "15", "false"),
        (
            "minimum_unique_match_rate",
            ">=",
            "0.800000000000",
            "1.000000000000",
            "true",
        ),
        (
            "minimum_usable_consensus_rate",
            ">=",
            "0.700000000000",
            "0.600000000000",
            "false",
        ),
        ("zero_ambiguous_matches", "==", "0", "0", "true"),
        ("complete_explicit_dispositions", "==", "15", "15", "true"),
    ]
    markdown = first_paths[1].read_text(encoding="utf-8")
    assert "- minimum bookmakers: 3" in markdown
    assert "- collection consensus minimum bookmakers: 3" in markdown
    assert "- collection consensus maximum odds age hours: 36.000000" in markdown
    assert "- gate sample floor: 30 drawings and 450 events" in markdown
    assert "- decision: PENDING" in markdown
    assert "- reasons: fewer than 30 drawings, fewer than 450 events" in markdown
    assert "## Collection Run Evidence" in markdown
    assert f"| 16 | 0 | {FETCHED_AT.isoformat()} | 100 | 78 | 8 |" in markdown
    assert "## Gate Predicate Outcomes" in markdown
    assert "| minimum_events | 15 | >= | 450 | false |" in markdown
    assert (
        "| minimum_usable_consensus_rate | 0.600000000000 | >= | "
        "0.700000000000 | false |"
    ) in markdown
    assert first_hashes == (
        "55af4ab37630e3a93fb823041ac5c502dd5be8dbd62081e26d13bc420a17f506",
        "0f29ad701380d6fa289e59ac7f41fc12ff7c2d1540c575b7ffb4ef7796b9336b",
    )


def test_secret_absent_from_sqlite_cache_cli_exceptions_and_reports(
    monkeypatch,
    tmp_path,
):
    factory, db_path = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)
    audit_report_dir = tmp_path / "reports"
    collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=MixedCoverageProvider(consensus_events=9),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    report_paths = write_external_coverage_reports(
        audit_external_coverage(factory, last=1, minimum_bookmakers=3),
        report_dir=audit_report_dir,
    )

    cache_dir = tmp_path / "cache"
    cache_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    APISportsClient(SECRET, session=cache_session, cache_dir=cache_dir).fetch_schedule(
        "football",
        (date(2026, 7, 14),),
    )

    failing_session = FakeSession(
        [requests.ConnectionError(f"transport leaked {SECRET}")]
    )
    with pytest.raises(APISportsError) as excinfo:
        APISportsClient(
            SECRET,
            session=failing_session,
            cache_dir=tmp_path / "failing-cache",
            max_retries=0,
        ).fetch_schedule("football", (date(2026, 7, 14),))

    class ExplodingAPISportsClient:
        def __init__(self, *_args, **_kwargs):
            raise APISportsError(f"provider leaked {SECRET}")

    monkeypatch.setenv("API_SPORTS_KEY", SECRET)
    monkeypatch.setattr(cli_module, "APISportsClient", ExplodingAPISportsClient)
    monkeypatch.setattr(
        cli_module,
        "collect_fresh_open_external_odds",
        lambda **kwargs: kwargs["provider_factory"](tmp_path / "fresh-cache"),
    )
    cli_result = CliRunner().invoke(
        app,
        [
            "collect-external-odds",
            "--open",
            "--db",
            str(tmp_path / "cli.db"),
        ],
    )

    assert cache_session.calls[0]["headers"]["x-apisports-key"] == SECRET
    assert SECRET not in "\n".join(sqlite_text_values(db_path))
    assert SECRET not in "".join(
        path.read_text(encoding="utf-8") for path in cache_dir.iterdir()
    )
    transport_chain = recursive_exception_chain(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None
    assert len(transport_chain) == 1
    assert_secret_absent_from_exception_chain(excinfo.value)
    assert cli_result.exit_code != 0
    assert SECRET not in cli_result.output
    assert_secret_absent_from_exception_chain(cli_result.exception)
    assert "[redacted]" in cli_result.output
    assert SECRET not in "".join(
        path.read_text(encoding="utf-8") for path in report_paths
    )


def recursive_exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    pending = [error]
    seen: set[int] = set()
    chain: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return tuple(chain)


def assert_secret_absent_from_exception_chain(error: BaseException) -> None:
    for reachable in recursive_exception_chain(error):
        assert SECRET not in str(reachable)
        assert SECRET not in repr(reachable)


def sqlite_factory(tmp_path: Path):
    db_path = tmp_path / "toto.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False), db_path


def install_open_drawing(monkeypatch) -> None:
    monkeypatch.setattr(
        collection_module,
        "resolve_open_drawing_from_api",
        lambda _client: type("Reference", (), {"drawing_id": 9000, "number": 5000})(),
    )


class FakeTotoBriefClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        assert drawing_id == 9000
        return self.payload


class MixedCoverageProvider:
    provider_name = "api-sports"

    def __init__(self, *, consensus_events: int) -> None:
        self.consensus_events = consensus_events
        self.requests_made = 0
        self.market_calls: tuple[str, ...] = ()
        self._quota_state = QuotaState(100, 78, 10, 8)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(
        self, sport: str, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        assert sport == "football"
        assert dates == (date(2026, 7, 14),)
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"football-{order}",
                sport="football",
                league=f"League {order % 3}",
                starts_at=event_start(order),
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                fetched_at=FETCHED_AT,
                payload_hash=f"schedule-hash-{order}",
            )
            for order in range(15)
        )

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        self.requests_made += 1
        self.market_calls = (*self.market_calls, provider_event_id)
        order = int(provider_event_id.rsplit("-", 1)[1])
        bookmaker_count = 3 if order < self.consensus_events else 2
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=FETCHED_AT - timedelta(hours=1),
                fetched_at=FETCHED_AT,
                payload_hash=f"market-hash-{order}-{index}",
                home_price=2.0 + index / 10,
                draw_price=3.8 + index / 10,
                away_price=4.2 + index / 10,
            )
            for index in range(bookmaker_count)
        )


class ProviderFailureProvider(MixedCoverageProvider):
    def __init__(self) -> None:
        super().__init__(consensus_events=0)

    def fetch_schedule(
        self, sport: str, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        raise APISportsError("sanitized provider unavailable")


class QuotaAfterProvider(MixedCoverageProvider):
    def __init__(self, *, after: int) -> None:
        super().__init__(consensus_events=15)
        self.after = after

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        if len(self.market_calls) >= self.after:
            self.market_calls = (*self.market_calls, provider_event_id)
            self.requests_made += 1
            self._quota_state = QuotaState(100, 10, 10, 0)
            from toto_ai.external_odds.api_sports import QuotaExhausted

            raise QuotaExhausted("quota reserve reached")
        return super().fetch_event_markets(sport, provider_event_id)


class InterruptingProvider(MixedCoverageProvider):
    def __init__(self) -> None:
        super().__init__(consensus_events=15)

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        raise KeyboardInterrupt("operator interrupted")


def drawing_info_payload() -> dict[str, object]:
    return {
        "data": {
            "id": 9000,
            "number": 5000,
            "ended_at": (FETCHED_AT + timedelta(hours=5)).isoformat(),
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": [
                {
                    "id": 10_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "name_en": f"Home {order} - Away {order}",
                    "championship": f"League {order % 3}",
                    "sport": "football",
                    "start_at": event_start(order).isoformat(),
                    "quotes": {
                        "bk_win_1": 45 + order,
                        "bk_draw": 30 + order,
                        "bk_win_2": 25 + order,
                        "pool_win_1": 48 + order,
                        "pool_draw": 32 + order,
                        "pool_win_2": 20 + order,
                    },
                }
                for order in reversed(range(15))
            ],
        }
    }


def event_start(order: int) -> datetime:
    return FETCHED_AT + timedelta(hours=6, minutes=order)


def sqlite_text_values(db_path: Path) -> list[str]:
    values: list[str] = []
    with sqlite3.connect(db_path) as connection:
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table_name in table_names:
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table_name})")
                if "CHAR" in row[2].upper() or "TEXT" in row[2].upper()
            ]
            if not columns:
                continue
            escaped_columns = ", ".join(f'"{column}"' for column in columns)
            for row in connection.execute(
                f'SELECT {escaped_columns} FROM "{table_name}"'
            ):
                values.extend(str(value) for value in row if value is not None)
    return values


@dataclass
class FakeResponse:
    payload: dict[str, object]
    headers: dict[str, str]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def quota_headers() -> dict[str, str]:
    return {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "x-ratelimit-limit": "10",
        "x-ratelimit-remaining": "9",
    }


def football_schedule_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_481_600,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "fixture": {
                    "id": 42,
                    "date": "2026-07-14T18:00:00+00:00",
                },
                "league": {"name": "Premier League"},
                "teams": {
                    "home": {"name": "Home FC"},
                    "away": {"name": "Away FC"},
                },
            }
        ],
    }
