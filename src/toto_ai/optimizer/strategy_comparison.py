"""Equal-input strategy contracts and thin adapters for package research."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from toto_ai.db.models import Event, Quote
from toto_ai.ev.models import EVConfig, EVInput, EVPackage, EVSurface
from toto_ai.ev.package import select_ev_package_with_top_coupons
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    exact_category_probabilities,
)
from toto_ai.ev.ternary import compute_ev_components, materialize_ev_surface
from toto_ai.optimizer.brief import analyze_event, build_baseline_brief
from toto_ai.optimizer.coupon_probabilities import top_probability_coupons
from toto_ai.optimizer.cover import verify_cover_package

OUTCOMES = ("1", "X", "2")
_PROBABILITY_TOLERANCE = 1e-12


@dataclass(frozen=True)
class FrozenStrategyEvent:
    """One ordered event from an immutable pre-deadline snapshot."""

    event_order: int
    name: str
    bk_probabilities: tuple[float, float, float]
    crowd_probabilities: tuple[float, float, float]

    def __post_init__(self) -> None:
        if type(self.event_order) is not int or not 0 <= self.event_order < 15:
            raise ValueError("event_order must be an integer in 0..14")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("event name must be non-empty")
        object.__setattr__(
            self,
            "bk_probabilities",
            _validated_probability_row(self.bk_probabilities, "BK"),
        )
        object.__setattr__(
            self,
            "crowd_probabilities",
            _validated_probability_row(self.crowd_probabilities, "crowd"),
        )


@dataclass(frozen=True)
class FrozenStrategyInput:
    """The exact shared information boundary for every compared strategy."""

    drawing_id: int
    drawing_number: int
    drawing_fingerprint: str
    source_captured_at: str
    as_of: str
    ended_at: str
    bank: int
    stake: int
    pool_sum: float
    jackpot: float
    possible_winnings: float
    events: tuple[FrozenStrategyEvent, ...]

    def __post_init__(self) -> None:
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be a positive integer")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be a positive integer")
        if (
            not isinstance(self.drawing_fingerprint, str)
            or len(self.drawing_fingerprint) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.drawing_fingerprint
            )
        ):
            raise ValueError("drawing_fingerprint must be a lowercase SHA-256")
        if type(self.stake) is not int or self.stake <= 0:
            raise ValueError("stake must be a positive integer")
        if type(self.bank) is not int or self.bank <= 0:
            raise ValueError("bank must be a positive integer")
        if self.bank % self.stake:
            raise ValueError("bank must be divisible by stake")
        _finite_number(self.pool_sum, "pool_sum", positive=True)
        _finite_number(self.jackpot, "jackpot", positive=False)
        _finite_number(
            self.possible_winnings,
            "possible_winnings",
            positive=False,
        )
        captured = _aware_datetime(self.source_captured_at, "source_captured_at")
        as_of = _aware_datetime(self.as_of, "as_of")
        ended = _aware_datetime(self.ended_at, "ended_at")
        if captured > as_of:
            raise ValueError("source evidence was captured after as_of")
        if as_of > ended:
            raise ValueError("as_of cannot be after the drawing deadline")
        object.__setattr__(self, "events", tuple(self.events))
        if [event.event_order for event in self.events] != list(range(15)):
            raise ValueError("events must contain exactly orders 0 through 14")

    @property
    def max_coupons(self) -> int:
        return self.bank // self.stake

    @property
    def bk_probability_matrix(self) -> tuple[tuple[float, float, float], ...]:
        return tuple(event.bk_probabilities for event in self.events)

    @property
    def crowd_probability_matrix(self) -> tuple[tuple[float, float, float], ...]:
        return tuple(event.crowd_probabilities for event in self.events)

    @property
    def input_sha256(self) -> str:
        return _sha256_json(
            {
                "schema_version": 1,
                "drawing_id": self.drawing_id,
                "drawing_number": self.drawing_number,
                "drawing_fingerprint": self.drawing_fingerprint,
                "source_captured_at": self.source_captured_at,
                "as_of": self.as_of,
                "ended_at": self.ended_at,
                "bank": self.bank,
                "stake": self.stake,
                "pool_sum": self.pool_sum,
                "jackpot": self.jackpot,
                "possible_winnings": self.possible_winnings,
                "events": [asdict(event) for event in self.events],
            }
        )


@dataclass(frozen=True)
class StrategyResult:
    """One validated package generated from a :class:`FrozenStrategyInput`."""

    strategy_id: str
    strategy_version: str
    source_engine: str
    category: int
    input_sha256: str
    config_sha256: str
    package_sha256: str
    requested_bank: int
    stake: int
    coupons: tuple[str, ...]
    cost: int
    unused_bank: int
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float
    runtime_seconds: float
    timed_out: bool
    fallback_reason: str | None = None
    brief: tuple[str, ...] = ()
    coverage_rate: float | None = None
    guarantee_pass: bool | None = None

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_version or not self.source_engine:
            raise ValueError("strategy identity fields must be non-empty")
        if self.category not in {13, 14}:
            raise ValueError("comparison category must be 13 or 14")
        if self.requested_bank <= 0 or self.stake <= 0:
            raise ValueError("strategy bank and stake must be positive")
        object.__setattr__(self, "coupons", tuple(self.coupons))
        object.__setattr__(self, "brief", tuple(self.brief))
        if len(set(self.coupons)) != len(self.coupons):
            raise ValueError("strategy coupons must be unique")
        if any(
            len(coupon) != 15 or set(coupon) - set(OUTCOMES)
            for coupon in self.coupons
        ):
            raise ValueError("strategy coupons must contain exactly 15 outcomes")
        if self.cost != len(self.coupons) * self.stake:
            raise ValueError("strategy cost must equal coupon count times stake")
        if self.cost > self.requested_bank:
            raise ValueError("strategy package exceeds requested bank")
        if self.unused_bank != self.requested_bank - self.cost:
            raise ValueError("unused bank does not match strategy cost")
        if self.package_sha256 != _package_sha256(self.coupons):
            raise ValueError("package_sha256 does not bind the coupon package")
        if any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0
            for value in (
                self.probability_at_least_13,
                self.probability_at_least_14,
                self.probability_at_least_15,
            )
        ):
            raise ValueError("category probabilities must be in [0, 1]")
        if not (
            self.probability_at_least_13
            >= self.probability_at_least_14
            >= self.probability_at_least_15
        ):
            raise ValueError("category probabilities must be nested")
        if not math.isfinite(self.runtime_seconds) or self.runtime_seconds < 0:
            raise ValueError("runtime_seconds must be finite and non-negative")

    @property
    def coupon_count(self) -> int:
        return len(self.coupons)


@dataclass(frozen=True)
class StrategyComparisonBundle:
    """Four strategy variants bound to one immutable comparison input."""

    frozen_input: FrozenStrategyInput
    results: tuple[StrategyResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.frozen_input, FrozenStrategyInput):
            raise ValueError("frozen_input must be a FrozenStrategyInput")
        object.__setattr__(self, "results", tuple(self.results))
        expected = {
            "EV_CROWD_CURRENT",
            "BK_PROBABILITY_ONLY",
            "TOTOBRIEF_STYLE_COVER_13",
            "TOTOBRIEF_STYLE_COVER_14",
        }
        observed = {result.strategy_id for result in self.results}
        if len(self.results) != 4 or observed != expected:
            raise ValueError("comparison must contain the four declared strategies")
        if any(
            result.input_sha256 != self.frozen_input.input_sha256
            for result in self.results
        ):
            raise ValueError("all strategies must use the same frozen input")
        if any(
            result.requested_bank != self.frozen_input.bank
            or result.stake != self.frozen_input.stake
            for result in self.results
        ):
            raise ValueError("all strategies must use the same bank and stake")


def run_equal_input_comparison(
    frozen: FrozenStrategyInput,
    *,
    ev_config: EVConfig,
    provenance: PackageSelectionProvenance | None = None,
    ev_runner: Callable[..., StrategyResult] | None = None,
    bk_runner: Callable[..., StrategyResult] | None = None,
    cover_runner: Callable[..., StrategyResult] | None = None,
) -> StrategyComparisonBundle:
    """Run EV, BK-only, Cover-13 and Cover-14 over identical bytes."""
    resolved_ev_runner = run_ev_crowd_current if ev_runner is None else ev_runner
    resolved_bk_runner = run_bk_probability_only if bk_runner is None else bk_runner
    resolved_cover_runner = (
        run_totobrief_style_cover if cover_runner is None else cover_runner
    )
    results = (
        resolved_ev_runner(
            frozen,
            config=ev_config,
            category=13,
            provenance=provenance,
        ),
        resolved_bk_runner(frozen, category=13),
        resolved_cover_runner(frozen, category=13),
        resolved_cover_runner(frozen, category=14),
    )
    return StrategyComparisonBundle(frozen_input=frozen, results=results)


def run_bk_probability_only(
    frozen: FrozenStrategyInput,
    *,
    category: int,
) -> StrategyResult:
    """Select the most probable coupons without using crowd probabilities."""
    started = time.perf_counter()
    _validated_category(category)
    coupons = tuple(
        top_probability_coupons(
            frozen.bk_probability_matrix,
            limit=frozen.max_coupons,
        )
    )
    return _strategy_result(
        strategy_id="BK_PROBABILITY_ONLY",
        source_engine="optimizer.coupon_probabilities.top_probability_coupons",
        category=category,
        frozen=frozen,
        coupons=coupons,
        config={"category": category},
        runtime_seconds=time.perf_counter() - started,
    )


def run_totobrief_style_cover(
    frozen: FrozenStrategyInput,
    *,
    category: int,
) -> StrategyResult:
    """Build a TotoBrief-style brief and exact verified Cover package."""
    started = time.perf_counter()
    _validated_category(category)
    analyses = [_brief_analysis(event) for event in frozen.events]
    cover_result = build_baseline_brief(
        analyses,
        category=category,
        bank=frozen.bank,
        stake=frozen.stake,
    )
    coupons = tuple(cover_result["selected_coupons"])
    brief = tuple(cover_result["brief"])
    verification = verify_cover_package(
        brief=list(brief),
        category=category,
        coupons=list(coupons),
    )
    if not verification["guarantee_pass"]:
        raise ValueError("Cover package failed its declared exact guarantee")
    return _strategy_result(
        strategy_id=f"TOTOBRIEF_STYLE_COVER_{category}",
        source_engine="optimizer.brief.build_baseline_brief+optimizer.cover",
        category=category,
        frozen=frozen,
        coupons=coupons,
        config={
            "category": category,
            "brief": brief,
            "candidate_count": cover_result["candidate_count"],
        },
        runtime_seconds=time.perf_counter() - started,
        timed_out=bool(cover_result["timed_out"]),
        brief=brief,
        coverage_rate=float(cover_result["coverage_rate"]),
        guarantee_pass=True,
    )


def run_cover_14_bk_fill(frozen: FrozenStrategyInput) -> StrategyResult:
    """Preserve exact Cover-14 and fill remaining capacity by BK probability."""
    started = time.perf_counter()
    cover = run_totobrief_style_cover(frozen, category=14)
    coupons = list(cover.coupons)
    selected = set(coupons)
    if len(coupons) < frozen.max_coupons:
        ranked = top_probability_coupons(
            frozen.bk_probability_matrix,
            limit=frozen.max_coupons + len(coupons),
        )
        for coupon in ranked:
            if coupon in selected:
                continue
            selected.add(coupon)
            coupons.append(coupon)
            if len(coupons) == frozen.max_coupons:
                break
    if len(coupons) != frozen.max_coupons:
        raise ValueError("BK fill could not use the complete dynamic bank")
    return _strategy_result(
        strategy_id="COVER_14_BK_FILL",
        source_engine=(
            "optimizer.brief.build_baseline_brief+optimizer.cover+"
            "optimizer.coupon_probabilities.top_probability_coupons"
        ),
        category=14,
        frozen=frozen,
        coupons=tuple(coupons),
        config={
            "category": 14,
            "fill": "BK_PROBABILITY_DESCENDING",
            "cover_package_sha256": cover.package_sha256,
            "cover_coupon_count": cover.coupon_count,
            "max_coupons": frozen.max_coupons,
        },
        runtime_seconds=time.perf_counter() - started,
        brief=cover.brief,
        coverage_rate=cover.coverage_rate,
        guarantee_pass=cover.guarantee_pass,
    )


def run_ev_crowd_current(
    frozen: FrozenStrategyInput,
    *,
    config: EVConfig,
    category: int = 13,
    provenance: PackageSelectionProvenance | None = None,
    component_builder: Callable[[EVInput], Any] = compute_ev_components,
    surface_materializer: Callable[[Any, float, float], EVSurface] = (
        materialize_ev_surface
    ),
    package_selector: Callable[..., tuple[EVPackage, Sequence[Any]]] = (
        select_ev_package_with_top_coupons
    ),
) -> StrategyResult:
    """Run the existing EV/crowd selector over the same frozen input."""
    started = time.perf_counter()
    _validated_category(category)
    if config.bank != frozen.bank or config.stake != frozen.stake:
        raise ValueError("EV config bank and stake must match the frozen input")
    ev_input = EVInput(
        drawing_id=frozen.drawing_id,
        drawing_number=frozen.drawing_number,
        true_probabilities=frozen.bk_probability_matrix,
        crowd_probabilities=frozen.crowd_probability_matrix,
        pool_sum=frozen.pool_sum,
        jackpot=frozen.jackpot,
        possible_winnings=frozen.possible_winnings,
        probability_sources=("frozen_totobrief_bk",) * 15,
        fetched_at=frozen.source_captured_at,
    )
    components = component_builder(ev_input)
    surface = surface_materializer(
        components,
        frozen.possible_winnings,
        frozen.jackpot,
    )
    package, _ = package_selector(
        surface,
        config,
        probabilities=frozen.bk_probability_matrix,
        provenance=provenance,
    )
    ranked = package.paper_coupons if package.paper_coupons else package.coupons
    coupons = tuple(coupon.coupon for coupon in ranked)
    fallback_reason = package.decision_reason
    return _strategy_result(
        strategy_id="EV_CROWD_CURRENT",
        source_engine="ev.ternary+ev.package.select_ev_package_with_top_coupons",
        category=category,
        frozen=frozen,
        coupons=coupons,
        config={"category": category, "ev_config": asdict(config)},
        runtime_seconds=time.perf_counter() - started,
        fallback_reason=fallback_reason,
    )


def _strategy_result(
    *,
    strategy_id: str,
    source_engine: str,
    category: int,
    frozen: FrozenStrategyInput,
    coupons: tuple[str, ...],
    config: dict[str, object],
    runtime_seconds: float,
    timed_out: bool = False,
    fallback_reason: str | None = None,
    brief: tuple[str, ...] = (),
    coverage_rate: float | None = None,
    guarantee_pass: bool | None = None,
) -> StrategyResult:
    probabilities = exact_category_probabilities(
        coupons,
        frozen.bk_probability_matrix,
    )
    return StrategyResult(
        strategy_id=strategy_id,
        strategy_version="v1",
        source_engine=source_engine,
        category=category,
        input_sha256=frozen.input_sha256,
        config_sha256=_sha256_json(config),
        package_sha256=_package_sha256(coupons),
        requested_bank=frozen.bank,
        stake=frozen.stake,
        coupons=coupons,
        cost=len(coupons) * frozen.stake,
        unused_bank=frozen.bank - len(coupons) * frozen.stake,
        probability_at_least_13=probabilities[0],
        probability_at_least_14=probabilities[1],
        probability_at_least_15=probabilities[2],
        runtime_seconds=runtime_seconds,
        timed_out=timed_out,
        fallback_reason=fallback_reason,
        brief=brief,
        coverage_rate=coverage_rate,
        guarantee_pass=guarantee_pass,
    )


def _brief_analysis(event: FrozenStrategyEvent):
    quote = Quote(
        pool_win_1=event.crowd_probabilities[0],
        pool_draw=event.crowd_probabilities[1],
        pool_win_2=event.crowd_probabilities[2],
        bk_win_1=event.bk_probabilities[0],
        bk_draw=event.bk_probabilities[1],
        bk_win_2=event.bk_probabilities[2],
    )
    return analyze_event(
        Event(event_order=event.event_order, name=event.name),
        quote,
    )


def _validated_probability_row(
    values: Sequence[float],
    name: str,
) -> tuple[float, float, float]:
    row = tuple(float(value) for value in values)
    if len(row) != 3:
        raise ValueError(f"{name} probability row must contain three values")
    if any(not math.isfinite(value) or value <= 0 for value in row):
        raise ValueError(f"{name} probabilities must be finite and positive")
    if not math.isclose(
        sum(row),
        1.0,
        rel_tol=_PROBABILITY_TOLERANCE,
        abs_tol=_PROBABILITY_TOLERANCE,
    ):
        raise ValueError(f"{name} probabilities must sum to one")
    return row  # type: ignore[return-value]


def _validated_category(category: int) -> None:
    if category not in {13, 14}:
        raise ValueError("comparison category must be 13 or 14")


def _aware_datetime(value: str, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"{name} must be a timezone-aware ISO-8601 string"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _finite_number(value: float, name: str, *, positive: bool) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        requirement = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be finite and {requirement}")
    return result


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_sha256(coupons: Sequence[str]) -> str:
    return hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode("utf-8")
    ).hexdigest()
