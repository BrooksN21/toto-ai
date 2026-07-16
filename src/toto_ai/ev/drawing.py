"""Fresh TotoBrief drawing input and open EV package orchestration."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

from toto_ai.analytics.api_inspector import DrawingReference
from toto_ai.api.client import TotoBriefClient
from toto_ai.ev.models import (
    EVConfig,
    EVInput,
    EVPackage,
    EVSurface,
    PlayTimingEligibility,
    RankedCoupon,
)
from toto_ai.ev.package import (
    select_ev_package,
    select_ev_package_with_top_coupons,
)
from toto_ai.ev.prize import normalize_triplet, smooth_crowd_matrix
from toto_ai.ev.ternary import (
    compute_ev_components,
    materialize_ev_surface,
)

SENSITIVITY_FACTORS = (0.70, 0.80, 0.90, 1.00)
SELF_DILUTION_LIMIT = 0.01
PossibleWinningsSource = Literal["pool_sum proxy", "explicit override"]
JackpotSource = Literal["totobrief payload", "explicit override"]
PhaseCallback = Callable[[dict[str, object]], None]
TimingEligibilityResolver = Callable[[Mapping[str, Any]], PlayTimingEligibility]


@dataclass(frozen=True)
class EVSensitivitySummary:
    prize_fund_factor: float
    possible_winnings: float
    decision: str
    selected_count: int
    cost: int
    unused_bank: int
    expected_payout: float
    modeled_roi: float | None


@dataclass(frozen=True)
class EVPackageRun:
    config: EVConfig
    ev_input: EVInput
    surface: EVSurface
    package: EVPackage
    top_coupons: tuple[RankedCoupon, ...]
    sensitivity: tuple[EVSensitivitySummary, ...]
    possible_winnings_source: PossibleWinningsSource
    jackpot_source: JackpotSource
    self_dilution_ratio: float
    model_supported: bool
    model_warning: str | None
    timing_eligibility: PlayTimingEligibility = field(
        default_factory=PlayTimingEligibility.not_checked
    )

    @property
    def timing_diagnostics_suppressed(self) -> bool:
        return (
            self.config.mode == "playable"
            and self.timing_eligibility.status != "playable"
        )


def resolve_open_drawing_from_api(
    client: TotoBriefClient,
    *,
    now: datetime | str | None = None,
) -> DrawingReference:
    """Resolve the nearest playable BaltBet drawing from API page one only."""
    payload = client.drawings("baltbet-main", 1)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise ValueError("TotoBrief drawings page one must contain a data list")

    current_time = _coerce_datetime(now)
    candidates: list[tuple[datetime, int, Mapping[str, Any]]] = []
    for row in payload["data"]:
        if not isinstance(row, Mapping) or row.get("status") not in {
            "active",
            "expected",
        }:
            continue
        ended_at = _parse_datetime(row.get("ended_at"))
        drawing_id = row.get("id")
        if ended_at is None or ended_at <= current_time:
            continue
        if type(drawing_id) is not int:
            raise ValueError("Playable drawing id must be an integer")
        candidates.append((ended_at, drawing_id, row))

    if not candidates:
        raise ValueError("No playable baltbet-main drawing was found on API page one")

    ended_at, drawing_id, selected = min(candidates, key=lambda item: item[:2])
    number = selected.get("number")
    if number is not None and type(number) is not int:
        raise ValueError("Playable drawing number must be an integer or null")
    return DrawingReference(
        drawing_id=drawing_id,
        number=number,
        community="baltbet-main",
        status=str(selected["status"]),
        ended_at=ended_at.isoformat(),
    )


def ev_input_from_payload(
    payload: Mapping[str, Any],
    *,
    fetched_at: str,
    stake: int,
    prize_fund_factor: float,
    possible_winnings: float | None,
    jackpot_override: float | None,
) -> EVInput:
    """Build one strict ordered EV input from a fresh drawing-info response."""
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        raise ValueError("drawing-info payload must contain a data object")

    drawing_id = data.get("id")
    if type(drawing_id) is not int:
        raise ValueError("drawing id must be an integer")
    drawing_number = data.get("number")
    if drawing_number is not None and type(drawing_number) is not int:
        raise ValueError("drawing number must be an integer or null")

    pool_sum = _finite_number("pool_sum", data.get("pool_sum"), positive=True)
    jackpot_value = (
        data.get("jackpot") if jackpot_override is None else jackpot_override
    )
    jackpot = _finite_number("jackpot", jackpot_value, positive=False)
    factor = _finite_number(
        "prize_fund_factor",
        prize_fund_factor,
        positive=False,
    )
    if possible_winnings is not None and factor != 1.0:
        raise ValueError(
            "possible_winnings cannot be combined with a non-default prize_fund_factor"
        )
    resolved_winnings = (
        _finite_number(
            "possible_winnings",
            pool_sum * factor,
            positive=False,
        )
        if possible_winnings is None
        else _finite_number(
            "possible_winnings",
            possible_winnings,
            positive=False,
        )
    )

    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise ValueError("drawing-info payload must contain exactly 15 events")
    if not all(isinstance(event, Mapping) for event in events):
        raise ValueError("every event must be an object")
    ordered_events = sorted(events, key=_event_order)
    if [_event_order(event) for event in ordered_events] != list(range(15)):
        raise ValueError("event orders must be exactly orders 0 through 14")

    true_rows = []
    crowd_rows = []
    for event in ordered_events:
        order = _event_order(event)
        quotes = event.get("quotes")
        if not isinstance(quotes, Mapping):
            raise ValueError(f"event {order} quotes must be an object")
        true_rows.append(_normalized_quote_row(quotes, "bk", order, "BK"))
        crowd_rows.append(_normalized_quote_row(quotes, "pool", order, "pool"))

    crowd_probabilities = smooth_crowd_matrix(
        tuple(crowd_rows),
        pool_sum,
        stake,
    )
    _require_aware_timestamp(fetched_at)
    return EVInput(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        true_probabilities=tuple(true_rows),
        crowd_probabilities=crowd_probabilities,
        pool_sum=pool_sum,
        jackpot=jackpot,
        possible_winnings=resolved_winnings,
        probability_sources=("totobrief_bk",) * 15,
        fetched_at=fetched_at,
    )


def build_open_ev_package(
    *,
    client: TotoBriefClient,
    drawing_id: int,
    config: EVConfig,
    jackpot_override: float | None = None,
    progress_callback: PhaseCallback | None = None,
    timing_eligibility_resolver: TimingEligibilityResolver | None = None,
) -> EVPackageRun:
    """Fetch a fresh snapshot and build one exact open-drawing EV package."""
    payload = client.drawing_info(drawing_id)
    fetched_at = _utc_now()
    _notify(progress_callback, {"phase": "input", "drawing_id": drawing_id})
    ev_input = ev_input_from_payload(
        payload,
        fetched_at=fetched_at,
        stake=config.stake,
        prize_fund_factor=config.prize_fund_factor,
        possible_winnings=config.possible_winnings,
        jackpot_override=jackpot_override,
    )
    if ev_input.drawing_id != drawing_id:
        raise ValueError(
            f"drawing-info data.id {ev_input.drawing_id} does not match requested "
            f"drawing id {drawing_id}"
        )
    timing_eligibility = (
        PlayTimingEligibility.not_checked()
        if timing_eligibility_resolver is None
        else timing_eligibility_resolver(payload)
    )
    if not isinstance(timing_eligibility, PlayTimingEligibility):
        raise TypeError("timing eligibility resolver returned an invalid result")

    def category_progress(update: dict[str, str | int | float]) -> None:
        _notify(progress_callback, dict(update))

    components = compute_ev_components(
        ev_input,
        progress_callback=category_progress if progress_callback is not None else None,
    )

    sensitivity = []
    main_surface: EVSurface | None = None
    main_package: EVPackage | None = None
    top_coupons: tuple[RankedCoupon, ...] = ()
    main_factor = (
        config.prize_fund_factor
        if config.possible_winnings is None
        and config.prize_fund_factor in SENSITIVITY_FACTORS
        else None
    )
    for factor in SENSITIVITY_FACTORS:
        _notify(progress_callback, {"phase": "sensitivity", "factor": factor})
        winnings = ev_input.pool_sum * factor
        surface = materialize_ev_surface(components, winnings, ev_input.jackpot)
        factor_config = replace(
            config,
            prize_fund_factor=factor,
            possible_winnings=None,
        )
        if factor == main_factor:
            factor_package, top_coupons = select_ev_package_with_top_coupons(
                surface,
                factor_config,
            )
            main_surface = surface
            main_package = factor_package
        else:
            factor_package = select_ev_package(surface, factor_config)
        factor_supported = (
            factor_package.cost / ev_input.pool_sum <= SELF_DILUTION_LIMIT
        )
        factor_package = _suppress_unsupported_play(
            factor_package,
            mode=config.mode,
            supported=factor_supported,
            bank=config.bank,
        )
        factor_package = _suppress_ineligible_timing(
            factor_package,
            mode=config.mode,
            timing_eligibility=timing_eligibility,
            bank=config.bank,
        )
        sensitivity.append(
            EVSensitivitySummary(
                prize_fund_factor=factor,
                possible_winnings=winnings,
                decision=factor_package.decision,
                selected_count=len(factor_package.coupons),
                cost=factor_package.cost,
                unused_bank=factor_package.unused_bank,
                expected_payout=factor_package.expected_payout,
                modeled_roi=factor_package.modeled_roi,
            )
        )

    _notify(progress_callback, {"phase": "package"})
    if main_surface is None or main_package is None:
        main_surface = materialize_ev_surface(
            components,
            ev_input.possible_winnings,
            ev_input.jackpot,
        )
        main_package, top_coupons = select_ev_package_with_top_coupons(
            main_surface,
            config,
        )
    self_dilution_ratio = main_package.cost / ev_input.pool_sum
    model_supported = self_dilution_ratio <= SELF_DILUTION_LIMIT
    package = _suppress_unsupported_play(
        main_package,
        mode=config.mode,
        supported=model_supported,
        bank=config.bank,
    )
    package = _suppress_ineligible_timing(
        package,
        mode=config.mode,
        timing_eligibility=timing_eligibility,
        bank=config.bank,
    )
    warning = None
    if not model_supported:
        warning = (
            "Package cost exceeds 1% of pool_sum; the v1 model excludes "
            "package self-dilution."
        )

    return EVPackageRun(
        config=config,
        ev_input=ev_input,
        surface=main_surface,
        package=package,
        top_coupons=top_coupons,
        sensitivity=tuple(sensitivity),
        possible_winnings_source=(
            "explicit override"
            if config.possible_winnings is not None
            else "pool_sum proxy"
        ),
        jackpot_source=(
            "explicit override"
            if jackpot_override is not None
            else "totobrief payload"
        ),
        self_dilution_ratio=self_dilution_ratio,
        model_supported=model_supported,
        model_warning=warning,
        timing_eligibility=timing_eligibility,
    )


def _suppress_unsupported_play(
    package: EVPackage,
    *,
    mode: str,
    supported: bool,
    bank: int,
) -> EVPackage:
    if mode == "playable" and not supported and package.decision == "PLAY":
        return _empty_no_bet(package, bank=bank)
    return package


def _suppress_ineligible_timing(
    package: EVPackage,
    *,
    mode: str,
    timing_eligibility: PlayTimingEligibility,
    bank: int,
) -> EVPackage:
    if (
        mode == "playable"
        and timing_eligibility.status != "playable"
        and package.decision == "PLAY"
    ):
        return _empty_no_bet(package, bank=bank)
    return package


def _empty_no_bet(package: EVPackage, *, bank: int) -> EVPackage:
    return replace(
        package,
        decision="NO BET",
        coupons=(),
        cost=0,
        unused_bank=bank,
        expected_payout=0.0,
        modeled_roi=None,
        derived_brief=("",) * len(package.derived_brief),
    )


def _normalized_quote_row(
    quotes: Mapping[str, Any],
    prefix: str,
    order: int,
    label: str,
) -> tuple[float, float, float]:
    keys = (f"{prefix}_win_1", f"{prefix}_draw", f"{prefix}_win_2")
    try:
        values = tuple(
            _finite_number(f"{label} quote", quotes.get(key), positive=False)
            for key in keys
        )
        return normalize_triplet(values)
    except ValueError as error:
        raise ValueError(f"Invalid {label} row for event {order}: {error}") from error


def _event_order(event: Mapping[str, Any]) -> int:
    order = event.get("order")
    if type(order) is not int:
        raise ValueError("event order must be an integer")
    return order


def _finite_number(name: str, value: Any, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number")
    if (positive and converted <= 0.0) or (not positive and converted < 0.0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be {qualifier}")
    return converted


def _coerce_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid datetime: {value}")
    return parsed


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _require_aware_timestamp(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("fetched_at must be an ISO datetime with a timezone")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            "fetched_at must be an ISO datetime with a timezone"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("fetched_at must be an ISO datetime with a timezone")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notify(callback: PhaseCallback | None, payload: dict[str, object]) -> None:
    if callback is not None:
        callback(payload)
