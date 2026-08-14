"""Explicitly retrospective strategy diagnostics with resumable checkpoints."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import StringIO
from itertools import combinations
from pathlib import Path
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.data_health import audit_data_health
from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.ev.models import EVConfig
from toto_ai.ev.prize import normalize_triplet, smooth_crowd_matrix
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    StrategyResult,
    run_bk_probability_only,
    run_ev_crowd_current,
    run_totobrief_style_cover,
)
from toto_ai.optimizer.strategy_historical_benchmark import (
    package_overlap,
    score_coupon_package,
)

EVIDENCE_TIER = "LEGACY_RETROSPECTIVE"
STRATEGY_IDS = frozenset(
    (
        "EV_CROWD_CURRENT",
        "BK_PROBABILITY_ONLY",
        "TOTOBRIEF_STYLE_COVER_13",
        "TOTOBRIEF_STYLE_COVER_14",
    )
)


@dataclass(frozen=True)
class LegacyRetrospectiveInput:
    """Current SQLite probabilities with deliberately unknown chronology."""

    drawing_id: int
    drawing_number: int
    ended_at: str
    source_extracted_at: str
    source_data_sha256: str
    bank: int
    stake: int
    pool_sum: float
    jackpot: float
    possible_winnings: float
    events: tuple[FrozenStrategyEvent, ...]
    evidence_tier: str = EVIDENCE_TIER
    chronology_verified: bool = False

    def __post_init__(self) -> None:
        if self.evidence_tier != EVIDENCE_TIER:
            raise ValueError("legacy input evidence tier cannot be changed")
        if self.chronology_verified is not False:
            raise ValueError("legacy input chronology must remain unverified")
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be positive")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be positive")
        if type(self.bank) is not int or type(self.stake) is not int:
            raise ValueError("bank and stake must be integers")
        if self.bank <= 0 or self.stake <= 0 or self.bank % self.stake:
            raise ValueError("bank must be positive and divisible by stake")
        _sha256_value(self.source_data_sha256, "source_data_sha256")
        _aware_timestamp(self.source_extracted_at, "source_extracted_at")
        object.__setattr__(self, "events", tuple(self.events))
        if [event.event_order for event in self.events] != list(range(15)):
            raise ValueError("legacy events must contain orders 0 through 14")
        for name, value, positive in (
            ("pool_sum", self.pool_sum, True),
            ("jackpot", self.jackpot, False),
            ("possible_winnings", self.possible_winnings, False),
        ):
            _finite_number(value, name, positive=positive)

    @property
    def max_coupons(self) -> int:
        return self.bank // self.stake

    @property
    def source_captured_at(self) -> str:
        return self.source_extracted_at

    @property
    def bk_probability_matrix(self) -> tuple[tuple[float, float, float], ...]:
        return tuple(event.bk_probabilities for event in self.events)

    @property
    def crowd_probability_matrix(
        self,
    ) -> tuple[tuple[float, float, float], ...]:
        return tuple(event.crowd_probabilities for event in self.events)

    @property
    def input_sha256(self) -> str:
        return _sha256_json(
            {
                "schema_version": 1,
                "evidence_tier": self.evidence_tier,
                "chronology_verified": self.chronology_verified,
                "drawing_id": self.drawing_id,
                "drawing_number": self.drawing_number,
                "ended_at": self.ended_at,
                "source_data_sha256": self.source_data_sha256,
                "bank": self.bank,
                "stake": self.stake,
                "pool_sum": self.pool_sum,
                "jackpot": self.jackpot,
                "possible_winnings": self.possible_winnings,
                "events": [asdict(event) for event in self.events],
            }
        )


@dataclass(frozen=True)
class LegacyRetrospectiveCase:
    strategy_input: LegacyRetrospectiveInput
    actual: str
    source_data_sha256: str


@dataclass(frozen=True)
class LegacyStrategyRow:
    drawing_id: int
    drawing_number: int
    ended_at: str
    source_extracted_at: str
    source_data_sha256: str
    input_sha256: str
    actual: str
    strategy_id: str
    strategy_version: str
    category: int
    config_sha256: str
    package_sha256: str
    coupon_count: int
    cost: int
    unused_bank: int
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float
    best_hits: int
    average_hits: float
    median_hits: float
    hit_distribution: tuple[tuple[int, int], ...]
    category_counts: tuple[tuple[int, int], ...]
    hit_13: bool
    hit_14: bool
    hit_15: bool
    average_actual_outcome_exposure: float
    minimum_actual_outcome_exposure: float
    zero_exposure_event_orders: tuple[int, ...]
    runtime_seconds: float
    timed_out: bool
    fallback_reason: str | None
    coverage_rate: float | None
    guarantee_pass: bool | None


@dataclass(frozen=True)
class LegacyOverlapRow:
    drawing_id: int
    drawing_number: int
    left_strategy_id: str
    right_strategy_id: str
    intersection_count: int
    union_count: int
    jaccard: float


@dataclass(frozen=True)
class LegacyRetrospectiveBenchmark:
    rows: tuple[LegacyStrategyRow, ...]
    overlaps: tuple[LegacyOverlapRow, ...]
    summary: dict[str, object]
    bank: int
    stake: int
    configuration_sha256: str


@dataclass(frozen=True)
class LegacyRetrospectiveReportPaths:
    manifest: Path
    json: Path
    rows_csv: Path
    overlaps_csv: Path
    markdown: Path


def load_legacy_retrospective_cases(
    session: Session,
    *,
    db_path: str | Path,
    last: int,
    bank: int,
    stake: int,
    community: str = "baltbet-main",
    extracted_at: datetime | str | None = None,
) -> tuple[LegacyRetrospectiveCase, ...]:
    """Load current DB rows without pretending they are pre-deadline evidence."""
    if type(last) is not int or last <= 0:
        raise ValueError("last must be a positive integer")
    if type(bank) is not int or type(stake) is not int:
        raise ValueError("bank and stake must be integers")
    if bank <= 0 or stake <= 0 or bank % stake:
        raise ValueError("bank must be positive and divisible by stake")
    extracted = _resolved_extracted_at(extracted_at)
    report = audit_data_health(
        session,
        db_path=Path(db_path).resolve(),
        use_case="backtest_probability",
        strict=False,
        community=community,
    )
    eligible = sorted(
        (
            row
            for row in report.drawings
            if row.use_case_eligibility["backtest_probability"]
        ),
        key=lambda row: (
            row.drawing_number if row.drawing_number is not None else -1,
            row.drawing_id,
        ),
        reverse=True,
    )[:last]
    cases = []
    for health_row in eligible:
        drawing = session.get(Drawing, health_row.drawing_id)
        if drawing is None or drawing.number is None or drawing.ended_at is None:
            raise ValueError("eligible legacy drawing lost its identity")
        events = list(
            session.scalars(
                select(Event)
                .where(Event.drawing_id == drawing.id)
                .order_by(Event.event_order)
            ).all()
        )
        quotes = {
            quote.event_order: quote
            for quote in session.scalars(
                select(Quote)
                .where(Quote.drawing_id == drawing.id)
                .order_by(Quote.event_order)
            ).all()
            if quote.event_order is not None
        }
        cases.append(
            _legacy_case(
                drawing,
                events,
                quotes,
                bank=bank,
                stake=stake,
                extracted_at=extracted,
            )
        )
    return tuple(cases)


def run_legacy_strategy_comparison(
    strategy_input: LegacyRetrospectiveInput,
    *,
    ev_config: EVConfig,
) -> tuple[StrategyResult, ...]:
    """Run the same four engines while preserving the legacy evidence label."""
    results = (
        run_ev_crowd_current(
            strategy_input,  # type: ignore[arg-type]
            config=ev_config,
            category=13,
            provenance=None,
        ),
        run_bk_probability_only(
            strategy_input,  # type: ignore[arg-type]
            category=13,
        ),
        run_totobrief_style_cover(
            strategy_input,  # type: ignore[arg-type]
            category=13,
        ),
        run_totobrief_style_cover(
            strategy_input,  # type: ignore[arg-type]
            category=14,
        ),
    )
    if {result.strategy_id for result in results} != STRATEGY_IDS:
        raise ValueError("legacy comparison returned an invalid strategy set")
    if any(
        result.input_sha256 != strategy_input.input_sha256
        or result.requested_bank != strategy_input.bank
        or result.stake != strategy_input.stake
        for result in results
    ):
        raise ValueError("legacy comparison returned foreign strategy output")
    return results


def benchmark_legacy_retrospective_cases(
    cases: Sequence[LegacyRetrospectiveCase],
    *,
    ev_config: EVConfig,
    checkpoint_dir: str | Path,
    comparison_runner: Callable[..., tuple[StrategyResult, ...]] = (
        run_legacy_strategy_comparison
    ),
    progress_callback: Callable[[int, int, int, str], None] | None = None,
) -> LegacyRetrospectiveBenchmark:
    retrospective_cases = tuple(cases)
    if not retrospective_cases:
        raise ValueError("legacy benchmark requires at least one case")
    if any(
        case.strategy_input.bank != ev_config.bank
        or case.strategy_input.stake != ev_config.stake
        for case in retrospective_cases
    ):
        raise ValueError("legacy case bank and stake must match EV config")
    root = Path(checkpoint_dir).absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("checkpoint directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    configuration_sha256 = _sha256_json(asdict(ev_config))
    rows = []
    overlaps = []
    resumed = 0
    total = len(retrospective_cases)
    for index, case in enumerate(retrospective_cases, start=1):
        checkpoint_path = root / (
            f"drawing-{case.strategy_input.drawing_number}-"
            f"{case.strategy_input.drawing_id}.json"
        )
        if checkpoint_path.exists():
            drawing_rows, drawing_overlaps = _load_checkpoint(
                checkpoint_path,
                case=case,
                configuration_sha256=configuration_sha256,
            )
            resumed += 1
            status = "resumed"
        else:
            if progress_callback is not None:
                progress_callback(
                    index,
                    total,
                    case.strategy_input.drawing_number,
                    "running",
                )
            results = comparison_runner(
                case.strategy_input,
                ev_config=ev_config,
            )
            drawing_rows, drawing_overlaps = _score_legacy_results(
                case,
                results,
            )
            _write_checkpoint(
                checkpoint_path,
                case=case,
                configuration_sha256=configuration_sha256,
                rows=drawing_rows,
                overlaps=drawing_overlaps,
            )
            status = "complete"
        rows.extend(drawing_rows)
        overlaps.extend(drawing_overlaps)
        if progress_callback is not None:
            progress_callback(
                index,
                total,
                case.strategy_input.drawing_number,
                status,
            )
    summary = _summary(rows, overlaps, total, resumed, ev_config)
    return LegacyRetrospectiveBenchmark(
        rows=tuple(rows),
        overlaps=tuple(overlaps),
        summary=summary,
        bank=ev_config.bank,
        stake=ev_config.stake,
        configuration_sha256=configuration_sha256,
    )


def write_legacy_retrospective_benchmark_reports(
    benchmark: LegacyRetrospectiveBenchmark,
    output_dir: str | Path,
) -> LegacyRetrospectiveReportPaths:
    if not isinstance(benchmark, LegacyRetrospectiveBenchmark):
        raise ValueError("benchmark must be a LegacyRetrospectiveBenchmark")
    root = Path(output_dir).absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("legacy report directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "legacy_benchmark.json"
    rows_path = root / "legacy_strategy_rows.csv"
    overlaps_path = root / "legacy_package_overlaps.csv"
    markdown_path = root / "legacy_benchmark.md"
    payload = {
        "schema_version": 1,
        "artifact_class": "RESEARCH/PAPER",
        "evidence_tier": EVIDENCE_TIER,
        "chronology_verified": False,
        "release_evidence": False,
        "actionable": False,
        "automatic_wagering": False,
        "bank": benchmark.bank,
        "stake": benchmark.stake,
        "configuration_sha256": benchmark.configuration_sha256,
        "summary": benchmark.summary,
        "rows": [asdict(row) for row in benchmark.rows],
        "overlaps": [asdict(row) for row in benchmark.overlaps],
    }
    _atomic_write(json_path, _json_bytes(payload))
    _atomic_write(rows_path, _rows_csv(benchmark.rows).encode("utf-8"))
    _atomic_write(
        overlaps_path,
        _overlaps_csv(benchmark.overlaps).encode("utf-8"),
    )
    _atomic_write(markdown_path, _markdown(benchmark).encode("utf-8"))
    unsigned = {
        "schema_version": 1,
        "artifact_class": "RESEARCH/PAPER",
        "evidence_tier": EVIDENCE_TIER,
        "chronology_verified": False,
        "release_evidence": False,
        "actionable": False,
        "automatic_wagering": False,
        "bank": benchmark.bank,
        "stake": benchmark.stake,
        "configuration_sha256": benchmark.configuration_sha256,
        "drawings_evaluated": benchmark.summary["drawings_evaluated"],
        "artifacts": {
            "benchmark_json": _artifact(root, json_path),
            "strategy_rows_csv": _artifact(root, rows_path),
            "package_overlaps_csv": _artifact(root, overlaps_path),
            "benchmark_markdown": _artifact(root, markdown_path),
        },
    }
    manifest_path = root / "manifest.json"
    _atomic_write(
        manifest_path,
        _json_bytes(
            {
                **unsigned,
                "manifest_sha256": hashlib.sha256(
                    _canonical_json_bytes(unsigned)
                ).hexdigest(),
            }
        ),
    )
    return LegacyRetrospectiveReportPaths(
        manifest=manifest_path,
        json=json_path,
        rows_csv=rows_path,
        overlaps_csv=overlaps_path,
        markdown=markdown_path,
    )


def _legacy_case(
    drawing: Drawing,
    events: Sequence[Event],
    quotes: Mapping[int, Quote],
    *,
    bank: int,
    stake: int,
    extracted_at: str,
) -> LegacyRetrospectiveCase:
    ordered = tuple(events)
    if len(ordered) != 15 or [event.event_order for event in ordered] != list(
        range(15)
    ):
        raise ValueError("legacy drawing events must be ordered 0 through 14")
    if set(quotes) != set(range(15)):
        raise ValueError("legacy drawing quotes must cover orders 0 through 14")
    pool_sum = _finite_number(drawing.pool_sum, "pool_sum", positive=True)
    jackpot = _finite_number(drawing.jackpot, "jackpot", positive=False)
    bk_rows = tuple(
        normalize_triplet(_quote_triplet(quotes[order], "bk"))
        for order in range(15)
    )
    pool_rows = tuple(
        normalize_triplet(_quote_triplet(quotes[order], "pool"))
        for order in range(15)
    )
    crowd_rows = smooth_crowd_matrix(pool_rows, pool_sum, stake)
    prediction_payload = {
        "schema_version": 1,
        "drawing_id": drawing.id,
        "drawing_number": drawing.number,
        "ended_at": drawing.ended_at,
        "pool_sum": pool_sum,
        "jackpot": jackpot,
        "events": [
            {
                "event_order": order,
                "name": ordered[order].name,
                "bk": bk_rows[order],
                "pool": pool_rows[order],
            }
            for order in range(15)
        ],
    }
    source_data_sha256 = _sha256_json(prediction_payload)
    strategy_input = LegacyRetrospectiveInput(
        drawing_id=drawing.id,
        drawing_number=drawing.number,
        ended_at=drawing.ended_at,
        source_extracted_at=extracted_at,
        source_data_sha256=source_data_sha256,
        bank=bank,
        stake=stake,
        pool_sum=pool_sum,
        jackpot=jackpot,
        possible_winnings=pool_sum,
        events=tuple(
            FrozenStrategyEvent(
                event_order=order,
                name=ordered[order].name or f"Event {order + 1}",
                bk_probabilities=bk_rows[order],
                crowd_probabilities=crowd_rows[order],
            )
            for order in range(15)
        ),
    )
    actual = "".join(_actual_outcome(event) for event in ordered)
    return LegacyRetrospectiveCase(
        strategy_input=strategy_input,
        actual=actual,
        source_data_sha256=source_data_sha256,
    )


def _score_legacy_results(
    case: LegacyRetrospectiveCase,
    results: Sequence[StrategyResult],
) -> tuple[tuple[LegacyStrategyRow, ...], tuple[LegacyOverlapRow, ...]]:
    result_tuple = tuple(results)
    if len(result_tuple) != 4 or {
        result.strategy_id for result in result_tuple
    } != STRATEGY_IDS:
        raise ValueError("legacy benchmark requires the four declared strategies")
    rows = []
    for result in result_tuple:
        if result.input_sha256 != case.strategy_input.input_sha256:
            raise ValueError("legacy result input hash does not match case")
        score = score_coupon_package(
            strategy_id=result.strategy_id,
            coupons=result.coupons,
            actual=case.actual,
        )
        rows.append(
            LegacyStrategyRow(
                drawing_id=case.strategy_input.drawing_id,
                drawing_number=case.strategy_input.drawing_number,
                ended_at=case.strategy_input.ended_at,
                source_extracted_at=case.strategy_input.source_extracted_at,
                source_data_sha256=case.source_data_sha256,
                input_sha256=case.strategy_input.input_sha256,
                actual=case.actual,
                strategy_id=result.strategy_id,
                strategy_version=result.strategy_version,
                category=result.category,
                config_sha256=result.config_sha256,
                package_sha256=result.package_sha256,
                coupon_count=result.coupon_count,
                cost=result.cost,
                unused_bank=result.unused_bank,
                probability_at_least_13=result.probability_at_least_13,
                probability_at_least_14=result.probability_at_least_14,
                probability_at_least_15=result.probability_at_least_15,
                best_hits=score.best_hits,
                average_hits=score.average_hits,
                median_hits=score.median_hits,
                hit_distribution=score.hit_distribution,
                category_counts=score.category_counts,
                hit_13=score.best_hits >= 13,
                hit_14=score.best_hits >= 14,
                hit_15=score.best_hits >= 15,
                average_actual_outcome_exposure=mean(
                    score.actual_outcome_exposure
                ),
                minimum_actual_outcome_exposure=min(
                    score.actual_outcome_exposure
                ),
                zero_exposure_event_orders=score.zero_exposure_event_orders,
                runtime_seconds=result.runtime_seconds,
                timed_out=result.timed_out,
                fallback_reason=result.fallback_reason,
                coverage_rate=result.coverage_rate,
                guarantee_pass=result.guarantee_pass,
            )
        )
    overlap_rows = []
    for left, right in combinations(result_tuple, 2):
        overlap = package_overlap(left.coupons, right.coupons)
        overlap_rows.append(
            LegacyOverlapRow(
                drawing_id=case.strategy_input.drawing_id,
                drawing_number=case.strategy_input.drawing_number,
                left_strategy_id=left.strategy_id,
                right_strategy_id=right.strategy_id,
                intersection_count=overlap.intersection_count,
                union_count=overlap.union_count,
                jaccard=overlap.jaccard,
            )
        )
    return tuple(rows), tuple(overlap_rows)


def _summary(
    rows: Sequence[LegacyStrategyRow],
    overlaps: Sequence[LegacyOverlapRow],
    drawing_count: int,
    resumed: int,
    config: EVConfig,
) -> dict[str, object]:
    strategies = {}
    for strategy_id in sorted({row.strategy_id for row in rows}):
        selected = tuple(row for row in rows if row.strategy_id == strategy_id)
        strategies[strategy_id] = {
            "drawings": len(selected),
            "average_best_hits": mean(row.best_hits for row in selected),
            "median_best_hits": median(row.best_hits for row in selected),
            "average_coupon_hits": mean(row.average_hits for row in selected),
            "hit_13_count": sum(row.hit_13 for row in selected),
            "hit_14_count": sum(row.hit_14 for row in selected),
            "hit_15_count": sum(row.hit_15 for row in selected),
            "hit_13_rate": mean(row.hit_13 for row in selected),
            "hit_14_rate": mean(row.hit_14 for row in selected),
            "hit_15_rate": mean(row.hit_15 for row in selected),
            "average_coupon_count": mean(row.coupon_count for row in selected),
            "average_cost": mean(row.cost for row in selected),
            "average_unused_bank": mean(row.unused_bank for row in selected),
            "average_actual_outcome_exposure": mean(
                row.average_actual_outcome_exposure for row in selected
            ),
            "zero_exposure_drawings": sum(
                bool(row.zero_exposure_event_orders) for row in selected
            ),
            "timed_out_count": sum(row.timed_out for row in selected),
            "fallback_count": sum(
                row.fallback_reason is not None for row in selected
            ),
            "average_runtime_seconds": mean(
                row.runtime_seconds for row in selected
            ),
            "average_modeled_probability_at_least_13": mean(
                row.probability_at_least_13 for row in selected
            ),
            "average_modeled_probability_at_least_14": mean(
                row.probability_at_least_14 for row in selected
            ),
            "average_modeled_probability_at_least_15": mean(
                row.probability_at_least_15 for row in selected
            ),
        }
    return {
        "drawings_evaluated": drawing_count,
        "resumed_drawings": resumed,
        "strategy_count": len(strategies),
        "bank": config.bank,
        "stake": config.stake,
        "evidence_tier": EVIDENCE_TIER,
        "chronology_verified": False,
        "release_evidence": False,
        "winner_status": "DIAGNOSTIC_ONLY_NO_RELEASE_WINNER",
        "strategies": strategies,
        "average_pairwise_jaccard": (
            mean(row.jaccard for row in overlaps) if overlaps else 1.0
        ),
    }


def _write_checkpoint(
    path: Path,
    *,
    case: LegacyRetrospectiveCase,
    configuration_sha256: str,
    rows: Sequence[LegacyStrategyRow],
    overlaps: Sequence[LegacyOverlapRow],
) -> None:
    unsigned = {
        "schema_version": 2,
        "evidence_tier": EVIDENCE_TIER,
        "chronology_verified": False,
        "drawing_id": case.strategy_input.drawing_id,
        "drawing_number": case.strategy_input.drawing_number,
        "source_data_sha256": case.source_data_sha256,
        "input_sha256": case.strategy_input.input_sha256,
        "configuration_sha256": configuration_sha256,
        "rows": [asdict(row) for row in rows],
        "overlaps": [asdict(row) for row in overlaps],
    }
    _atomic_write(
        path,
        _json_bytes(
            {
                **unsigned,
                "checkpoint_sha256": hashlib.sha256(
                    _canonical_json_bytes(unsigned)
                ).hexdigest(),
            }
        ),
    )


def _load_checkpoint(
    path: Path,
    *,
    case: LegacyRetrospectiveCase,
    configuration_sha256: str,
) -> tuple[tuple[LegacyStrategyRow, ...], tuple[LegacyOverlapRow, ...]]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("legacy checkpoint must be a regular non-symlink file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("legacy checkpoint must be an object")
    checkpoint_sha256 = payload.pop("checkpoint_sha256", None)
    if checkpoint_sha256 != hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest():
        raise ValueError("legacy checkpoint hash mismatch")
    expected = {
        "schema_version": 2,
        "evidence_tier": EVIDENCE_TIER,
        "chronology_verified": False,
        "drawing_id": case.strategy_input.drawing_id,
        "drawing_number": case.strategy_input.drawing_number,
        "source_data_sha256": case.source_data_sha256,
        "input_sha256": case.strategy_input.input_sha256,
        "configuration_sha256": configuration_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("legacy checkpoint does not match current input/config")
    raw_rows = payload.get("rows")
    raw_overlaps = payload.get("overlaps")
    if not isinstance(raw_rows, list) or not isinstance(raw_overlaps, list):
        raise ValueError("legacy checkpoint rows are malformed")
    rows = tuple(_legacy_row_from_json(value) for value in raw_rows)
    overlaps = tuple(LegacyOverlapRow(**value) for value in raw_overlaps)
    if len(rows) != 4 or len(overlaps) != 6:
        raise ValueError("legacy checkpoint strategy cardinality is invalid")
    return rows, overlaps


def _legacy_row_from_json(value: object) -> LegacyStrategyRow:
    if not isinstance(value, dict):
        raise ValueError("legacy checkpoint row must be an object")
    copied = dict(value)
    copied["hit_distribution"] = tuple(
        tuple(item) for item in copied["hit_distribution"]
    )
    copied["category_counts"] = tuple(
        tuple(item) for item in copied["category_counts"]
    )
    copied["zero_exposure_event_orders"] = tuple(
        copied["zero_exposure_event_orders"]
    )
    return LegacyStrategyRow(**copied)


def _actual_outcome(event: Event) -> str:
    if (
        isinstance(event.result, str)
        and event.result.strip().casefold() in {"*", "void", "cancelled", "canceled"}
        and isinstance(event.result_status, str)
        and event.result_status.strip().casefold()
        in {"void", "cancelled", "canceled"}
    ):
        return "*"
    normalized = normalize_result(event.result)
    if normalized is None:
        raise ValueError("legacy drawing has an unsupported actual outcome")
    return normalized


def _quote_triplet(quote: Quote, prefix: str) -> tuple[float, float, float]:
    values = (
        getattr(quote, f"{prefix}_win_1"),
        getattr(quote, f"{prefix}_draw"),
        getattr(quote, f"{prefix}_win_2"),
    )
    return tuple(
        _finite_number(value, f"{prefix} probability", positive=True)
        for value in values
    )


def _resolved_extracted_at(value: datetime | str | None) -> str:
    resolved = datetime.now(timezone.utc) if value is None else value
    parsed = _aware_timestamp(resolved, "extracted_at")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _aware_timestamp(value: datetime | str, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{name} must be an ISO timestamp") from error
    else:
        raise ValueError(f"{name} must be a timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _finite_number(
    value: object,
    name: str,
    *,
    positive: bool,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (float(value) <= 0 if positive else float(value) < 0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be a finite {qualifier} number")
    return float(value)


def _sha256_value(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _rows_csv(rows: Sequence[LegacyStrategyRow]) -> str:
    return _dataclass_csv(LegacyStrategyRow, rows)


def _overlaps_csv(rows: Sequence[LegacyOverlapRow]) -> str:
    return _dataclass_csv(LegacyOverlapRow, rows)


def _dataclass_csv(row_type, rows: Sequence[object]) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    fields = tuple(row_type.__dataclass_fields__)
    writer.writerow(fields)
    for row in rows:
        values = asdict(row)
        writer.writerow(_csv_value(values[field]) for field in fields)
    return stream.getvalue()


def _csv_value(value: object) -> object:
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _markdown(benchmark: LegacyRetrospectiveBenchmark) -> str:
    lines = [
        "# Legacy Retrospective Strategy Diagnostic",
        "",
        "**LEGACY_RETROSPECTIVE — NOT RELEASE EVIDENCE — NOT ACTIONABLE.**",
        "",
        "Current SQLite probabilities do not have proven pre-deadline capture "
        "chronology. This report can reveal large instability, but cannot "
        "prove predictive edge or profitability.",
        "",
        f"- Drawings evaluated: {benchmark.summary['drawings_evaluated']}",
        f"- Resumed from checkpoints: {benchmark.summary['resumed_drawings']}",
        f"- Bank / stake: {benchmark.bank} / {benchmark.stake}",
        "",
        "| Strategy | Avg best | Median best | Hit 13+ | Hit 14+ | Hit 15 | "
        "Avg cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    strategies = benchmark.summary["strategies"]
    if not isinstance(strategies, Mapping):
        raise ValueError("legacy strategy summary must be a mapping")
    for strategy_id in sorted(strategies):
        row = strategies[strategy_id]
        if not isinstance(row, Mapping):
            raise ValueError("legacy strategy summary row must be a mapping")
        lines.append(
            f"| {strategy_id} | {row['average_best_hits']:.3f} | "
            f"{row['median_best_hits']:.3f} | "
            f"{row['hit_13_count']}/{row['drawings']} | "
            f"{row['hit_14_count']}/{row['drawings']} | "
            f"{row['hit_15_count']}/{row['drawings']} | "
            f"{row['average_cost']:.2f} |"
        )
    lines.extend(
        (
            "",
            "No result in this report may be aggregated into strict or "
            "prospective release metrics.",
            "",
        )
    )
    return "\n".join(lines)


def _artifact(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
