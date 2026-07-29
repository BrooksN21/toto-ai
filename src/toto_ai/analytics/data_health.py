"""Versioned, read-only data-health contract for TotoAI drawing data."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.db.models import (
    ArchivedPackage,
    Drawing,
    DrawingResultSnapshot,
    Event,
    PackageSettlement,
    Quote,
)

DATA_HEALTH_CONTRACT_VERSION = "1.0.0"
DATA_HEALTH_REPORT_SCHEMA_VERSION = 1
DATA_QUALITY_EXIT_CODE = 3
EXECUTION_ERROR_EXIT_CODE = 4
EXPECTED_EVENT_ORDERS = frozenset(range(15))
DECIDED_RESULTS = frozenset(("1", "X", "2"))
VOID_RESULTS = frozenset(("*", "void", "cancelled", "canceled"))
USE_CASES = (
    "historical_inventory",
    "backtest_probability",
    "result_settlement",
    "prospective_generation",
)
DataHealthUseCase = Literal[
    "historical_inventory",
    "backtest_probability",
    "result_settlement",
    "prospective_generation",
]

REASON_ORDER = (
    "invalid_event_count_order",
    "empty_event_names",
    "missing_quotes",
    "invalid_zero_pool",
    "incomplete_bk",
    "all_results_missing",
    "incomplete_results",
    "missing_raw_snapshot",
    "missing_result_snapshot",
    "unsettled_package",
)

BLOCKING_REASONS: Mapping[DataHealthUseCase, frozenset[str]] = {
    "historical_inventory": frozenset(
        (
            "invalid_event_count_order",
            "empty_event_names",
            "missing_quotes",
            "invalid_zero_pool",
            "incomplete_bk",
            "all_results_missing",
            "incomplete_results",
            "missing_raw_snapshot",
            "missing_result_snapshot",
            "unsettled_package",
        )
    ),
    "backtest_probability": frozenset(
        (
            "invalid_event_count_order",
            "empty_event_names",
            "missing_quotes",
            "invalid_zero_pool",
            "incomplete_bk",
            "all_results_missing",
            "incomplete_results",
        )
    ),
    "result_settlement": frozenset(
        (
            "invalid_event_count_order",
            "all_results_missing",
            "incomplete_results",
            "missing_result_snapshot",
            "unsettled_package",
        )
    ),
    "prospective_generation": frozenset(
        (
            "invalid_event_count_order",
            "empty_event_names",
            "missing_quotes",
            "invalid_zero_pool",
            "incomplete_bk",
        )
    ),
}


class DataHealthFailure(ValueError):
    """Raised when a mandatory data-health gate fails closed."""

    def __init__(self, report: DataHealthReport) -> None:
        self.report = report
        reasons = ", ".join(
            f"{reason}={count}"
            for reason, count in report.summary.reason_counts.items()
        )
        super().__init__(
            f"data-health {report.use_case} failed "
            f"({report.summary.unhealthy_drawings}/"
            f"{report.summary.total_drawings} unhealthy"
            + (f"; {reasons}" if reasons else "")
            + ")"
        )


@dataclass(frozen=True)
class DrawingHealth:
    drawing_id: int
    drawing_number: int | None
    drawing_status: str
    event_count: int
    event_orders: tuple[int, ...]
    nonblank_name_count: int
    quote_count: int
    valid_pool_count: int
    zero_pool_count: int
    complete_bk_count: int
    terminal_result_count: int
    void_result_count: int
    result_snapshot_count: int
    complete_result_snapshot_count: int
    raw_snapshot_present: bool
    actionable_package_count: int
    unsettled_actionable_package_count: int
    observed_reason_codes: tuple[str, ...]
    use_case_eligibility: dict[str, bool]
    selected_status: str
    selected_reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DataHealthMetadata:
    selected_min_number: int | None
    selected_max_number: int | None
    gaps: tuple[int, ...]
    duplicates: dict[int, tuple[int, ...]]

    @property
    def healthy(self) -> bool:
        return not self.gaps and not self.duplicates

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_min_number": self.selected_min_number,
            "selected_max_number": self.selected_max_number,
            "gaps": list(self.gaps),
            "duplicates": {
                str(number): list(ids)
                for number, ids in sorted(self.duplicates.items())
            },
            "healthy": self.healthy,
        }


@dataclass(frozen=True)
class DataHealthSummary:
    total_drawings: int
    healthy_drawings: int
    unhealthy_drawings: int
    inventory_counts: dict[str, int]
    use_case_totals: dict[str, dict[str, int]]
    reason_counts: dict[str, int]
    observed_reason_counts: dict[str, int]
    gap_count: int
    duplicate_number_count: int
    strict: bool
    passed: bool
    exit_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DataHealthReport:
    contract_version: str
    report_schema_version: int
    generated_at: str
    community: str
    use_case: DataHealthUseCase
    strict: bool
    selectors: dict[str, int | None]
    summary: DataHealthSummary
    metadata: DataHealthMetadata
    drawings: tuple[DrawingHealth, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "report_schema_version": self.report_schema_version,
            "generated_at": self.generated_at,
            "community": self.community,
            "use_case": self.use_case,
            "strict": self.strict,
            "selectors": self.selectors,
            "summary": self.summary.to_dict(),
            "metadata": self.metadata.to_dict(),
            "drawings": [drawing.to_dict() for drawing in self.drawings],
        }


@dataclass(frozen=True)
class DataHealthGateResult:
    report: DataHealthReport
    override_applied: bool


def audit_data_health(
    session: Session,
    *,
    db_path: str | Path | None = None,
    use_case: DataHealthUseCase | str = "historical_inventory",
    from_drawing: int | None = None,
    to_drawing: int | None = None,
    last: int | None = None,
    strict: bool = True,
    community: str = "baltbet-main",
    drawing_ids: Sequence[int] | None = None,
    raw_snapshot_drawing_ids: Iterable[int] | None = None,
) -> DataHealthReport:
    """Evaluate selected drawings without mutating the database."""
    selected_use_case = _validate_use_case(use_case)
    _validate_selectors(
        from_drawing=from_drawing,
        to_drawing=to_drawing,
        last=last,
        drawing_ids=drawing_ids,
    )

    drawings = list(
        session.scalars(
            select(Drawing)
            .where(Drawing.name == community)
            .order_by(Drawing.number, Drawing.id)
        ).all()
    )
    drawings = _select_drawings(
        drawings,
        from_drawing=from_drawing,
        to_drawing=to_drawing,
        last=last,
        drawing_ids=drawing_ids,
    )
    if not drawings:
        raise ValueError("No drawings matched the selected data-health scope.")

    selected_ids = tuple(drawing.id for drawing in drawings)
    events = _group_by_drawing(
        session.scalars(
            select(Event)
            .where(Event.drawing_id.in_(selected_ids))
            .order_by(Event.drawing_id, Event.event_order, Event.id)
        ).all()
    )
    quotes = _group_by_drawing(
        session.scalars(
            select(Quote)
            .where(Quote.drawing_id.in_(selected_ids))
            .order_by(Quote.drawing_id, Quote.event_order, Quote.id)
        ).all()
    )
    result_snapshots = _group_by_drawing(
        session.scalars(
            select(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.drawing_id.in_(selected_ids))
            .order_by(
                DrawingResultSnapshot.drawing_id,
                DrawingResultSnapshot.retrieved_at,
                DrawingResultSnapshot.id,
            )
        ).all()
    )
    packages = _group_by_drawing(
        session.scalars(
            select(ArchivedPackage).where(
                ArchivedPackage.drawing_id.in_(selected_ids)
            )
        ).all()
    )
    settlements = _group_by_drawing(
        session.scalars(
            select(PackageSettlement).where(
                PackageSettlement.drawing_id.in_(selected_ids)
            )
        ).all()
    )

    raw_ids = (
        set(raw_snapshot_drawing_ids)
        if raw_snapshot_drawing_ids is not None
        else discover_raw_snapshot_drawing_ids(db_path)
    )
    rows = tuple(
        _drawing_health(
            drawing,
            events=events.get(drawing.id, ()),
            quotes=quotes.get(drawing.id, ()),
            result_snapshots=result_snapshots.get(drawing.id, ()),
            packages=packages.get(drawing.id, ()),
            settlements=settlements.get(drawing.id, ()),
            raw_snapshot_present=drawing.id in raw_ids,
            selected_use_case=selected_use_case,
        )
        for drawing in drawings
    )
    metadata = _metadata(
        drawings,
        from_drawing=from_drawing,
        to_drawing=to_drawing,
    )
    summary = _summary(
        rows,
        metadata=metadata,
        use_case=selected_use_case,
        strict=strict,
    )
    return DataHealthReport(
        contract_version=DATA_HEALTH_CONTRACT_VERSION,
        report_schema_version=DATA_HEALTH_REPORT_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        community=community,
        use_case=selected_use_case,
        strict=strict,
        selectors={
            "from_drawing": from_drawing,
            "to_drawing": to_drawing,
            "last": last,
        },
        summary=summary,
        metadata=metadata,
        drawings=rows,
    )


def require_data_health(
    session: Session,
    *,
    use_case: DataHealthUseCase | str,
    drawing_ids: Sequence[int],
    allow_unhealthy_research: bool = False,
) -> DataHealthGateResult:
    """Fail closed unless an explicit research-only override is supplied."""
    report = audit_data_health(
        session,
        use_case=use_case,
        strict=True,
        drawing_ids=drawing_ids,
        raw_snapshot_drawing_ids=(),
    )
    if report.summary.passed:
        return DataHealthGateResult(report=report, override_applied=False)
    if allow_unhealthy_research:
        if use_case not in ("backtest_probability", "historical_inventory"):
            raise ValueError(
                "data-health override is allowed only for historical research"
            )
        return DataHealthGateResult(report=report, override_applied=True)
    raise DataHealthFailure(report)


def discover_raw_snapshot_drawing_ids(
    db_path: str | Path | None,
) -> set[int]:
    """Discover drawing IDs only in the canonical sibling ``data/raw`` tree."""
    if db_path is None:
        return set()
    raw_root = Path(db_path).resolve().parent / "raw"
    if not raw_root.is_dir():
        return set()
    drawing_ids: set[int] = set()
    for path in raw_root.rglob("*.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        drawing_ids.update(_detail_drawing_ids(payload))
    return drawing_ids


def write_data_health_reports(
    report: DataHealthReport,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "data_health_v1.csv"
    json_path = directory / "data_health_v1.json"
    markdown_path = directory / "data_health_v1.md"

    detail_rows = [_csv_row(report, row) for row in report.drawings]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)
    json_path.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return csv_path, json_path, markdown_path


def _drawing_health(
    drawing: Drawing,
    *,
    events: Sequence[Event],
    quotes: Sequence[Quote],
    result_snapshots: Sequence[DrawingResultSnapshot],
    packages: Sequence[ArchivedPackage],
    settlements: Sequence[PackageSettlement],
    raw_snapshot_present: bool,
    selected_use_case: DataHealthUseCase,
) -> DrawingHealth:
    event_orders = tuple(
        sorted(
            event.event_order
            for event in events
            if type(event.event_order) is int
        )
    )
    quote_orders = tuple(
        quote.event_order for quote in quotes if type(quote.event_order) is int
    )
    structure_valid = (
        len(events) == 15
        and len(set(event_orders)) == 15
        and set(event_orders) == EXPECTED_EVENT_ORDERS
    )
    quote_structure_valid = (
        len(quotes) == 15
        and len(set(quote_orders)) == 15
        and set(quote_orders) == EXPECTED_EVENT_ORDERS
    )
    nonblank_names = sum(
        isinstance(event.name, str) and bool(event.name.strip()) for event in events
    )
    valid_pool_count = sum(
        _valid_probability_triple(
            quote.pool_win_1,
            quote.pool_draw,
            quote.pool_win_2,
        )
        for quote in quotes
    )
    zero_pool_count = sum(
        _zero_probability_triple(
            quote.pool_win_1,
            quote.pool_draw,
            quote.pool_win_2,
        )
        for quote in quotes
    )
    complete_bk_count = sum(
        _valid_probability_triple(
            quote.bk_win_1,
            quote.bk_draw,
            quote.bk_win_2,
        )
        for quote in quotes
    )
    terminal_results = sum(_terminal_result(event.result) for event in events)
    void_results = sum(_void_result(event.result) for event in events)
    complete_result_snapshots = sum(
        bool(snapshot.complete) and snapshot.event_count == 15
        for snapshot in result_snapshots
    )
    actionable_packages = tuple(
        package for package in packages if package.provenance == "pre_bet_runner"
    )
    settled_archives = {settlement.archive_sha256 for settlement in settlements}
    unsettled_packages = sum(
        package.archive_sha256 not in settled_archives
        for package in actionable_packages
    )

    reasons: list[str] = []
    if not structure_valid:
        reasons.append("invalid_event_count_order")
    if nonblank_names != 15:
        reasons.append("empty_event_names")
    if not quote_structure_valid or valid_pool_count + zero_pool_count != 15:
        reasons.append("missing_quotes")
    if zero_pool_count:
        reasons.append("invalid_zero_pool")
    if not quote_structure_valid or complete_bk_count != 15:
        reasons.append("incomplete_bk")
    if terminal_results == 0:
        reasons.append("all_results_missing")
    elif terminal_results != 15:
        reasons.append("incomplete_results")
    if not raw_snapshot_present:
        reasons.append("missing_raw_snapshot")
    if drawing.status == "finished" and complete_result_snapshots == 0:
        reasons.append("missing_result_snapshot")
    if unsettled_packages:
        reasons.append("unsettled_package")

    observed = _ordered_reasons(reasons)
    eligibility = {
        use_case: not bool(
            set(observed).intersection(BLOCKING_REASONS[use_case])
        )
        for use_case in USE_CASES
    }
    selected_blockers = _ordered_reasons(
        set(observed).intersection(BLOCKING_REASONS[selected_use_case])
    )
    return DrawingHealth(
        drawing_id=drawing.id,
        drawing_number=drawing.number,
        drawing_status=drawing.status or "",
        event_count=len(events),
        event_orders=event_orders,
        nonblank_name_count=nonblank_names,
        quote_count=len(quotes),
        valid_pool_count=valid_pool_count,
        zero_pool_count=zero_pool_count,
        complete_bk_count=complete_bk_count,
        terminal_result_count=terminal_results,
        void_result_count=void_results,
        result_snapshot_count=len(result_snapshots),
        complete_result_snapshot_count=complete_result_snapshots,
        raw_snapshot_present=raw_snapshot_present,
        actionable_package_count=len(actionable_packages),
        unsettled_actionable_package_count=unsettled_packages,
        observed_reason_codes=observed,
        use_case_eligibility=eligibility,
        selected_status="healthy" if not selected_blockers else "unhealthy",
        selected_reason_codes=selected_blockers or ("healthy",),
    )


def _summary(
    rows: Sequence[DrawingHealth],
    *,
    metadata: DataHealthMetadata,
    use_case: DataHealthUseCase,
    strict: bool,
) -> DataHealthSummary:
    healthy = sum(row.use_case_eligibility[use_case] for row in rows)
    unhealthy = len(rows) - healthy
    use_case_totals = {
        candidate: {
            "healthy": sum(
                row.use_case_eligibility[candidate] for row in rows
            ),
            "unhealthy": sum(
                not row.use_case_eligibility[candidate] for row in rows
            ),
        }
        for candidate in USE_CASES
    }
    reason_counts = Counter(
        reason
        for row in rows
        for reason in row.selected_reason_codes
        if reason != "healthy"
    )
    observed_counts = Counter(
        reason for row in rows for reason in row.observed_reason_codes
    )
    finished_rows = tuple(row for row in rows if row.drawing_status == "finished")
    inventory_counts = {
        "event_rows": sum(row.event_count for row in rows),
        "finished_drawings": len(finished_rows),
        "finished_incomplete_result_drawings": sum(
            row.terminal_result_count != 15 for row in finished_rows
        ),
        "missing_terminal_results_in_finished": sum(
            max(0, 15 - row.terminal_result_count) for row in finished_rows
        ),
        "valid_pool_drawings": sum(
            row.quote_count == 15
            and row.valid_pool_count == 15
            and row.zero_pool_count == 0
            for row in rows
        ),
        "complete_bk_drawings": sum(
            row.quote_count == 15 and row.complete_bk_count == 15 for row in rows
        ),
        "raw_snapshot_drawings": sum(row.raw_snapshot_present for row in rows),
        "result_snapshot_drawings": sum(
            row.complete_result_snapshot_count > 0 for row in rows
        ),
        "actionable_package_drawings": sum(
            row.actionable_package_count > 0 for row in rows
        ),
        "unsettled_actionable_package_drawings": sum(
            row.unsettled_actionable_package_count > 0 for row in rows
        ),
    }
    metadata_blocks = use_case == "historical_inventory" and not metadata.healthy
    passed = unhealthy == 0 and not metadata_blocks
    return DataHealthSummary(
        total_drawings=len(rows),
        healthy_drawings=healthy,
        unhealthy_drawings=unhealthy,
        inventory_counts=inventory_counts,
        use_case_totals=use_case_totals,
        reason_counts=dict(sorted(reason_counts.items())),
        observed_reason_counts=dict(sorted(observed_counts.items())),
        gap_count=len(metadata.gaps),
        duplicate_number_count=len(metadata.duplicates),
        strict=strict,
        passed=passed,
        exit_status=(
            "pass"
            if passed or not strict
            else "data_quality_failure"
        ),
    )


def _metadata(
    drawings: Sequence[Drawing],
    *,
    from_drawing: int | None,
    to_drawing: int | None,
) -> DataHealthMetadata:
    by_number: dict[int, list[int]] = defaultdict(list)
    for drawing in drawings:
        if drawing.number is not None:
            by_number[drawing.number].append(drawing.id)
    selected_numbers = sorted(by_number)
    lower = from_drawing
    upper = to_drawing
    if lower is None and selected_numbers:
        lower = selected_numbers[0]
    if upper is None and selected_numbers:
        upper = selected_numbers[-1]
    gaps = (
        tuple(
            number
            for number in range(lower, upper + 1)
            if number not in by_number
        )
        if lower is not None and upper is not None
        else ()
    )
    duplicates = {
        number: tuple(sorted(ids))
        for number, ids in by_number.items()
        if len(ids) > 1
    }
    return DataHealthMetadata(
        selected_min_number=lower,
        selected_max_number=upper,
        gaps=gaps,
        duplicates=duplicates,
    )


def _select_drawings(
    drawings: Sequence[Drawing],
    *,
    from_drawing: int | None,
    to_drawing: int | None,
    last: int | None,
    drawing_ids: Sequence[int] | None,
) -> list[Drawing]:
    if drawing_ids is not None:
        ids = set(drawing_ids)
        selected = [drawing for drawing in drawings if drawing.id in ids]
        missing = sorted(ids - {drawing.id for drawing in selected})
        if missing:
            raise ValueError(f"Drawing IDs were not found: {missing}")
        return selected
    selected = [
        drawing
        for drawing in drawings
        if drawing.number is not None
        and (from_drawing is None or drawing.number >= from_drawing)
        and (to_drawing is None or drawing.number <= to_drawing)
    ]
    if last is None:
        return selected
    latest_numbers = sorted(
        {drawing.number for drawing in selected if drawing.number is not None},
        reverse=True,
    )[:last]
    included = set(latest_numbers)
    return [drawing for drawing in selected if drawing.number in included]


def _validate_selectors(
    *,
    from_drawing: int | None,
    to_drawing: int | None,
    last: int | None,
    drawing_ids: Sequence[int] | None,
) -> None:
    for name, value in (
        ("from_drawing", from_drawing),
        ("to_drawing", to_drawing),
        ("last", last),
    ):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError(f"{name} must be a positive integer")
    if (
        from_drawing is not None
        and to_drawing is not None
        and from_drawing > to_drawing
    ):
        raise ValueError("from_drawing cannot be greater than to_drawing")
    if last is not None and (
        from_drawing is not None or to_drawing is not None
    ):
        raise ValueError("--last cannot be combined with drawing range selectors")
    if drawing_ids is not None and any(
        value is not None for value in (from_drawing, to_drawing, last)
    ):
        raise ValueError("drawing_ids cannot be combined with CLI selectors")


def _validate_use_case(value: str) -> DataHealthUseCase:
    if value not in USE_CASES:
        raise ValueError(
            "use_case must be one of: " + ", ".join(USE_CASES)
        )
    return value  # type: ignore[return-value]


def _group_by_drawing(rows: Iterable[object]) -> dict[int, tuple[object, ...]]:
    grouped: dict[int, list[object]] = defaultdict(list)
    for row in rows:
        grouped[row.drawing_id].append(row)
    return {drawing_id: tuple(items) for drawing_id, items in grouped.items()}


def _valid_probability_triple(*values: float | None) -> bool:
    return all(_valid_number(value) for value in values) and sum(
        float(value) for value in values if value is not None
    ) > 0


def _zero_probability_triple(*values: float | None) -> bool:
    return all(_valid_number(value) for value in values) and all(
        float(value) == 0 for value in values if value is not None
    )


def _valid_number(value: float | None) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _terminal_result(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    return normalized in DECIDED_RESULTS or normalized.casefold() in VOID_RESULTS


def _void_result(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and value.strip().casefold() in VOID_RESULTS
    )


def _ordered_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    values = set(reasons)
    return tuple(reason for reason in REASON_ORDER if reason in values)


def _detail_drawing_ids(value: object, *, depth: int = 0) -> set[int]:
    if depth > 12:
        return set()
    found: set[int] = set()
    if isinstance(value, dict):
        events = value.get("events")
        if (
            type(value.get("id")) is int
            and value.get("name") == "baltbet-main"
            and isinstance(events, list)
        ):
            found.add(value["id"])
        for child in value.values():
            found.update(_detail_drawing_ids(child, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.update(_detail_drawing_ids(child, depth=depth + 1))
    return found


def _csv_row(
    report: DataHealthReport,
    row: DrawingHealth,
) -> dict[str, object]:
    return {
        "contract_version": report.contract_version,
        "use_case": report.use_case,
        "summary_total_drawings": report.summary.total_drawings,
        "summary_healthy_drawings": report.summary.healthy_drawings,
        "summary_unhealthy_drawings": report.summary.unhealthy_drawings,
        "summary_inventory_counts": json.dumps(
            report.summary.inventory_counts,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "summary_reason_counts": json.dumps(
            report.summary.reason_counts,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "summary_gap_count": report.summary.gap_count,
        "summary_duplicate_number_count": (
            report.summary.duplicate_number_count
        ),
        "summary_exit_status": report.summary.exit_status,
        "drawing_id": row.drawing_id,
        "drawing_number": row.drawing_number,
        "drawing_status": row.drawing_status,
        "selected_status": row.selected_status,
        "selected_reason_codes": "|".join(row.selected_reason_codes),
        "observed_reason_codes": "|".join(row.observed_reason_codes),
        "event_count": row.event_count,
        "event_orders": "|".join(str(value) for value in row.event_orders),
        "nonblank_name_count": row.nonblank_name_count,
        "quote_count": row.quote_count,
        "valid_pool_count": row.valid_pool_count,
        "zero_pool_count": row.zero_pool_count,
        "complete_bk_count": row.complete_bk_count,
        "terminal_result_count": row.terminal_result_count,
        "void_result_count": row.void_result_count,
        "result_snapshot_count": row.result_snapshot_count,
        "complete_result_snapshot_count": row.complete_result_snapshot_count,
        "raw_snapshot_present": row.raw_snapshot_present,
        "actionable_package_count": row.actionable_package_count,
        "unsettled_actionable_package_count": (
            row.unsettled_actionable_package_count
        ),
        **{
            f"eligible_{use_case}": row.use_case_eligibility[use_case]
            for use_case in USE_CASES
        },
    }


def _markdown(report: DataHealthReport) -> str:
    summary = report.summary
    lines = [
        "# TotoAI Data Health",
        "",
        f"- Contract version: `{report.contract_version}`",
        f"- Report schema: `{report.report_schema_version}`",
        f"- Use case: `{report.use_case}`",
        f"- Strict: `{str(report.strict).lower()}`",
        f"- Exit status: `{summary.exit_status}`",
        f"- Drawings: {summary.total_drawings}",
        f"- Healthy: {summary.healthy_drawings}",
        f"- Unhealthy: {summary.unhealthy_drawings}",
        f"- Gaps: {summary.gap_count}",
        f"- Duplicate visible numbers: {summary.duplicate_number_count}",
        "",
        "## Inventory counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]
    for metric, count in summary.inventory_counts.items():
        lines.append(f"| {metric} | {count} |")
    lines.extend(
        [
        "",
        "## Use-case totals",
        "",
        "| Use case | Healthy | Unhealthy |",
        "|---|---:|---:|",
        ]
    )
    for use_case, counts in summary.use_case_totals.items():
        lines.append(
            f"| {use_case} | {counts['healthy']} | {counts['unhealthy']} |"
        )
    lines.extend(
        [
            "",
            "## Selected-use-case reasons",
            "",
            "| Reason | Drawings |",
            "|---|---:|",
        ]
    )
    if summary.reason_counts:
        for reason, count in summary.reason_counts.items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| healthy | 0 |")
    lines.extend(
        [
            "",
            "## Metadata",
            "",
            "- Gaps: "
            + (
                ", ".join(map(str, report.metadata.gaps))
                if report.metadata.gaps
                else "none"
            ),
            "- Duplicates: "
            + (
                ", ".join(
                    f"{number} ({','.join(map(str, ids))})"
                    for number, ids in sorted(
                        report.metadata.duplicates.items()
                    )
                )
                if report.metadata.duplicates
                else "none"
            ),
            "",
            "## Drawing detail",
            "",
            "| Number | ID | Status | Health | Reasons | Events | Pool | BK | "
            "Results | VOID |",
            "|---:|---:|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report.drawings:
        lines.append(
            f"| {row.drawing_number} | {row.drawing_id} | "
            f"{row.drawing_status} | {row.selected_status} | "
            f"{', '.join(row.selected_reason_codes)} | {row.event_count} | "
            f"{row.valid_pool_count} | {row.complete_bk_count} | "
            f"{row.terminal_result_count} | {row.void_result_count} |"
        )
    return "\n".join(lines) + "\n"
