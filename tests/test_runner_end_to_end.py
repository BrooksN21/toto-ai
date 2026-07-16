from __future__ import annotations

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

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - depends on the test environment
    httpx = None

import toto_ai.ev.drawing as drawing_module
import toto_ai.runner.reports as runner_reports
from toto_ai.cli import (
    _build_runner_timing_resolver,
    _build_timing_eligibility_resolver,
    _resolve_runner_target,
)
from toto_ai.db.session import (
    get_session_factory,
    init_db,
    open_readonly_db,
)
from toto_ai.ev.drawing import build_open_ev_package
from toto_ai.ev.models import EVComponents, EVSurface
from toto_ai.ev.reports import write_ev_package_reports
from toto_ai.external_odds.api_sports import APISportsError
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.domain import ProviderEvent, ProviderMarket, QuotaState
from toto_ai.external_odds.prospective import collect_fresh_open_external_odds
from toto_ai.external_odds.reports import write_external_coverage_reports
from toto_ai.runner import (
    DrawingRunnerConfig,
    RunnerReportLinks,
    run_drawing,
    write_drawing_run_reports,
)

DEADLINE = datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc)
T_MINUS_21 = DEADLINE - timedelta(minutes=21)
T_MINUS_20 = DEADLINE - timedelta(minutes=20)
T_MINUS_19 = DEADLINE - timedelta(minutes=19)
T_MINUS_5 = DEADLINE - timedelta(minutes=5)


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
    ) -> None:
        self._payloads = (payload, final_payload or payload)
        self._resolution_index = 0
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
        data = self._active_payload["data"]
        assert isinstance(data, dict)
        assert drawing_id == data["id"]
        return deepcopy(self._active_payload)


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
    ) -> None:
        self.payload = payload
        self.observed_at = observed_at
        self.provider_starts = provider_starts or {}
        self.unavailable_orders = frozenset(unavailable_orders)
        self.failing_schedule_dates = frozenset(failing_schedule_dates)
        self.on_first_schedule_call = on_first_schedule_call
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
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=self.observed_at - timedelta(hours=1),
                fetched_at=self.observed_at,
                payload_hash=f"market-{provider_event_id}-{index}",
                home_price=2.0 + index / 10,
                draw_price=3.8 + index / 10,
                away_price=4.2 + index / 10,
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
    values = np.zeros(3**6, dtype=np.float64)

    def fixed_components(_ev_input, progress_callback=None):
        if progress_callback is not None:
            progress_callback({"phase": "category", "category": 15})
        return EVComponents(
            possible_winnings_ev_per_ruble=values,
            jackpot_ev_per_ruble=values,
            event_count=6,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    def fixed_surface(_components, _possible_winnings, _jackpot):
        return EVSurface(
            gross_ev=np.linspace(1.1, 1.5, num=3**6, dtype=np.float64),
            event_count=6,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    monkeypatch.setattr(drawing_module, "compute_ev_components", fixed_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", fixed_surface)
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
    bank: int = 4800,
    mode: str = "playable",
    provider_starts: dict[int, datetime] | None = None,
    unavailable_orders: tuple[int, ...] = (),
    failing_schedule_dates: tuple[date, ...] = (),
    advance_after_package: bool = False,
    advance_on_first_schedule_call: bool = False,
    max_passes: int = 1,
):
    payload = payload or _payload()
    client = _FakeTotoBriefClient(payload, final_payload=final_payload)
    clock = _FakeClock(launch_at)
    db_path = tmp_path / "toto.sqlite"
    report_dir = tmp_path / "reports"
    cache_root = tmp_path / "cache"
    engine = init_db(db_path)
    session_factory = get_session_factory(engine)
    readonly_engine = open_readonly_db(db_path)
    readonly_session_factory = get_session_factory(readonly_engine)
    provider_instances: list[_FakeProvider] = []

    def provider_factory(cache_dir: Path) -> _FakeProvider:
        cache_dir.mkdir(parents=True, exist_ok=True)
        provider = _FakeProvider(
            payload,
            clock.now(),
            provider_starts=provider_starts,
            unavailable_orders=unavailable_orders,
            failing_schedule_dates=failing_schedule_dates,
            on_first_schedule_call=(
                lambda: setattr(clock, "current", T_MINUS_5)
                if advance_on_first_schedule_call
                else None
            ),
        )
        provider_instances.append(provider)
        return provider

    config = DrawingRunnerConfig(bank=bank, stake=30, mode=mode)
    timing_resolver = _build_runner_timing_resolver(str(db_path))
    ev_timing_resolver = _build_timing_eligibility_resolver(str(db_path))
    def build_package(drawing_id: int):
        package = build_open_ev_package(
            client=client,
            drawing_id=drawing_id,
            config=config.ev_config,
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

    external_paths = (
        write_external_coverage_reports(result.audit, report_dir=report_dir)
        if result.audit is not None
        else ()
    )
    ev_paths = (
        write_ev_package_reports(result.ev_run, report_dir=report_dir)
        if result.ev_run is not None
        else ()
    )
    runner_paths = write_drawing_run_reports(
        result,
        links=RunnerReportLinks(external=external_paths, ev=ev_paths),
        report_dir=report_dir,
    )
    report_paths = (*external_paths, *ev_paths, *runner_paths)
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
        assert result.collection is not None
        assert len(result.collection.snapshot.events) == 15
        assert result.collection.snapshot.target_fingerprint == (
            result.target.fingerprint
        )
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
        assert all("222222" not in path.read_text() for path in report_paths)


@pytest.mark.parametrize("bank", (4800, 6000, 9600))
def test_safe_runner_caps_dynamic_banks_and_keeps_external_fallback_audit_only(
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

    assert result.decision == "PLAY"
    assert result.collection is not None
    assert len(result.collection.snapshot.events) == 15
    assert sum(
        event.probability_source == "totobrief_bk_fallback"
        for event in result.collection.snapshot.events
    ) == 3
    assert result.audit is not None
    assert result.audit.gate.decision == "PENDING"
    assert result.ev_run is not None
    assert result.ev_run.ev_input.probability_sources == ("totobrief_bk",) * 15
    assert result.ev_run.package.cost == bank
    assert result.ev_run.package.cost <= bank
    assert result.ev_run.package.cost % 30 == 0
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
    assert result.timing_eligibility.status == "multi_day"
    assert result.ev_run is None
    assert len(result.collection.snapshot.events) == 15
    assert provider_calls[0][0] != provider_calls[-1][0]
    assert all("222222" not in path.read_text() for path in report_paths)


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
    assert result.timing_eligibility.status == "unknown"
    assert result.ev_run is None
    assert all("222222" not in path.read_text() for path in report_paths)
    bytes_written = db_path.read_bytes() + b"".join(
        path.read_bytes() for path in report_paths
    ) + b"".join(
        path.read_bytes() for path in cache_root.rglob("*") if path.is_file()
    )
    assert b"acceptance-secret-must-not-persist" not in bytes_written


def test_safe_runner_stops_before_retry_when_collection_reaches_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, provider_calls, _, _ = _run_acceptance_scenario(
        tmp_path,
        T_MINUS_19,
        failing_schedule_dates=(DEADLINE.date(),),
        advance_on_first_schedule_call=True,
        max_passes=2,
    )

    assert result.decision == "NO BET"
    assert result.collection is not None
    assert result.collection.stop_reason == "safety_stop"
    assert result.collection.base_pass_count == 1
    assert len(provider_calls) == 1
    assert result.ev_run is None
    assert all("222222" not in path.read_text() for path in report_paths)


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
    assert all("222222" not in path.read_text() for path in report_paths)


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
