"""Deterministic JSON, CSV, and concise Markdown package-audit reports."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from toto_ai.package.audit import OUTCOMES, PackageAudit, recompute_audit_sha256


def package_audit_report_paths(
    audit: PackageAudit,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path, Path]:
    drawing = "package" if audit.drawing_id is None else f"drawing_{audit.drawing_id}"
    stem = (
        f"package_audit_{drawing}_{audit.strategy}_bank_{audit.bank.requested}_"
        f"{audit.package_sha256}_{audit.audit_sha256}"
    )
    root = Path(report_dir)
    bundle = root / stem
    return bundle / f"{stem}.json", bundle / f"{stem}.csv", bundle / f"{stem}.md"


def write_package_audit_reports(
    audit: PackageAudit,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path, Path]:
    complete_report = audit.to_dict()
    recompute_audit_sha256(complete_report)
    paths = package_audit_report_paths(audit, report_dir)
    contents = (
        (paths[0], (_render_json(complete_report) + "\n").encode()),
        (paths[1], _render_csv(audit).encode()),
        (paths[2], _render_markdown(audit).encode()),
    )
    final_dir = paths[0].parent
    root = final_dir.parent
    root.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        expected = {path.name: content for path, content in contents}
        actual_names = {path.name for path in final_dir.iterdir()}
        if actual_names != set(expected):
            raise ValueError(
                f"Existing audit bundle integrity mismatch: {final_dir}"
            )
        for path, content in contents:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(
                    f"Existing audit report integrity mismatch: {path}"
                )
        return paths
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.", dir=root))
    try:
        for path, content in contents:
            target = temporary_dir / path.name
            with tempfile.NamedTemporaryFile(
                dir=temporary_dir,
                prefix=f".{path.name}.",
                delete=False,
            ) as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
                staged = Path(output.name)
            staged.replace(target)
        temporary_dir.replace(final_dir)
        return paths
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)


def _render_json(complete_report: dict[str, object]) -> str:
    return json.dumps(
        complete_report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _render_csv(audit: PackageAudit) -> str:
    output = io.StringIO(newline="")
    fields = (
        "event",
        "count_1",
        "count_x",
        "count_2",
        "percentage_1",
        "percentage_x",
        "percentage_2",
        "fixed_outcome",
        "maximum_share",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for exposure in audit.event_exposures:
        writer.writerow(
            {
                "event": exposure.event,
                "count_1": exposure.counts["1"],
                "count_x": exposure.counts["X"],
                "count_2": exposure.counts["2"],
                "percentage_1": f"{exposure.percentages['1']:.12f}",
                "percentage_x": f"{exposure.percentages['X']:.12f}",
                "percentage_2": f"{exposure.percentages['2']:.12f}",
                "fixed_outcome": exposure.fixed_outcome or "",
                "maximum_share": f"{exposure.maximum_share:.12f}",
            }
        )
    return output.getvalue()


def _render_markdown(audit: PackageAudit) -> str:
    lines = [
        "# Package Audit",
        "",
        f"- schema version: {audit.schema_version}",
        f"- strategy: {audit.strategy.upper()}",
        f"- drawing id: {audit.drawing_id or 'n/a'}",
        f"- package SHA-256: {audit.package_sha256}",
        f"- audit SHA-256: {audit.audit_sha256}",
        f"- requested/effective/used bank: {audit.bank.requested}/"
        f"{audit.bank.effective}/{audit.bank.used}",
        f"- stake/coupons: {audit.bank.stake}/{audit.bank.coupon_count}",
        f"- union brief: {','.join(audit.union_brief)}",
        f"- union variants: {audit.union_brief_variant_count}",
        f"- fixed events: {','.join(map(str, audit.fixed_events)) or 'none'}",
        f"- near-fixed events: "
        f"{','.join(map(str, audit.near_fixed_events)) or 'none'}",
        f"- worst minimum distance: {audit.worst_minimum_distance}",
        f"- guaranteed hits: {audit.guaranteed_hits}",
        f"- derived guaranteed category: {audit.guaranteed_category}",
        "",
        "For EV and Hybrid packages this derived category describes exact coverage "
        "of the union brief; it is not a declared Cover target.",
        "",
        "## Event exposure",
        "",
        "| Event | 1 | X | 2 | Fixed | Max share |",
        "| ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for exposure in audit.event_exposures:
        values = [
            f"{exposure.counts[outcome]} "
            f"({exposure.percentages[outcome]:.2%})"
            for outcome in OUTCOMES
        ]
        lines.append(
            f"| {exposure.event} | {values[0]} | {values[1]} | {values[2]} | "
            f"{exposure.fixed_outcome or ''} | {exposure.maximum_share:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Exact union-brief coverage",
            "",
            "| Category | Covered | Share | Guarantee |",
            "| ---: | ---: | ---: | --- |",
        ]
    )
    for category, row in audit.category_coverage.items():
        lines.append(
            f"| {category} | {row['covered_variants']}/"
            f"{row['total_variants']} | {float(row['share']):.6%} | "
            f"{'yes' if row['guarantee'] else 'no'} |"
        )
    lines.extend(["", "## Warnings", ""])
    if not audit.warnings:
        lines.append("- none")
    else:
        for warning in audit.warnings:
            lines.append(
                "- " + json.dumps(warning, ensure_ascii=False, sort_keys=True)
            )
    lines.append("")
    return "\n".join(lines)
