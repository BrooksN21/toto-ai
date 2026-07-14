"""Chronological modeled-EV backtesting with frozen holdout exclusion."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from statistics import fmean

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.ev.drawing import SELF_DILUTION_LIMIT
from toto_ai.ev.models import EVComponents, EVInput, EVSurface
from toto_ai.ev.package import rank_coupon_indices
from toto_ai.ev.prize import normalize_triplet, smooth_crowd_matrix, validate_bank
from toto_ai.ev.ternary import (
    compute_ev_components,
    coupon_from_index,
    materialize_ev_surface,
)
from toto_ai.optimizer.strategy_backtest import load_strategy_experiment_manifest

DEFAULT_PRIZE_FUND_FACTORS = (0.7, 0.8, 0.9, 1.0)
EMPTY_PACKAGE_HASH = hashlib.sha256(b"").hexdigest()
ProgressCallback = Callable[[dict[str, object]], None]
SurfaceBuilder = Callable[..., EVComponents | EVSurface]


@dataclass(frozen=True)
class EVBacktestConfig:
    banks: tuple[int, ...]
    thresholds: tuple[float, ...]
    stake: int
    prize_fund_factors: tuple[float, ...] = DEFAULT_PRIZE_FUND_FACTORS

    def __post_init__(self) -> None:
        banks = tuple(self.banks)
        thresholds = _finite_tuple("thresholds", self.thresholds)
        factors = _finite_tuple(
            "prize_fund_factors",
            self.prize_fund_factors,
            non_negative=True,
        )
        if not banks:
            raise ValueError("banks must not be empty")
        if not thresholds:
            raise ValueError("thresholds must not be empty")
        if not factors:
            raise ValueError("prize_fund_factors must not be empty")
        for bank in banks:
            validate_bank(bank, self.stake)
        _require_unique("banks", banks)
        _require_unique("thresholds", thresholds)
        _require_unique("prize_fund_factors", factors)
        object.__setattr__(self, "banks", banks)
        object.__setattr__(self, "thresholds", thresholds)
        object.__setattr__(self, "prize_fund_factors", factors)


@dataclass(frozen=True)
class EVBacktestRow:
    drawing_id: int
    drawing_number: int | None
    bank: int
    threshold: float
    prize_fund_factor: float
    decision: str
    selected_coupons: int
    cost: int
    unused_bank: int
    package_expected_payout: float
    package_modeled_roi: float | None
    self_dilution_ratio: float
    model_supported: bool
    best_hits: int | None
    hit_9: bool
    hit_10: bool
    hit_11: bool
    hit_12: bool
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_hash: str


@dataclass(frozen=True)
class EVBacktestSummary:
    bank: int
    threshold: float
    prize_fund_factor: float
    drawing_count: int
    play_count: int
    no_bet_count: int
    unsupported_count: int
    skip_rate: float
    average_selected_coupons: float
    average_bank_utilization: float
    average_package_expected_payout: float
    average_package_modeled_roi: float | None
    average_best_hits: float | None
    hit_9_rate: float
    hit_10_rate: float
    hit_11_rate: float
    hit_12_rate: float
    hit_13_rate: float
    hit_14_rate: float
    hit_15_rate: float
    model_review_required: bool


@dataclass(frozen=True)
class EVBacktestResult:
    config: EVBacktestConfig
    rows: tuple[EVBacktestRow, ...]
    summaries: tuple[EVBacktestSummary, ...]
    drawing_ids: tuple[int, ...]
    processed_drawing_ids: tuple[int, ...]
    skipped_drawing_ids: tuple[int, ...]
    elapsed_seconds: float
    configuration_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "summaries", tuple(self.summaries))
        object.__setattr__(self, "drawing_ids", tuple(self.drawing_ids))
        object.__setattr__(
            self,
            "processed_drawing_ids",
            tuple(self.processed_drawing_ids),
        )
        object.__setattr__(
            self,
            "skipped_drawing_ids",
            tuple(self.skipped_drawing_ids),
        )


@dataclass(frozen=True)
class _PendingPackage:
    drawing_id: int
    drawing_number: int | None
    bank: int
    threshold: float
    prize_fund_factor: float
    decision: str
    coupons: tuple[str, ...]
    cost: int
    unused_bank: int
    expected_payout: float
    modeled_roi: float | None
    self_dilution_ratio: float
    model_supported: bool
    package_hash: str


def load_frozen_holdout_ids(path: str | Path) -> frozenset[int]:
    """Return the final validated holdout IDs from a strategy manifest."""
    manifest = load_strategy_experiment_manifest(path)
    drawing_ids = manifest["drawing_ids"]
    if not isinstance(drawing_ids, list) or not all(
        type(drawing_id) is int and drawing_id > 0 for drawing_id in drawing_ids
    ):
        raise ValueError("Manifest drawing_ids must be positive integers.")
    if len(set(drawing_ids)) != len(drawing_ids):
        raise ValueError("Manifest drawing_ids must not contain duplicates.")
    last = manifest.get("last")
    if type(last) is not int or last != len(drawing_ids):
        raise ValueError("Manifest last must equal the drawing_ids count.")
    holdout_size = manifest.get("holdout_size")
    if type(holdout_size) is not int:
        raise ValueError("Manifest holdout_size must be an integer.")
    if holdout_size <= 0:
        raise ValueError("Manifest holdout_size must be positive.")
    if holdout_size > len(drawing_ids):
        raise ValueError("Manifest holdout_size cannot exceed drawing_ids count.")
    return frozenset(drawing_ids[-holdout_size:])


def ev_backtest_configuration_hash(
    config: EVBacktestConfig,
    *,
    last: int,
    forbidden_drawing_ids: frozenset[int],
    community: str = "baltbet-main",
) -> str:
    """Hash every setting that determines a resumable backtest window."""
    if not isinstance(config, EVBacktestConfig):
        raise ValueError("config must be an EVBacktestConfig")
    if type(last) is not int or last <= 0:
        raise ValueError("last must be a positive integer")
    if not isinstance(community, str) or not community:
        raise ValueError("community must be a non-empty string")
    forbidden = frozenset(forbidden_drawing_ids)
    if not all(type(drawing_id) is int and drawing_id > 0 for drawing_id in forbidden):
        raise ValueError("forbidden drawing IDs must be positive integers")
    payload = {
        "config": asdict(config),
        "last": last,
        "community": community,
        "forbidden_drawing_ids": sorted(forbidden),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def ev_backtest_checkpoint_path(
    configuration_hash: str,
    *,
    last: int,
    stake: int,
    report_dir: str | Path = "reports",
) -> Path:
    """Return a deterministic checkpoint path scoped to the exact config."""
    _validate_sha256(configuration_hash, "configuration_hash")
    if type(last) is not int or last <= 0:
        raise ValueError("last must be a positive integer")
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive integer")
    return Path(report_dir) / (
        f"ev_backtest_last_{last}_stake_{stake}_config_"
        f"{configuration_hash}.partial.csv"
    )


def run_ev_backtest(
    session: Session,
    *,
    last: int,
    banks: Iterable[int],
    thresholds: Iterable[float],
    stake: int,
    forbidden_drawing_ids: frozenset[int],
    prize_fund_factors: Iterable[float] = DEFAULT_PRIZE_FUND_FACTORS,
    community: str = "baltbet-main",
    progress_callback: ProgressCallback | None = None,
    surface_builder: SurfaceBuilder = compute_ev_components,
    checkpoint_path: str | Path | None = None,
) -> EVBacktestResult:
    """Evaluate the latest result-complete drawings without result leakage."""
    forbidden = frozenset(forbidden_drawing_ids)
    config = EVBacktestConfig(
        banks=tuple(banks),
        thresholds=tuple(thresholds),
        stake=stake,
        prize_fund_factors=tuple(prize_fund_factors),
    )
    configuration_hash = ev_backtest_configuration_hash(
        config,
        last=last,
        community=community,
        forbidden_drawing_ids=forbidden,
    )
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    checkpoint_rows, _, checkpoint_packages = _load_checkpoint(
        checkpoint,
        config,
        configuration_hash,
    )

    started_at = time.perf_counter()
    candidates = _load_candidate_drawings(session, community, forbidden)
    candidate_by_id = {drawing.id: drawing for drawing in candidates}
    checkpoint_by_id: dict[int, tuple[EVBacktestRow, ...]] = {}
    for row in checkpoint_rows:
        checkpoint_by_id.setdefault(row.drawing_id, ())
        checkpoint_by_id[row.drawing_id] += (row,)
    if not set(checkpoint_by_id) <= set(candidate_by_id):
        raise ValueError("Checkpoint drawings do not match the current configuration")

    rows: list[EVBacktestRow] = []
    processed_ids: list[int] = []
    skipped_ids: list[int] = []
    package_manifests: dict[str, tuple[str, ...]] = {}
    total = len(candidates)
    for index, drawing in enumerate(candidates, start=1):
        if len(processed_ids) == last:
            break
        resumed_rows = checkpoint_by_id.get(drawing.id)
        if resumed_rows is not None:
            rows.extend(resumed_rows)
            for row in resumed_rows:
                _register_package_manifest(
                    package_manifests,
                    row.package_hash,
                    checkpoint_packages[row.package_hash],
                )
            processed_ids.append(drawing.id)
            _notify(
                progress_callback,
                _progress_payload("drawing_resumed", drawing, index, total, started_at),
            )
            continue

        try:
            ev_input = _load_ev_input(session, drawing, stake)
        except (TypeError, ValueError):
            _append_unique(skipped_ids, drawing.id)
            _write_checkpoint(
                checkpoint,
                rows,
                skipped_ids,
                configuration_hash,
                package_manifests,
            )
            _notify(
                progress_callback,
                _progress_payload(
                    "drawing_skipped",
                    drawing,
                    index,
                    total,
                    started_at,
                ),
            )
            continue

        _notify(
            progress_callback,
            _progress_payload("drawing", drawing, index, total, started_at),
        )

        def category_progress(
            update: dict[str, object],
            current_drawing: Drawing = drawing,
            current_index: int = index,
        ) -> None:
            payload = _progress_payload(
                str(update.get("phase", "category")),
                current_drawing,
                current_index,
                total,
                started_at,
            )
            payload.update(update)
            _notify(progress_callback, payload)

        reusable = surface_builder(
            ev_input,
            progress_callback=(
                category_progress if progress_callback is not None else None
            ),
        )
        pending = _build_pending_packages(ev_input, reusable, config)
        _notify(
            progress_callback,
            {
                **_progress_payload(
                    "packages_ready",
                    drawing,
                    index,
                    total,
                    started_at,
                ),
                "package_hashes": tuple(item.package_hash for item in pending),
            },
        )

        actual_result = _load_actual_result(session, drawing.id)
        if actual_result is None:
            _append_unique(skipped_ids, drawing.id)
            _write_checkpoint(
                checkpoint,
                rows,
                skipped_ids,
                configuration_hash,
                package_manifests,
            )
            _notify(
                progress_callback,
                _progress_payload(
                    "drawing_skipped",
                    drawing,
                    index,
                    total,
                    started_at,
                ),
            )
            continue

        drawing_rows = tuple(
            _realized_row(item, actual_result) for item in pending
        )
        for item in pending:
            _register_package_manifest(
                package_manifests,
                item.package_hash,
                item.coupons,
            )
        rows.extend(drawing_rows)
        processed_ids.append(drawing.id)
        _write_checkpoint(
            checkpoint,
            rows,
            skipped_ids,
            configuration_hash,
            package_manifests,
        )
        _notify(
            progress_callback,
            _progress_payload(
                "drawing_complete",
                drawing,
                index,
                total,
                started_at,
            ),
        )

    _write_checkpoint(
        checkpoint,
        rows,
        skipped_ids,
        configuration_hash,
        package_manifests,
    )
    chronological_drawings = sorted(
        (candidate_by_id[drawing_id] for drawing_id in processed_ids),
        key=_chronology_key,
    )
    chronological_order = {
        drawing.id: index for index, drawing in enumerate(chronological_drawings)
    }
    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda row: (
                chronological_order[row.drawing_id],
                config.prize_fund_factors.index(row.prize_fund_factor),
                config.thresholds.index(row.threshold),
                config.banks.index(row.bank),
            ),
        )
    )
    ordered_processed = tuple(drawing.id for drawing in chronological_drawings)
    return EVBacktestResult(
        config=config,
        rows=ordered_rows,
        summaries=summarize_ev_backtest(ordered_rows, config),
        drawing_ids=ordered_processed,
        processed_drawing_ids=ordered_processed,
        skipped_drawing_ids=tuple(skipped_ids),
        elapsed_seconds=time.perf_counter() - started_at,
        configuration_hash=configuration_hash,
    )


def summarize_ev_backtest(
    rows: Iterable[EVBacktestRow],
    config: EVBacktestConfig,
) -> tuple[EVBacktestSummary, ...]:
    """Aggregate one summary for every factor, threshold, and dynamic bank."""
    selected_rows = tuple(rows)
    summaries = []
    for factor in config.prize_fund_factors:
        for threshold in config.thresholds:
            for bank in config.banks:
                group = tuple(
                    row
                    for row in selected_rows
                    if row.bank == bank
                    and row.threshold == threshold
                    and row.prize_fund_factor == factor
                )
                drawing_count = len(group)
                play_count = sum(row.decision == "PLAY" for row in group)
                no_bet_count = sum(row.decision == "NO BET" for row in group)
                unsupported_count = sum(not row.model_supported for row in group)
                roi_values = tuple(
                    row.package_modeled_roi
                    for row in group
                    if row.package_modeled_roi is not None
                )
                best_hits = tuple(
                    row.best_hits for row in group if row.best_hits is not None
                )
                skip_rate = no_bet_count / drawing_count if drawing_count else 0.0
                summaries.append(
                    EVBacktestSummary(
                        bank=bank,
                        threshold=threshold,
                        prize_fund_factor=factor,
                        drawing_count=drawing_count,
                        play_count=play_count,
                        no_bet_count=no_bet_count,
                        unsupported_count=unsupported_count,
                        skip_rate=skip_rate,
                        average_selected_coupons=_average(
                            row.selected_coupons for row in group
                        ),
                        average_bank_utilization=_average(
                            row.cost / row.bank for row in group
                        ),
                        average_package_expected_payout=_average(
                            row.package_expected_payout for row in group
                        ),
                        average_package_modeled_roi=(
                            fmean(roi_values) if roi_values else None
                        ),
                        average_best_hits=(fmean(best_hits) if best_hits else None),
                        hit_9_rate=_hit_rate(group, 9),
                        hit_10_rate=_hit_rate(group, 10),
                        hit_11_rate=_hit_rate(group, 11),
                        hit_12_rate=_hit_rate(group, 12),
                        hit_13_rate=_hit_rate(group, 13),
                        hit_14_rate=_hit_rate(group, 14),
                        hit_15_rate=_hit_rate(group, 15),
                        model_review_required=skip_rate > 0.80,
                    )
                )
    return tuple(summaries)


def _load_candidate_drawings(
    session: Session,
    community: str,
    forbidden: frozenset[int],
) -> list[Drawing]:
    statement = (
        select(Drawing)
        .where(Drawing.name == community)
        .where(Drawing.status == "finished")
    )
    if forbidden:
        statement = statement.where(Drawing.id.not_in(sorted(forbidden)))
    drawings = list(session.scalars(statement).all())
    return sorted(drawings, key=_chronology_key, reverse=True)


def _load_ev_input(session: Session, drawing: Drawing, stake: int) -> EVInput:
    rows = session.execute(
        select(
            Event.event_order,
            Quote.bk_win_1,
            Quote.bk_draw,
            Quote.bk_win_2,
            Quote.pool_win_1,
            Quote.pool_draw,
            Quote.pool_win_2,
        )
        .join(
            Quote,
            and_(
                Quote.drawing_id == Event.drawing_id,
                Quote.event_order == Event.event_order,
            ),
        )
        .where(Event.drawing_id == drawing.id)
        .order_by(Event.event_order)
    ).all()
    orders = [row[0] for row in rows]
    if len(rows) != 15 or orders != list(range(15)):
        raise ValueError("drawing must contain exactly ordered events 0 through 14")
    pool_sum = _finite_number("pool_sum", drawing.pool_sum, positive=True)
    jackpot = _finite_number("jackpot", drawing.jackpot, positive=False)
    true_probabilities = tuple(
        normalize_triplet(tuple(_quote_number(value) for value in row[1:4]))
        for row in rows
    )
    crowd_rows = tuple(
        normalize_triplet(tuple(_quote_number(value) for value in row[4:7]))
        for row in rows
    )
    return EVInput(
        drawing_id=drawing.id,
        drawing_number=drawing.number,
        true_probabilities=true_probabilities,
        crowd_probabilities=smooth_crowd_matrix(crowd_rows, pool_sum, stake),
        pool_sum=pool_sum,
        jackpot=jackpot,
        possible_winnings=pool_sum,
        probability_sources=("totobrief_bk",) * 15,
        fetched_at=drawing.ended_at or "historical-db",
    )


def _build_pending_packages(
    ev_input: EVInput,
    reusable: EVComponents | EVSurface,
    config: EVBacktestConfig,
) -> tuple[_PendingPackage, ...]:
    if not isinstance(reusable, (EVComponents, EVSurface)):
        raise ValueError("surface_builder must return EVComponents or EVSurface")
    pending = []
    for factor in config.prize_fund_factors:
        surface = (
            materialize_ev_surface(
                reusable,
                ev_input.pool_sum * factor,
                ev_input.jackpot,
            )
            if isinstance(reusable, EVComponents)
            else reusable
        )
        order = rank_coupon_indices(surface)
        if order.ndim != 1 or order.size != surface.gross_ev.size:
            raise ValueError("complete surface ranking must include every coupon")
        ordered_values = surface.gross_ev[order]
        for threshold in config.thresholds:
            eligible_positions = np.flatnonzero(ordered_values >= threshold)
            for bank in config.banks:
                maximum = validate_bank(bank, config.stake)
                selected_indices = order[eligible_positions[:maximum]]
                proposed_coupons = tuple(
                    coupon_from_index(int(index), surface.event_count)
                    for index in selected_indices
                )
                proposed_cost = len(proposed_coupons) * config.stake
                proposed_payout = float(
                    surface.gross_ev[selected_indices].sum(dtype=np.float64)
                    * config.stake
                )
                self_dilution_ratio = proposed_cost / ev_input.pool_sum
                model_supported = self_dilution_ratio <= SELF_DILUTION_LIMIT
                coupons = (
                    proposed_coupons
                    if model_supported or not proposed_coupons
                    else ()
                )
                cost = proposed_cost if coupons else 0
                expected_payout = proposed_payout if coupons else 0.0
                pending.append(
                    _PendingPackage(
                        drawing_id=ev_input.drawing_id,
                        drawing_number=ev_input.drawing_number,
                        bank=bank,
                        threshold=threshold,
                        prize_fund_factor=factor,
                        decision="PLAY" if coupons else "NO BET",
                        coupons=coupons,
                        cost=cost,
                        unused_bank=bank - cost,
                        expected_payout=expected_payout,
                        modeled_roi=(
                            expected_payout / cost - 1.0 if cost else None
                        ),
                        self_dilution_ratio=self_dilution_ratio,
                        model_supported=model_supported,
                        package_hash=_package_hash(coupons),
                    )
                )
    return tuple(pending)


def _load_actual_result(session: Session, drawing_id: int) -> str | None:
    rows = session.execute(
        select(Event.event_order, Event.result)
        .where(Event.drawing_id == drawing_id)
        .order_by(Event.event_order)
    ).all()
    if len(rows) != 15 or [row[0] for row in rows] != list(range(15)):
        return None
    normalized = tuple(normalize_result(row[1]) for row in rows)
    if any(outcome is None for outcome in normalized):
        return None
    return "".join(outcome for outcome in normalized if outcome is not None)


def _realized_row(pending: _PendingPackage, actual_result: str) -> EVBacktestRow:
    best_hits = (
        max(
            sum(
                left == right
                for left, right in zip(coupon, actual_result, strict=True)
            )
            for coupon in pending.coupons
        )
        if pending.coupons
        else None
    )
    return EVBacktestRow(
        drawing_id=pending.drawing_id,
        drawing_number=pending.drawing_number,
        bank=pending.bank,
        threshold=pending.threshold,
        prize_fund_factor=pending.prize_fund_factor,
        decision=pending.decision,
        selected_coupons=len(pending.coupons),
        cost=pending.cost,
        unused_bank=pending.unused_bank,
        package_expected_payout=pending.expected_payout,
        package_modeled_roi=pending.modeled_roi,
        self_dilution_ratio=pending.self_dilution_ratio,
        model_supported=pending.model_supported,
        best_hits=best_hits,
        hit_9=best_hits is not None and best_hits >= 9,
        hit_10=best_hits is not None and best_hits >= 10,
        hit_11=best_hits is not None and best_hits >= 11,
        hit_12=best_hits is not None and best_hits >= 12,
        hit_13=best_hits is not None and best_hits >= 13,
        hit_14=best_hits is not None and best_hits >= 14,
        hit_15=best_hits is not None and best_hits >= 15,
        package_hash=pending.package_hash,
    )


_CHECKPOINT_PREFIX_FIELDS = (
    "record_type",
    "configuration_hash",
    "skip_reason",
    "coupon_payload",
)
_ROW_FIELDS = tuple(EVBacktestRow.__dataclass_fields__)
_CHECKPOINT_FIELDS = _CHECKPOINT_PREFIX_FIELDS + _ROW_FIELDS


def _write_checkpoint(
    path: Path | None,
    rows: Iterable[EVBacktestRow],
    skipped_ids: Iterable[int],
    configuration_hash: str,
    package_manifests: dict[str, tuple[str, ...]],
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as output:
        temporary_path = Path(output.name)
        writer = csv.DictWriter(output, fieldnames=_CHECKPOINT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "record_type": "row",
                    "configuration_hash": configuration_hash,
                    "skip_reason": "",
                    "coupon_payload": "",
                    **asdict(row),
                }
            )
        for drawing_id in skipped_ids:
            writer.writerow(
                {
                    "record_type": "skip",
                    "configuration_hash": configuration_hash,
                    "skip_reason": "ineligible_or_incomplete",
                    "coupon_payload": "",
                    "drawing_id": drawing_id,
                }
            )
        for package_hash in sorted(package_manifests):
            writer.writerow(
                {
                    "record_type": "package",
                    "configuration_hash": configuration_hash,
                    "skip_reason": "",
                    "coupon_payload": ",".join(
                        package_manifests[package_hash]
                    ),
                    "package_hash": package_hash,
                }
            )
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_checkpoint(
    path: Path | None,
    config: EVBacktestConfig,
    configuration_hash: str,
) -> tuple[
    tuple[EVBacktestRow, ...],
    tuple[int, ...],
    dict[str, tuple[str, ...]],
]:
    if path is None or not path.exists():
        return (), (), {}
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != _CHECKPOINT_FIELDS:
            raise ValueError("Invalid EV backtest checkpoint header")
        records = list(reader)
    if any(row["configuration_hash"] != configuration_hash for row in records):
        raise ValueError("Checkpoint configuration does not match this run")
    if any(
        record["record_type"] not in {"row", "skip", "package"}
        for record in records
    ):
        raise ValueError("Invalid EV backtest checkpoint record type")
    try:
        rows = tuple(
            _checkpoint_row(record)
            for record in records
            if record["record_type"] == "row"
        )
        skipped = tuple(
            _checkpoint_skip_id(record)
            for record in records
            if record["record_type"] == "skip"
        )
        package_records = tuple(
            _checkpoint_package(record)
            for record in records
            if record["record_type"] == "package"
        )
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid EV backtest checkpoint row: {error}") from error
    package_hashes = tuple(package_hash for package_hash, _ in package_records)
    if len(set(package_hashes)) != len(package_hashes):
        raise ValueError("Checkpoint package manifests must not contain duplicates")
    packages = dict(package_records)
    if len(set(skipped)) != len(skipped):
        raise ValueError("Checkpoint skip records must not contain duplicates")
    if {row.drawing_id for row in rows} & set(skipped):
        raise ValueError("Checkpoint drawing cannot be both completed and skipped")

    by_drawing: dict[int, list[EVBacktestRow]] = {}
    for row in rows:
        by_drawing.setdefault(row.drawing_id, []).append(row)
        _validate_checkpoint_row(row, config)
    expected_grid = set(
        product(
            config.banks,
            config.thresholds,
            config.prize_fund_factors,
        )
    )
    for group in by_drawing.values():
        actual_grid = {
            (row.bank, row.threshold, row.prize_fund_factor) for row in group
        }
        if len(group) != len(expected_grid) or actual_grid != expected_grid:
            raise ValueError(
                "Checkpoint completed drawing must contain the exact unique "
                "Cartesian grid"
            )
        if len({row.drawing_number for row in group}) != 1:
            raise ValueError(
                "Checkpoint drawing_number must be stable within a drawing"
            )
    referenced_hashes = {row.package_hash for row in rows}
    missing_hashes = referenced_hashes - packages.keys()
    if missing_hashes:
        raise ValueError("Checkpoint row references a missing package manifest")
    orphan_hashes = packages.keys() - referenced_hashes
    if orphan_hashes:
        raise ValueError("Checkpoint contains an orphan package manifest")
    for row in rows:
        coupons = packages[row.package_hash]
        if len(coupons) != row.selected_coupons:
            raise ValueError(
                "Checkpoint package coupon count contradicts selected_coupons"
            )
        if row.decision == "PLAY" and not coupons:
            raise ValueError("Checkpoint PLAY row references an empty package")
        if row.decision == "NO BET" and coupons:
            raise ValueError("Checkpoint NO BET row references a non-empty package")
    return rows, skipped, packages


def _checkpoint_row(record: dict[str, str]) -> EVBacktestRow:
    if record["skip_reason"] or record["coupon_payload"]:
        raise ValueError("completed rows must not contain checkpoint metadata")
    return EVBacktestRow(
        drawing_id=int(record["drawing_id"]),
        drawing_number=(
            int(record["drawing_number"]) if record["drawing_number"] else None
        ),
        bank=int(record["bank"]),
        threshold=float(record["threshold"]),
        prize_fund_factor=float(record["prize_fund_factor"]),
        decision=record["decision"],
        selected_coupons=int(record["selected_coupons"]),
        cost=int(record["cost"]),
        unused_bank=int(record["unused_bank"]),
        package_expected_payout=float(record["package_expected_payout"]),
        package_modeled_roi=(
            float(record["package_modeled_roi"])
            if record["package_modeled_roi"]
            else None
        ),
        self_dilution_ratio=float(record["self_dilution_ratio"]),
        model_supported=_parse_bool(record["model_supported"]),
        best_hits=int(record["best_hits"]) if record["best_hits"] else None,
        hit_9=_parse_bool(record["hit_9"]),
        hit_10=_parse_bool(record["hit_10"]),
        hit_11=_parse_bool(record["hit_11"]),
        hit_12=_parse_bool(record["hit_12"]),
        hit_13=_parse_bool(record["hit_13"]),
        hit_14=_parse_bool(record["hit_14"]),
        hit_15=_parse_bool(record["hit_15"]),
        package_hash=record["package_hash"],
    )


def _checkpoint_skip_id(record: dict[str, str]) -> int:
    drawing_id = int(record["drawing_id"])
    if drawing_id <= 0:
        raise ValueError("skip drawing_id must be positive")
    if record["skip_reason"] != "ineligible_or_incomplete":
        raise ValueError("skip reason is invalid")
    if record["coupon_payload"]:
        raise ValueError("skip records must not contain coupon payloads")
    if any(
        record[field]
        for field in _ROW_FIELDS
        if field != "drawing_id"
    ):
        raise ValueError("skip records must not contain completed row fields")
    return drawing_id


def _checkpoint_package(record: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    if record["skip_reason"]:
        raise ValueError("package manifests must not contain a skip reason")
    if any(record[field] for field in _ROW_FIELDS if field != "package_hash"):
        raise ValueError("package manifests must not contain completed row fields")
    payload = record["coupon_payload"]
    coupons = tuple(payload.split(",")) if payload else ()
    if len(set(coupons)) != len(coupons):
        raise ValueError("package manifest coupons must not contain duplicates")
    if any(
        len(coupon) != 15 or set(coupon) - {"1", "X", "2"}
        for coupon in coupons
    ):
        raise ValueError("package manifest coupons must be 15 outcomes in 1/X/2")
    package_hash = record["package_hash"]
    _validate_sha256(package_hash, "package_hash")
    if _package_hash(coupons) != package_hash:
        raise ValueError("Checkpoint package hash does not match coupon payload")
    return package_hash, coupons


def _register_package_manifest(
    manifests: dict[str, tuple[str, ...]],
    package_hash: str,
    coupons: tuple[str, ...],
) -> None:
    existing = manifests.get(package_hash)
    if existing is not None and existing != coupons:
        raise ValueError("Conflicting coupon payloads share a package hash")
    manifests[package_hash] = coupons


def _package_hash(coupons: tuple[str, ...]) -> str:
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def _validate_checkpoint_row(
    row: EVBacktestRow,
    config: EVBacktestConfig,
) -> None:
    if row.drawing_id <= 0:
        raise ValueError("Checkpoint drawing_id must be positive")
    if row.bank not in config.banks:
        raise ValueError("Checkpoint bank is outside the configuration")
    if row.threshold not in config.thresholds:
        raise ValueError("Checkpoint threshold is outside the configuration")
    if row.prize_fund_factor not in config.prize_fund_factors:
        raise ValueError("Checkpoint factor is outside the configuration")
    if row.decision not in {"PLAY", "NO BET"}:
        raise ValueError("Checkpoint decision must be PLAY or NO BET")
    maximum = validate_bank(row.bank, config.stake)
    if not 0 <= row.selected_coupons <= maximum:
        raise ValueError("Checkpoint selected_coupons exceeds the bank cap")
    if row.cost != row.selected_coupons * config.stake:
        raise ValueError("Checkpoint cost does not match selected coupons")
    if row.unused_bank != row.bank - row.cost:
        raise ValueError("Checkpoint unused_bank does not match cost")
    if (
        not math.isfinite(row.package_expected_payout)
        or row.package_expected_payout < 0.0
    ):
        raise ValueError("Checkpoint package expected payout must be non-negative")
    if (
        not math.isfinite(row.self_dilution_ratio)
        or row.self_dilution_ratio < 0.0
    ):
        raise ValueError("Checkpoint self-dilution ratio must be non-negative")
    if row.model_supported != (
        row.self_dilution_ratio <= SELF_DILUTION_LIMIT
    ):
        raise ValueError("Checkpoint model support contradicts self-dilution")
    _validate_sha256(row.package_hash, "package_hash")

    expected_hits = tuple(
        row.best_hits is not None and row.best_hits >= hits
        for hits in range(9, 16)
    )
    actual_hits = tuple(getattr(row, f"hit_{hits}") for hits in range(9, 16))
    if actual_hits != expected_hits:
        raise ValueError("Checkpoint hit indicators contradict best_hits")

    if row.decision == "NO BET":
        if (
            row.selected_coupons != 0
            or row.cost != 0
            or row.unused_bank != row.bank
            or row.package_expected_payout != 0.0
            or row.package_modeled_roi is not None
            or row.best_hits is not None
            or row.package_hash != EMPTY_PACKAGE_HASH
        ):
            raise ValueError("Checkpoint NO BET row invariants are invalid")
        return

    if not row.model_supported:
        raise ValueError("Checkpoint PLAY row cannot use an unsupported model")
    if row.selected_coupons == 0 or row.best_hits is None:
        raise ValueError("Checkpoint PLAY row must contain coupons and best_hits")
    if not 0 <= row.best_hits <= 15:
        raise ValueError("Checkpoint best_hits must be in 0..15")
    expected_roi = row.package_expected_payout / row.cost - 1.0
    if (
        row.package_modeled_roi is None
        or not math.isfinite(row.package_modeled_roi)
        or not math.isclose(
            row.package_modeled_roi,
            expected_roi,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    ):
        raise ValueError("Checkpoint modeled ROI contradicts payout and cost")


def _chronology_key(drawing: Drawing) -> tuple[str, int, int]:
    number = drawing.number if drawing.number is not None else drawing.id
    return drawing.ended_at or "", number, drawing.id


def _progress_payload(
    phase: str,
    drawing: Drawing,
    index: int,
    total: int,
    started_at: float,
) -> dict[str, object]:
    elapsed = time.perf_counter() - started_at
    average = elapsed / index if index else 0.0
    return {
        "phase": phase,
        "drawing_id": drawing.id,
        "drawing_number": drawing.number,
        "drawing_index": index,
        "drawing_total": total,
        "elapsed_seconds": elapsed,
        "eta_seconds": average * (total - index),
    }


def _finite_tuple(
    name: str,
    values: Iterable[float],
    *,
    non_negative: bool = False,
) -> tuple[float, ...]:
    converted = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError(f"{name} must contain finite numbers")
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(f"{name} must contain finite numbers") from error
        if not math.isfinite(number) or (non_negative and number < 0.0):
            raise ValueError(f"{name} must contain finite non-negative numbers")
        converted.append(number)
    return tuple(converted)


def _finite_number(name: str, value: object, *, positive: bool) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(number) or (number <= 0.0 if positive else number < 0.0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return number


def _quote_number(value: object) -> float:
    return _finite_number("probability", value, positive=False)


def _require_unique(name: str, values: tuple[object, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


def _average(values: Iterable[float]) -> float:
    materialized = tuple(values)
    return fmean(materialized) if materialized else 0.0


def _hit_rate(rows: tuple[EVBacktestRow, ...], hits: int) -> float:
    return (
        sum(getattr(row, f"hit_{hits}") for row in rows) / len(rows)
        if rows
        else 0.0
    )


def _append_unique(values: list[int], value: int) -> None:
    if value not in values:
        values.append(value)


def _parse_bool(value: str) -> bool:
    if value not in {"True", "False"}:
        raise ValueError("Invalid checkpoint boolean")
    return value == "True"


def _validate_sha256(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _notify(callback: ProgressCallback | None, payload: dict[str, object]) -> None:
    if callback is not None:
        callback(payload)
