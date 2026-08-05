from __future__ import annotations

import hashlib
import json
import socket
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import requests
from typer.testing import CliRunner

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - depends on the test environment
    httpx = None

import toto_ai.cli as cli_module
import toto_ai.ev.drawing as drawing_module
import toto_ai.runner.reports as runner_reports
from toto_ai.cli import (
    _build_runner_package,
    _build_runner_timing_resolver,
    _build_timing_eligibility_resolver,
    _resolve_runner_target,
)
from toto_ai.db.session import (
    get_session_factory,
    init_db,
    open_readonly_db,
)
from toto_ai.ev.models import (
    EVComponents,
    EVInput,
    EVPackage,
    EVSurface,
    RankedCoupon,
)
from toto_ai.external_odds.api_sports import APISportsError
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.domain import ProviderEvent, ProviderMarket, QuotaState
from toto_ai.external_odds.preparation import prepare_drawing
from toto_ai.external_odds.prospective import collect_fresh_open_external_odds
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.runner import (
    DrawingRunnerConfig,
    publish_drawing_run_artifacts,
    run_drawing,
    write_drawing_run_reports,
)

DEADLINE = datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc)
T_MINUS_21 = DEADLINE - timedelta(minutes=21)
T_MINUS_20 = DEADLINE - timedelta(minutes=20)
T_MINUS_19 = DEADLINE - timedelta(minutes=19)
T_MINUS_5 = DEADLINE - timedelta(minutes=5)
SENTINEL_KEY = "task-6-review-sentinel-key"
_CAPTURED_EV_INPUTS: list[EVInput] = []


@dataclass
class _FakeClock:
    current: datetime
    elapsed: float = 0.0

    def __post_init__(self) -> None:
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)
        self.elapsed += seconds


class _FakeTotoBriefClient:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        final_payload: dict[str, object] | None = None,
        ev_payload: dict[str, object] | None = None,
    ) -> None:
        self._payloads = (payload, final_payload or payload)
        self._ev_payload = ev_payload
        self._resolution_index = 0
        self._drawing_info_calls = 0
        self._active_payload = payload

    @property
    def payload(self) -> dict[str, object]:
        return self._active_payload

    def drawings(self, name: str, page: int) -> dict[str, object]:
        assert (name, page) == ("baltbet-main", 1)
        self._active_payload = self._payloads[min(self._resolution_index, 1)]
        self._resolution_index += 1
        data = self._active_payload["data"]
        assert isinstance(data, dict)
        return {
            "data": [
                {
                    "id": data["id"],
                    "number": data["number"],
                    "status": "expected",
                    "ended_at": data["ended_at"],
                }
            ]
        }

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        self._drawing_info_calls += 1
        payload = (
            self._ev_payload
            if self._ev_payload is not None and self._drawing_info_calls >= 3
            else self._active_payload
        )
        data = payload["data"]
        assert isinstance(data, dict)
        assert drawing_id == data["id"]
        return deepcopy(payload)


class _FakeProvider:
    provider_name = "api-sports"

    def __init__(
        self,
        payload: dict[str, object],
        observed_at: datetime,
        *,
        provider_starts: dict[int, datetime] | None = None,
        unavailable_orders: tuple[int, ...] = (),
        failing_schedule_dates: tuple[date, ...] = (),
        on_first_schedule_call: Callable[[], None] | None = None,
        on_first_market_call: Callable[[], None] | None = None,
        market_prices: tuple[tuple[float, float, float], ...] | None = None,
    ) -> None:
        self.payload = payload
        self.observed_at = observed_at
        self.provider_starts = provider_starts or {}
        self.unavailable_orders = frozenset(unavailable_orders)
        self.failing_schedule_dates = frozenset(failing_schedule_dates)
        self.on_first_schedule_call = on_first_schedule_call
        self.on_first_market_call = on_first_market_call
        self.market_prices = market_prices
        self.requests_made = 0
        self.cache_hits = 0
        self.schedule_calls: list[date] = []
        self.market_calls: list[str] = []
        self._quota_state = QuotaState(100, 80, 10, 8)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(
        self,
        sport: str,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        assert sport == "football"
        requested_date = dates[0]
        self.schedule_calls.append(requested_date)
        if self.on_first_schedule_call is not None:
            callback = self.on_first_schedule_call
            self.on_first_schedule_call = None
            callback()
        if requested_date in self.failing_schedule_dates:
            try:
                raise RuntimeError("acceptance-secret-must-not-persist")
            except RuntimeError as error:
                raise APISportsError("provider schedule failed") from error
        data = self.payload["data"]
        assert isinstance(data, dict)
        events = data["events"]
        assert isinstance(events, list)

        def provider_start(event: dict[str, object]) -> datetime:
            order = int(event["order"])
            if order in self.provider_starts:
                return self.provider_starts[order]
            return datetime.fromisoformat(str(event["start_at"]))

        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"provider-{event['order']}",
                sport="football",
                league=str(event["championship"]),
                starts_at=provider_start(event),
                home_team=f"Home {event['order']}",
                away_team=f"Away {event['order']}",
                fetched_at=self.observed_at,
                payload_hash=f"schedule-{event['order']}",
                provider_home_team_id=f"provider-home-{event['order']}",
                provider_away_team_id=f"provider-away-{event['order']}",
            )
            for event in events
            if int(event["order"]) not in self.unavailable_orders
            and provider_start(event).date() == requested_date
        )

    def fetch_event_markets(
        self,
        sport: str,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        self.requests_made += 1
        assert sport == "football"
        self.market_calls.append(provider_event_id)
        if self.on_first_market_call is not None:
            callback = self.on_first_market_call
            self.on_first_market_call = None
            callback()
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=self.observed_at - timedelta(hours=1),
                fetched_at=self.observed_at,
                payload_hash=f"market-{provider_event_id}-{index}",
                home_price=(
                    self.market_prices[index][0]
                    if self.market_prices is not None
                    else 2.0 + index / 10
                ),
                draw_price=(
                    self.market_prices[index][1]
                    if self.market_prices is not None
                    else 3.8 + index / 10
                ),
                away_price=(
                    self.market_prices[index][2]
                    if self.market_prices is not None
                    else 4.2 + index / 10
                ),
            )
            for index in range(3)
        )


def _forbid_unconfigured_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("acceptance must not use unconfigured network")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    if httpx is not None:
        monkeypatch.setattr(httpx, "request", forbidden)
        monkeypatch.setattr(httpx.Client, "request", forbidden)
        monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)


@pytest.fixture(autouse=True)
def _fast_ev_and_no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    _CAPTURED_EV_INPUTS.clear()
    values = np.zeros(1, dtype=np.float64)

    def fixed_components(ev_input, progress_callback=None):
        _CAPTURED_EV_INPUTS.append(ev_input)
        if progress_callback is not None:
            progress_callback({"phase": "category", "category": 15})
        return EVComponents(
            possible_winnings_ev_per_ruble=values,
            jackpot_ev_per_ruble=values,
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    def fixed_surface(_components, _possible_winnings, _jackpot):
        return EVSurface(
            gross_ev=np.array([1.2], dtype=np.float64),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    monkeypatch.setattr(drawing_module, "compute_ev_components", fixed_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", fixed_surface)

    def safety_valid_coupon(index: int) -> str:
        digest = hashlib.sha256(f"runner-e2e-{index}".encode()).digest()
        return "".join("1X2"[digest[order] % 3] for order in range(15))

    def fixture_coupons(config):
        return tuple(
            RankedCoupon(
                rank=index + 1,
                coupon=safety_valid_coupon(index),
                gross_ev=1.2,
                net_ev=0.2,
            )
            for index in range(config.max_coupons)
        )

    def fixed_package(surface, config):
        if not np.any(surface.gross_ev >= config.min_gross_ev):
            return EVPackage(
                decision="NO BET",
                coupons=(),
                cost=0,
                unused_bank=config.bank,
                expected_payout=0.0,
                modeled_roi=None,
                derived_brief=(),
                decision_reason="no coupon meets the gross EV threshold",
            )
        coupons = fixture_coupons(config)
        cost = len(coupons) * config.stake
        return EVPackage(
            decision="PLAY",
            coupons=coupons,
            cost=cost,
            unused_bank=config.bank - cost,
            expected_payout=1.2 * cost,
            modeled_roi=0.2,
            derived_brief=("1X2",) * 15,
        )

    monkeypatch.setattr(
        drawing_module,
        "select_ev_package",
        fixed_package,
    )
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        lambda surface, config, diagnostic_limit=20: (
            fixed_package(surface, config),
            fixture_coupons(config)[:diagnostic_limit],
        ),
    )
    monkeypatch.setattr(
        drawing_module,
        "_utc_now",
        lambda: T_MINUS_19.isoformat(),
    )
    monkeypatch.setattr(
        time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(
            AssertionError("acceptance must use the fake sleeper")
        ),
    )


def _payload(
    start_overrides: dict[int, datetime | None] | None = None,
) -> dict[str, object]:
    first_start = DEADLINE + timedelta(hours=1)
    overrides = start_overrides or {}
    return {
        "data": {
            "id": 9200,
            "number": 5200,
            "ended_at": DEADLINE.isoformat(),
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": [
                {
                    "id": 30_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "name_en": f"Home {order} - Away {order}",
                    "championship": f"League {order % 3}",
                    "sport": "football",
                    "start_at": (
                        None
                        if order in overrides and overrides[order] is None
                        else overrides.get(
                            order,
                            first_start
                            + timedelta(days=order // 8, minutes=order),
                        ).isoformat()
                    ),
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


def _run_acceptance_scenario(
    tmp_path: Path,
    launch_at: datetime,
    *,
    payload: dict[str, object] | None = None,
    final_payload: dict[str, object] | None = None,
    ev_payload: dict[str, object] | None = None,
    bank: int = 4800,
    mode: str = "playable",
    provider_starts: dict[int, datetime] | None = None,
    unavailable_orders: tuple[int, ...] = (),
    failing_schedule_dates: tuple[date, ...] = (),
    advance_after_package: bool = False,
    advance_on_first_schedule_call: bool = False,
    advance_on_first_market_call: bool = False,
    max_passes: int = 1,
    market_prices: tuple[tuple[float, float, float], ...] | None = None,
    schedule_observed_at: datetime | None = None,
):
    payload = payload or _payload()
    client = _FakeTotoBriefClient(
        payload,
        final_payload=final_payload,
        ev_payload=ev_payload,
    )
    clock = _FakeClock(launch_at)
    db_path = tmp_path / "toto.sqlite"
    report_dir = tmp_path / "reports"
    cache_root = tmp_path / "cache"
    engine = init_db(db_path)
    session_factory = get_session_factory(engine)
    readonly_engine = open_readonly_db(db_path)
    readonly_session_factory = get_session_factory(readonly_engine)
    provider_instances: list[_FakeProvider] = []

    preparation_target = parse_target_drawing(payload, fetched_at=launch_at)
    preparation_candidates = tuple(
        ProviderEvent(
            provider="api-sports",
            provider_event_id=f"provider-{event.event_order}",
            sport=event.sport,
            league=event.championship,
            starts_at=(
                event.starts_at
                or (provider_starts or {}).get(event.event_order)
                or event.deadline + timedelta(hours=event.event_order + 1)
            ),
            home_team=event.home_team,
            away_team=event.away_team,
            fetched_at=launch_at,
            payload_hash=f"preparation-{event.event_order}",
            provider_home_team_id=f"provider-home-{event.event_order}",
            provider_away_team_id=f"provider-away-{event.event_order}",
        )
        for event in preparation_target.events
    )
    preparation = prepare_drawing(
        preparation_target,
        preparation_candidates,
        session_factory=session_factory,
    )
    prepared_pins = preparation.pins if preparation.status == "ready" else None

    def provider_factory(cache_dir: Path) -> _FakeProvider:
        cache_dir.mkdir(parents=True, exist_ok=True)
        provider = _FakeProvider(
            payload,
            schedule_observed_at or clock.now(),
            provider_starts=provider_starts,
            unavailable_orders=unavailable_orders,
            failing_schedule_dates=failing_schedule_dates,
            on_first_schedule_call=(
                lambda: setattr(clock, "current", T_MINUS_5)
                if advance_on_first_schedule_call
                else None
            ),
            on_first_market_call=(
                lambda: setattr(clock, "current", T_MINUS_5)
                if advance_on_first_market_call
                else None
            ),
            market_prices=market_prices,
        )
        provider_instances.append(provider)
        return provider

    config = DrawingRunnerConfig(bank=bank, stake=30, mode=mode)
    timing_resolver = _build_runner_timing_resolver(str(db_path))
    ev_timing_resolver = _build_timing_eligibility_resolver(str(db_path))
    def build_package(expected):
        package = _build_runner_package(
            client=client,
            expected=expected,
            config=config.ev_config,
            fetched_at=clock.now(),
            progress_callback=None,
            timing_eligibility_resolver=ev_timing_resolver,
        )
        if advance_after_package:
            clock.current = T_MINUS_5
        return package

    result = run_drawing(
        config=config,
        resolve_target=lambda resolved_at: _resolve_runner_target(
            client, resolved_at
        ),
        collect_target=lambda target, stop_at: collect_fresh_open_external_odds(
            totobrief_client=client,
            provider_factory=provider_factory,
            session_factory=session_factory,
            aliases={},
            prepared_pins=prepared_pins,
            cache_root=cache_root,
            target=target,
            stop_at=stop_at,
            max_passes=max_passes,
            max_expansion_passes=1,
            retry_delay_seconds=0.0,
            now=clock.now,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        ),
        resolve_timing=timing_resolver,
        audit_coverage=lambda: audit_external_coverage(
            readonly_session_factory,
            last=30,
            minimum_bookmakers=3,
        ),
        build_package=build_package,
        now=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    publication = publish_drawing_run_artifacts(
        result,
        report_dir=report_dir,
        protected_paths=(db_path,),
        protected_roots=(cache_root,),
        now=clock.now,
    )
    result = publication.result
    report_paths = publication.paths
    engine.dispose()
    readonly_engine.dispose()
    provider_calls = tuple(
        (
            tuple(provider.schedule_calls),
            tuple(provider.market_calls),
        )
        for provider in provider_instances
    )
    return result, report_paths, provider_calls, db_path, cache_root


@pytest.mark.parametrize(
    ("launch_at", "expected_decision", "provider_calls"),
    (
        (T_MINUS_21, "PLAY", 1),
        (T_MINUS_19, "PLAY", 1),
        (T_MINUS_5, "NO BET", 0),
    ),
)
def test_safe_runner_operator_boundary(
    monkeypatch,
    tmp_path,
    launch_at,
    expected_decision,
    provider_calls,
):
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, observed_provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path=tmp_path,
        launch_at=launch_at,
    )

    assert result.decision == expected_decision
    assert len(observed_provider_calls) == provider_calls
    assert all(path.exists() for path in report_paths)
    if expected_decision == "PLAY":
        manifest = _runner_manifest_payload(report_paths)
        assert manifest["schema_version"] == 4
        _assert_stable_non_override_timing(manifest)
        ev = manifest["ev"]
        package = ev["package"]
        assert ev["computed"] is True
        assert ev["requested_bank"] == 4800
        assert ev["effective_budget"] == 4800
        assert ev["selected_cost"] == 4800
        assert ev["unused_requested_bank"] == 0
        assert package["decision"] == "PLAY"
        assert package["selected_count"] == len(package["coupons"]) == 160
        assert package["cost"] == ev["selected_cost"] == 4800
        assert package["unused_bank"] == ev["unused_requested_bank"] == 0
        assert package["cost"] == package["selected_count"] * 30
        assert 0 < package["cost"] <= ev["effective_budget"] <= ev["requested_bank"]
        assert result.collection is not None
        assert len(result.collection.snapshot.events) == 15
        assert result.collection.snapshot.target_fingerprint == (
            result.target.fingerprint
        )
        assert result.collection.snapshot.pinned_revalidation is not None
        assert result.collection.snapshot.pinned_revalidation.ready_for_play is True
        assert result.timing_eligibility.target_fingerprint == (
            result.target.fingerprint
        )
        assert result.audit is not None
        assert result.audit.gate.decision == "PENDING"
        assert result.ev_run is not None
        assert result.ev_run.ev_input.probability_sources == (
            "totobrief_bk",
        ) * 15
        assert result.ev_run.package.cost == 4800
    else:
        assert result.collection is None
        assert result.ev_run is None
        _assert_suppressed_package_summary(report_paths, bank=4800)


def test_run_drawing_cli_computed_threshold_no_bet_leaks_no_coupon_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    payload = _payload()
    client = _FakeTotoBriefClient(payload)
    clock = _FakeClock(T_MINUS_19)
    provider_instances: list[_FakeProvider] = []
    captured_publications = []

    def zero_surface(components, _possible_winnings, _jackpot):
        return EVSurface(
            gross_ev=np.zeros_like(components.possible_winnings_ev_per_ruble),
            event_count=components.event_count,
            probability_mass=components.probability_mass,
            crowd_mass=components.crowd_mass,
            minimum_denominator=components.minimum_denominator,
        )

    def configured_provider_factory(api_key: str, quota_reserve: int):
        assert api_key == SENTINEL_KEY
        assert quota_reserve == 10

        def create(_cache_dir: Path):
            provider = _FakeProvider(payload, clock.now())
            provider_instances.append(provider)
            return provider

        return create

    real_publish = runner_reports.publish_drawing_run_artifacts

    def capture_publication(*args, **kwargs):
        publication = real_publish(*args, **kwargs)
        captured_publications.append(publication)
        return publication

    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(
        json.dumps({"version": 1, "aliases": {}}),
        encoding="utf-8",
    )
    db_path = tmp_path / "toto.sqlite"
    engine = init_db(db_path)
    session_factory = get_session_factory(engine)
    target = parse_target_drawing(payload, fetched_at=clock.now())
    preparation_provider = _FakeProvider(payload, clock.now())
    schedule_dates = tuple(
        sorted({event.starts_at.date() for event in target.events if event.starts_at})
    )
    candidates = tuple(
        candidate
        for requested_date in schedule_dates
        for candidate in preparation_provider.fetch_schedule(
            "football", (requested_date,)
        )
    )
    prepared = prepare_drawing(
        target,
        candidates,
        session_factory=session_factory,
    )
    assert prepared.status == "ready"
    engine.dispose()
    report_dir = tmp_path / "reports"
    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_KEY)
    monkeypatch.setattr(cli_module, "TotoBriefClient", lambda: client)
    monkeypatch.setattr(cli_module, "_utc_now_datetime", clock.now)
    monkeypatch.setattr(
        cli_module,
        "_api_sports_provider_factory",
        configured_provider_factory,
    )
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", zero_surface)
    monkeypatch.setattr(
        cli_module,
        "publish_drawing_run_artifacts",
        capture_publication,
    )

    command = CliRunner().invoke(
        cli_module.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4800",
            "--db",
            str(db_path),
            "--report-dir",
            str(report_dir),
            "--cache-root",
            str(tmp_path / "cache"),
            "--aliases",
            str(aliases_path),
            "--max-passes",
            "1",
            "--max-expansion-passes",
            "1",
            "--retry-delay-seconds",
            "0",
        ],
    )

    assert command.exit_code == 0, command.output
    assert "Decision: NO BET" in command.output
    assert "Coupon" not in command.output
    assert len(captured_publications) == 1
    publication = captured_publications[0]
    assert publication.result.decision == "NO BET"
    assert publication.result.ev_run is not None
    assert publication.result.ev_run.package.decision == "NO BET"
    assert publication.result.ev_run.top_coupons
    assert publication.ev == ()
    assert provider_instances

    manifest = _runner_manifest_payload(publication.paths)
    assert manifest["report_links"]["ev"] == []
    linked_paths = {
        Path(path)
        for paths in manifest["report_links"].values()
        for path in paths
    }
    assert linked_paths <= set(publication.paths)
    scanned = b"".join(path.read_bytes() for path in publication.paths)
    for coupon in publication.result.ev_run.top_coupons:
        assert coupon.coupon.encode() not in scanned
    assert not tuple(report_dir.glob("ev_package_*"))


@pytest.mark.parametrize("bank", (4800, 6000, 9600))
def test_safe_runner_never_authorizes_bk_fallback_after_pin_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bank: int,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, provider_calls, db_path, cache_root = (
        _run_acceptance_scenario(
            tmp_path,
            T_MINUS_19,
            bank=bank,
            unavailable_orders=(12, 13, 14),
        )
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert len(result.collection.snapshot.events) == 15
    assert sum(
        event.probability_source == "totobrief_bk_fallback"
        for event in result.collection.snapshot.events
    ) == 3
    summary = result.collection.snapshot.pinned_revalidation
    assert summary is not None
    assert summary.matched_count == 12
    assert summary.missing_event_orders == (12, 13, 14)
    assert summary.ready_for_play is False
    assert result.audit is None
    assert result.ev_run is None
    assert provider_calls and provider_calls[0][0]
    persisted = db_path.read_bytes() + b"".join(
        path.read_bytes() for path in report_paths
    )
    cache_bytes = b"".join(
        path.read_bytes() for path in cache_root.rglob("*") if path.is_file()
    )
    assert b"acceptance-secret-must-not-persist" not in persisted + cache_bytes


def test_safe_runner_refuses_target_roll_forward_and_publishes_coupon_free_no_bet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    changed = _payload()
    changed_data = changed["data"]
    assert isinstance(changed_data, dict)
    changed_data["number"] = 5201
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        final_payload=changed,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "final target does not match preflight"
    assert provider_calls == ()
    manifest_path = next(path for path in report_paths if path.suffix == ".json")
    manifest = manifest_path.read_text(encoding="utf-8")
    assert result.target.fingerprint in manifest
    assert result.final_fingerprint in manifest
    assert "222222" not in manifest
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_refuses_second_fetch_target_mutation_without_starting_ev(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    changed = _payload()
    changed_data = changed["data"]
    assert isinstance(changed_data, dict)
    changed_data["number"] = 5201

    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        ev_payload=changed,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "fresh EV target does not match pinned target"
    assert result.collection is not None
    assert result.ev_run is None
    assert provider_calls
    assert _CAPTURED_EV_INPUTS == []
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_expands_to_day_five_and_vetoes_multi_day_timing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    payload = _payload({14: None})
    late_start = DEADLINE + timedelta(days=4, hours=1)
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        payload=payload,
        provider_starts={14: late_start},
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert result.collection.expanded is True
    assert result.collection.final_horizon_days == 5
    assert result.collection.snapshot.events[14].effective_start_source == "provider"
    assert result.timing_eligibility.status == "not_checked"
    assert "pinned revalidation" in result.terminal_reason
    assert result.ev_run is None
    assert len(result.collection.snapshot.events) == 15
    assert provider_calls[0][0] != provider_calls[-1][0]
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_partial_schedule_remains_explicit_and_unresolved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    payload = _payload({14: None})
    result, report_paths, _, db_path, cache_root = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        payload=payload,
        failing_schedule_dates=(DEADLINE.date(), DEADLINE.date() + timedelta(days=1)),
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert len(result.collection.snapshot.events) == 15
    assert result.collection.snapshot.eligibility.status == "unknown"
    assert result.timing_eligibility.status == "not_checked"
    summary = result.collection.snapshot.pinned_revalidation
    assert summary is not None
    assert summary.ready_for_play is False
    assert summary.failed_schedule_dates
    assert summary.provider_failure_event_orders
    assert any(
        event.probability_source == "totobrief_bk_fallback"
        for event in result.collection.snapshot.events
    )
    assert result.ev_run is None
    _assert_suppressed_package_summary(report_paths, bank=4800)
    bytes_written = db_path.read_bytes() + b"".join(
        path.read_bytes() for path in report_paths
    ) + b"".join(
        path.read_bytes() for path in cache_root.rglob("*") if path.is_file()
    )
    assert b"acceptance-secret-must-not-persist" not in bytes_written


def test_stale_pinned_schedule_blocks_runner_before_ev(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, _, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        schedule_observed_at=T_MINUS_19 - timedelta(days=2),
    )

    assert result.decision == "NO BET"
    assert result.ev_run is None
    assert result.collection is not None
    summary = result.collection.snapshot.pinned_revalidation
    assert summary is not None
    assert summary.matched_count == 0
    assert summary.stale_event_orders == tuple(range(15))
    assert summary.schedule_fresh is False
    assert summary.ready_for_play is False
    assert "pinned revalidation" in result.terminal_reason
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_stops_before_retry_when_collection_reaches_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        advance_on_first_schedule_call=True,
        max_passes=2,
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert result.collection.stop_reason == "safety_stop"
    assert result.collection.base_pass_count == 1
    assert provider_calls == (((DEADLINE.date(),), ()),)
    assert result.collection.snapshot.status == "complete"
    assert len(result.collection.snapshot.events) == 15
    assert {
        event.fallback_reason for event in result.collection.snapshot.events
    } == {"safety stop reached"}
    assert result.ev_run is None
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_stops_in_pass_after_market_request_reaches_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        advance_on_first_market_call=True,
        max_passes=2,
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert result.collection.stop_reason == "safety_stop"
    assert provider_calls == (
        (
            (DEADLINE.date(), DEADLINE.date() + timedelta(days=1)),
            ("provider-0",),
        ),
    )
    assert result.collection.snapshot.status == "complete"
    assert len(result.collection.snapshot.events) == 15
    assert result.collection.snapshot.events[0].fallback_reason == (
        "safety stop reached"
    )
    assert all(
        event.fallback_reason == "safety stop reached"
        for event in result.collection.snapshot.events[1:]
    )
    assert result.ev_run is None
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_safe_runner_discards_package_that_finishes_at_safety_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        advance_after_package=True,
    )

    assert result.decision == "NO BET"
    assert result.ev_run is None
    assert provider_calls
    _assert_suppressed_package_summary(report_paths, bank=4800)


def test_external_consensus_is_diagnostic_and_pin_failure_blocks_fallback_ev(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    payload = _payload()
    consensus_result, _, _, _, _ = _run_acceptance_scenario(
        tmp_path / "consensus",
        T_MINUS_19,
        payload=payload,
        market_prices=(
            (1.30, 8.0, 12.0),
            (1.35, 7.5, 11.0),
            (1.40, 7.0, 10.0),
        ),
    )
    consensus_input = _CAPTURED_EV_INPUTS[-1]
    _CAPTURED_EV_INPUTS.clear()
    fallback_result, _, _, _, _ = _run_acceptance_scenario(
        tmp_path / "fallback",
        T_MINUS_19,
        payload=payload,
        unavailable_orders=tuple(range(15)),
    )

    expected_bk = _independently_normalized_bk(payload)
    assert len(consensus_input.true_probabilities) == 15
    assert len(consensus_input.crowd_probabilities) == 15
    np.testing.assert_allclose(
        np.asarray(consensus_input.true_probabilities),
        np.asarray(expected_bk),
        rtol=1e-15,
        atol=1e-15,
    )
    assert consensus_result.collection is not None
    assert fallback_result.collection is not None
    consensus_event = consensus_result.collection.snapshot.events[0]
    fallback_event = fallback_result.collection.snapshot.events[0]
    assert consensus_event.probability_source == "external_consensus"
    assert fallback_event.probability_source == "totobrief_bk_fallback"
    assert (
        consensus_event.probability_1,
        consensus_event.probability_x,
        consensus_event.probability_2,
    ) != (
        fallback_event.probability_1,
        fallback_event.probability_x,
        fallback_event.probability_2,
    )
    assert consensus_result.ev_run is not None
    assert fallback_result.decision == "NO BET"
    assert fallback_result.ev_run is None
    summary = fallback_result.collection.snapshot.pinned_revalidation
    assert summary is not None
    assert summary.matched_count == 0
    assert summary.ready_for_play is False


def test_command_boundary_detaches_chained_provider_secret_from_every_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    now = datetime.now(timezone.utc)
    payload = _payload_for_deadline(now + timedelta(minutes=19))
    client = _FakeTotoBriefClient(payload)
    scenario_dir = tmp_path / "command-secret"
    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_KEY)
    monkeypatch.setattr(cli_module, "TotoBriefClient", lambda: client)

    def configured_provider_factory(api_key: str, quota_reserve: int):
        assert api_key == SENTINEL_KEY
        assert quota_reserve == 10

        def fail(_cache_dir: Path):
            try:
                raise RuntimeError(f"provider context {SENTINEL_KEY}")
            except RuntimeError:
                error = APISportsError(f"provider rejected {SENTINEL_KEY}")
                cause = ValueError(f"provider cause {SENTINEL_KEY}")
                raise error from cause

        return fail

    monkeypatch.setattr(
        cli_module,
        "_api_sports_provider_factory",
        configured_provider_factory,
    )
    result = CliRunner().invoke(
        cli_module.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4800",
            "--db",
            str(scenario_dir / "toto.sqlite"),
            "--report-dir",
            str(scenario_dir / "reports"),
            "--cache-root",
            str(scenario_dir / "cache"),
        ],
    )

    assert result.exit_code != 0
    assert SENTINEL_KEY not in result.output
    assert "[redacted]" in result.output
    assert result.exception is not None
    assert all(
        SENTINEL_KEY not in text
        for error in _exception_graph(result.exception)
        for text in (str(error), repr(error))
    )
    artifact_bytes = b"".join(
        path.read_bytes() for path in scenario_dir.rglob("*") if path.is_file()
    )
    assert SENTINEL_KEY.encode() not in artifact_bytes


def test_safe_runner_reports_are_byte_deterministic_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    first = _run_acceptance_scenario(tmp_path, T_MINUS_19)
    first_paths = sorted(first[1], key=lambda path: path.name)
    first_bytes = [path.read_bytes() for path in first_paths]
    second = _run_acceptance_scenario(tmp_path, T_MINUS_19)
    second_paths = sorted(second[1], key=lambda path: path.name)
    second_bytes = [path.read_bytes() for path in second_paths]

    assert [path.name for path in first_paths] == [path.name for path in second_paths]
    assert first_bytes == second_bytes
    all_bytes = b"".join(first_bytes + second_bytes)
    assert b"acceptance-secret-must-not-persist" not in all_bytes
    assert not hasattr(first[0], "submit_bet")


def test_safe_runner_report_pair_rolls_back_and_removes_interrupted_new_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, _, _, _, _ = _run_acceptance_scenario(tmp_path, T_MINUS_19)
    rollback_dir = tmp_path / "rollback"
    original_paths = write_drawing_run_reports(result, report_dir=rollback_dir)
    original_bytes = tuple(path.read_bytes() for path in original_paths)
    real_replace = runner_reports.os.replace
    installs = 0

    def interrupt_second_install(source: str, destination: str) -> None:
        nonlocal installs
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            source_path.name.endswith(".tmp")
            and not source_path.name.endswith(".bak.tmp")
            and destination_path.suffix in {".json", ".md"}
        ):
            installs += 1
            if installs == 2:
                raise KeyboardInterrupt("acceptance publication interrupted")
        real_replace(source, destination)

    monkeypatch.setattr(runner_reports.os, "replace", interrupt_second_install)
    with pytest.raises(KeyboardInterrupt, match="publication interrupted"):
        write_drawing_run_reports(result, report_dir=rollback_dir)
    assert tuple(path.read_bytes() for path in original_paths) == original_bytes
    assert tuple(rollback_dir.glob(".*.tmp")) == ()

    fresh_dir = tmp_path / "interrupted-new"
    installs = 0
    with pytest.raises(KeyboardInterrupt, match="publication interrupted"):
        write_drawing_run_reports(result, report_dir=fresh_dir)
    assert tuple(fresh_dir.glob("drawing_run_*")) == ()
    assert tuple(fresh_dir.glob(".*.tmp")) == ()


def _assert_suppressed_package_summary(
    report_paths: tuple[Path, ...],
    *,
    bank: int,
) -> None:
    payload = _runner_manifest_payload(report_paths)
    assert payload["schema_version"] == 4
    _assert_stable_non_override_timing(payload)
    assert payload["ev"] == {
        "computed": False,
        "requested_bank": bank,
        "effective_budget": None,
        "selected_cost": None,
        "unused_requested_bank": None,
        "input_fetched_at": None,
        "minimum_gross_ev": None,
        "prize_fund_factor": None,
        "possible_winnings_source": None,
        "jackpot_source": None,
        "self_dilution_ratio": None,
        "model_supported": None,
        "model_warning": None,
        "package_safety": None,
        "package": {
            "decision": "NO BET",
            "decision_reason": payload["terminal_reason"],
            "coupons": [],
            "selected_count": None,
            "cost": None,
            "unused_bank": None,
            "expected_payout": None,
            "modeled_roi": None,
            "derived_brief": [],
        },
        "sensitivity": [],
    }
    markdown_path = next(
        path for path in report_paths if path.name.startswith("drawing_run_")
        and path.suffix == ".md"
    )
    bullets = _markdown_section_bullets(
        markdown_path.read_text(encoding="utf-8"),
        "EV Package",
    )
    assert bullets["EV package computation"] == "not run"
    assert bullets["decision"] == "NO BET"
    assert bullets["decision reason"] == payload["terminal_reason"]
    assert bullets["requested bank"] == str(bank)
    assert bullets["effective cap"] == "n/a"
    assert bullets["selected count"] == "n/a"
    assert bullets["selected cost"] == "n/a"
    assert bullets["cost"] == "n/a"
    assert bullets["unused requested bank"] == "n/a"
    assert bullets["unused bank"] == "n/a"
    assert bullets["expected payout"] == "n/a"
    assert bullets["modeled ROI"] == "n/a"
    assert bullets["selected coupons"] == "none"


def _assert_stable_non_override_timing(payload: dict[str, object]) -> None:
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    raw = eligibility["raw"]
    effective = eligibility["effective"]
    assert isinstance(raw, dict)
    assert isinstance(effective, dict)
    assert raw == effective
    assert eligibility == {
        **effective,
        "raw": raw,
        "effective": effective,
        "override": None,
    }


def _runner_manifest_payload(report_paths: tuple[Path, ...]) -> dict[str, object]:
    json_path = next(
        path for path in report_paths if path.name.startswith("drawing_run_")
        and path.suffix == ".json"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _markdown_section_bullets(markdown: str, section: str) -> dict[str, str]:
    marker = f"## {section}\n"
    body = markdown.split(marker, 1)[1].split("\n## ", 1)[0]
    return {
        key: value
        for line in body.splitlines()
        if line.startswith("- ") and ": " in line
        for key, value in (line[2:].split(": ", 1),)
    }


def _independently_normalized_bk(
    payload: dict[str, object],
) -> tuple[tuple[float, float, float], ...]:
    data = payload["data"]
    assert isinstance(data, dict)
    events = data["events"]
    assert isinstance(events, list)
    rows = []
    for event in sorted(events, key=lambda item: int(item["order"])):
        quotes = event["quotes"]
        assert isinstance(quotes, dict)
        raw = (
            float(quotes["bk_win_1"]),
            float(quotes["bk_draw"]),
            float(quotes["bk_win_2"]),
        )
        total = sum(raw)
        rows.append(tuple(value / total for value in raw))
    return tuple(rows)


def _payload_for_deadline(deadline: datetime) -> dict[str, object]:
    payload = _payload()
    data = payload["data"]
    assert isinstance(data, dict)
    data["ended_at"] = deadline.isoformat()
    events = data["events"]
    assert isinstance(events, list)
    for event in events:
        order = int(event["order"])
        event["start_at"] = (
            deadline + timedelta(hours=1, minutes=order)
        ).isoformat()
    return payload


def _exception_graph(error: BaseException) -> tuple[BaseException, ...]:
    seen: set[int] = set()
    pending = [error]
    graph = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        graph.append(current)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return tuple(graph)
