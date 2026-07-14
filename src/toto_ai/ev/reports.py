"""Deterministic rollback-safe EV package reports."""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from toto_ai.ev.drawing import EVPackageRun

CSV_FIELDS = ("rank", "coupon", "gross_ev", "net_ev")


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
