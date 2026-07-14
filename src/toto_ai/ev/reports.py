"""Deterministic rollback-safe EV package reports."""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from toto_ai.ev.backtest import EVBacktestResult, EVBacktestRow
from toto_ai.ev.drawing import EVPackageRun

CSV_FIELDS = ("rank", "coupon", "gross_ev", "net_ev")
EV_BACKTEST_CSV_FIELDS = tuple(EVBacktestRow.__dataclass_fields__)


def ev_package_report_paths(
    result: EVPackageRun,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    drawing_number = result.ev_input.drawing_number or result.ev_input.drawing_id
    stem = (
        f"ev_package_{drawing_number}_{result.config.mode}_"
        f"bank_{result.config.bank}"
    )
    output_dir = Path(report_dir)
    return output_dir / f"{stem}.csv", output_dir / f"{stem}.md"


def write_ev_package_reports(
    result: EVPackageRun,
    report_dir: str | Path = "reports",
    *,
    input_paths: Iterable[str | Path] = (),
) -> tuple[Path, Path]:
    """Render and atomically publish the exact package and model report."""
    csv_path, markdown_path = ev_package_report_paths(result, report_dir)
    output_paths = {csv_path.resolve(), markdown_path.resolve()}
    resolved_inputs = {Path(path).resolve() for path in input_paths}
    if output_paths & resolved_inputs:
        raise ValueError("EV report and input paths must be distinct")

    csv_bytes = _render_csv(result).encode("utf-8")
    markdown_bytes = _render_markdown(result).encode("utf-8")
    _write_atomic_pair(
        ((csv_path, csv_bytes), (markdown_path, markdown_bytes)),
    )
    return csv_path, markdown_path


def ev_backtest_report_paths(
    result: EVBacktestResult,
    last: int,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    """Return deterministic final report paths for one backtest config."""
    output_dir = Path(report_dir)
    stem = (
        f"ev_backtest_last_{last}_stake_{result.config.stake}_config_"
        f"{result.configuration_hash}"
    )
    return output_dir / f"{stem}.csv", output_dir / f"{stem}.md"


def write_ev_backtest_reports(
    result: EVBacktestResult,
    *,
    last: int,
    report_dir: str | Path = "reports",
    input_paths: Iterable[str | Path] = (),
) -> tuple[Path, Path]:
    """Render and atomically publish modeled backtest rows and summaries."""
    csv_path, markdown_path = ev_backtest_report_paths(result, last, report_dir)
    output_paths = {csv_path.resolve(), markdown_path.resolve()}
    resolved_inputs = {Path(path).resolve() for path in input_paths}
    if output_paths & resolved_inputs:
        raise ValueError("EV backtest report and input paths must be distinct")
    _write_atomic_pair(
        (
            (csv_path, _render_ev_backtest_csv(result).encode("utf-8")),
            (markdown_path, _render_ev_backtest_markdown(result).encode("utf-8")),
        )
    )
    return csv_path, markdown_path


def _render_csv(result: EVPackageRun) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in result.package.coupons:
        writer.writerow(
            {
                "rank": row.rank,
                "coupon": row.coupon,
                "gross_ev": f"{row.gross_ev:.12f}",
                "net_ev": f"{row.net_ev:.12f}",
            }
        )
    return output.getvalue()


def _render_ev_backtest_csv(result: EVBacktestResult) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=EV_BACKTEST_CSV_FIELDS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in result.rows:
        values = asdict(row)
        values["threshold"] = f"{row.threshold:.12f}"
        values["prize_fund_factor"] = f"{row.prize_fund_factor:.12f}"
        values["package_expected_payout"] = (
            f"{row.package_expected_payout:.12f}"
        )
        values["package_modeled_roi"] = (
            ""
            if row.package_modeled_roi is None
            else f"{row.package_modeled_roi:.12f}"
        )
        values["self_dilution_ratio"] = f"{row.self_dilution_ratio:.12f}"
        values["best_hits"] = "" if row.best_hits is None else row.best_hits
        writer.writerow(values)
    return output.getvalue()


def _render_ev_backtest_markdown(result: EVBacktestResult) -> str:
    lines = [
        "# Modeled EV Backtest",
        "",
        "## Scope",
        "",
        f"- configuration hash: {result.configuration_hash}",
        f"- processed drawings: {len(result.processed_drawing_ids)}",
        f"- skipped drawings: {len(result.skipped_drawing_ids)}",
        f"- elapsed seconds: {result.elapsed_seconds:.6f}",
        f"- banks: {','.join(str(value) for value in result.config.banks)}",
        "- thresholds: "
        + ",".join(f"{value:.12f}" for value in result.config.thresholds),
        "- prize fund factors: "
        + ",".join(
            f"{value:.12f}" for value in result.config.prize_fund_factors
        ),
        f"- stake: {result.config.stake}",
        "- modeled payout uses expected crowd denominators",
        "- modeled payout is not observed bookmaker payout",
        "- modeled ROI is not observed ROI",
        "- self-dilution support limit: 0.010000",
        "- above-boundary packages are suppressed to empty NO BET rows",
        "",
        "## Threshold Summary",
        "",
        "| Factor | Bank | Threshold | Drawings | PLAY | NO BET | Unsupported | "
        "Skip rate | Avg selected | Avg utilization | Avg modeled payout | "
        "Avg modeled ROI | Avg best hits | Hit 9 | Hit 10 | Hit 11 | Hit 12 | "
        "Hit 13 | Hit 14 | Hit 15 | Review |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | --- |",
    ]
    for row in result.summaries:
        roi = (
            "n/a"
            if row.average_package_modeled_roi is None
            else f"{row.average_package_modeled_roi:.12f}"
        )
        best_hits = (
            "n/a" if row.average_best_hits is None else f"{row.average_best_hits:.6f}"
        )
        review = (
            "model_review_required=true"
            if row.model_review_required
            else "model_review_required=false"
        )
        lines.append(
            f"| {row.prize_fund_factor:.2f} | {row.bank} | "
            f"{row.threshold:.2f} | {row.drawing_count} | {row.play_count} | "
            f"{row.no_bet_count} | {row.unsupported_count} | "
            f"{row.skip_rate:.6f} | "
            f"{row.average_selected_coupons:.6f} | "
            f"{row.average_bank_utilization:.6f} | "
            f"{row.average_package_expected_payout:.6f} | {roi} | {best_hits} | "
            f"{row.hit_9_rate:.6f} | {row.hit_10_rate:.6f} | "
            f"{row.hit_11_rate:.6f} | {row.hit_12_rate:.6f} | "
            f"{row.hit_13_rate:.6f} | {row.hit_14_rate:.6f} | "
            f"{row.hit_15_rate:.6f} | {review} |"
        )
    lines.extend(
        [
            "",
            "## Decisions",
            "",
            f"- PLAY rows: {sum(row.decision == 'PLAY' for row in result.rows)}",
            f"- NO BET rows: {sum(row.decision == 'NO BET' for row in result.rows)}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_markdown(result: EVPackageRun) -> str:
    config = result.config
    ev_input = result.ev_input
    package = result.package
    bank_ratio = config.bank / ev_input.pool_sum
    modeled_roi = (
        "n/a" if package.modeled_roi is None else f"{package.modeled_roi:.12f}"
    )
    lines = [
        f"# EV Package {ev_input.drawing_number or ev_input.drawing_id}",
        "",
        "## Decision",
        "",
        f"- decision: {package.decision}",
        f"- mode: {config.mode}",
        f"- minimum gross EV: {config.min_gross_ev:.12f}",
        f"- selected count: {len(package.coupons)}",
        f"- cost: {package.cost}",
        f"- unused bank: {package.unused_bank}",
        f"- expected payout: {package.expected_payout:.12f}",
        f"- modeled ROI: {modeled_roi}",
        "- modeled ROI is not observed ROI",
        "",
        "## Input Snapshot",
        "",
        f"- drawing id: {ev_input.drawing_id}",
        f"- drawing number: {ev_input.drawing_number}",
        f"- fetched at: {ev_input.fetched_at}",
        f"- pool sum: {ev_input.pool_sum:.6f}",
        f"- jackpot: {ev_input.jackpot:.6f}",
        f"- jackpot source: {result.jackpot_source}",
        f"- possible winnings: {ev_input.possible_winnings:.6f}",
        f"- possible winnings source: {result.possible_winnings_source}",
        f"- prize fund factor: {config.prize_fund_factor:.6f}",
        "- crowd joint model: independent event marginals",
        f"- bank ratio: {bank_ratio:.12f}",
        f"- self-dilution ratio: {result.self_dilution_ratio:.12f}",
        f"- model supported: {'yes' if result.model_supported else 'no'}",
    ]
    if result.model_warning is not None:
        lines.append(f"- unsupported warning: {result.model_warning}")

    lines.extend(
        [
            "",
            "## Derived Brief",
            "",
            " ".join(value or "-" for value in package.derived_brief),
            "",
            "The derived brief is descriptive; only the exact package CSV "
            "lists selected coupons.",
            "",
            "## Event Probabilities",
            "",
            "| Event | Source | True 1 | True X | True 2 | Crowd 1 | Crowd X | "
            "Crowd 2 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, (true_row, crowd_row, source) in enumerate(
        zip(
            ev_input.true_probabilities,
            ev_input.crowd_probabilities,
            ev_input.probability_sources,
            strict=True,
        ),
        start=1,
    ):
        lines.append(
            f"| {index} | {source} | "
            f"{true_row[0]:.12f} | {true_row[1]:.12f} | {true_row[2]:.12f} | "
            f"{crowd_row[0]:.12f} | {crowd_row[1]:.12f} | {crowd_row[2]:.12f} |"
        )

    lines.extend(
        [
            "",
            "## Top 20 diagnostics",
            "",
            "| Rank | Coupon | Gross EV | Net EV |",
            "| ---: | --- | ---: | ---: |",
        ]
    )
    for row in result.top_coupons:
        lines.append(
            f"| {row.rank} | {row.coupon} | {row.gross_ev:.12f} | {row.net_ev:.12f} |"
        )

    lines.extend(
        [
            "",
            "## Sensitivity",
            "",
            "| Factor | Possible winnings | Decision | Selected | Cost | "
            "Unused bank | Expected payout | Modeled ROI |",
            "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in result.sensitivity:
        sensitivity_roi = (
            "n/a" if row.modeled_roi is None else f"{row.modeled_roi:.12f}"
        )
        lines.append(
            f"| {row.prize_fund_factor:.2f} | {row.possible_winnings:.6f} | "
            f"{row.decision} | {row.selected_count} | {row.cost} | "
            f"{row.unused_bank} | {row.expected_payout:.12f} | {sensitivity_roi} |"
        )
    lines.append("")
    return "\n".join(lines)


def _write_atomic_pair(
    artifacts: tuple[tuple[Path, bytes], tuple[Path, bytes]],
) -> None:
    temporary_paths: list[Path] = []
    rendered: list[tuple[Path, Path]] = []
    backups: dict[Path, Path | None] = {}
    publication_started = False

    try:
        for final_path, content in artifacts:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=final_path.parent,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
            ) as output:
                output.write(content)
                temporary_path = Path(output.name)
            temporary_paths.append(temporary_path)
            rendered.append((temporary_path, final_path))

        for _, final_path in rendered:
            if not final_path.exists():
                backups[final_path] = None
                continue
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=final_path.parent,
                prefix=f".{final_path.name}.",
                suffix=".bak.tmp",
            ) as output:
                backup_path = Path(output.name)
            temporary_paths.append(backup_path)
            shutil.copy2(final_path, backup_path)
            backups[final_path] = backup_path

        publication_started = True
        for temporary_path, final_path in rendered:
            temporary_path.replace(final_path)
            temporary_paths.remove(temporary_path)
    except BaseException:
        if publication_started:
            for _, final_path in rendered:
                backup_path = backups.get(final_path)
                if backup_path is None:
                    final_path.unlink(missing_ok=True)
                    continue
                backup_path.replace(final_path)
                if backup_path in temporary_paths:
                    temporary_paths.remove(backup_path)
        raise
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)
