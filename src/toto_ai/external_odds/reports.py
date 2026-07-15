"""Deterministic rollback-safe external-odds coverage reports."""

from __future__ import annotations

import csv
import io
import os
import shutil
import tempfile
from pathlib import Path

from toto_ai.external_odds.audit import CoverageAudit, CoverageMetrics

CSV_FIELDS = (
    "row_type",
    "scope",
    "name",
    "collection_id",
    "drawing_id",
    "drawing_number",
    "event_order",
    "sport",
    "league",
    "match_status",
    "provider_event_id",
    "probability_source",
    "eligible_bookmaker_count",
    "fallback_reason",
    "requests_made",
    "target_count",
    "explicit_dispositions",
    "unique_match_count",
    "unique_match_rate",
    "missing_count",
    "missing_rate",
    "ambiguous_count",
    "ambiguous_rate",
    "unknown_sport_count",
    "unknown_sport_rate",
    "consensus_1_count",
    "consensus_1_rate",
    "consensus_2_count",
    "consensus_2_rate",
    "consensus_3_count",
    "consensus_3_rate",
    "usable_consensus_count",
    "usable_consensus_rate",
    "stale_count",
    "semantic_count",
    "incomplete_market_count",
    "fallback_count",
    "quota_count",
    "provider_error_count",
)


def external_coverage_report_paths(
    audit: CoverageAudit,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    stem = (
        f"external_coverage_last_{audit.requested_last}_"
        f"min_bookmakers_{audit.minimum_bookmakers}"
    )
    output_dir = Path(report_dir)
    return output_dir / f"{stem}.csv", output_dir / f"{stem}.md"


def write_external_coverage_reports(
    audit: CoverageAudit,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    csv_path, markdown_path = external_coverage_report_paths(audit, report_dir)
    _write_atomic_pair(
        (
            (csv_path, _render_csv(audit).encode("utf-8")),
            (markdown_path, _render_markdown(audit).encode("utf-8")),
        )
    )
    return csv_path, markdown_path


def _render_csv(audit: CoverageAudit) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in audit.dispositions:
        writer.writerow(
            {
                "row_type": "disposition",
                "scope": "event",
                "name": "",
                "collection_id": row.collection_id,
                "drawing_id": row.drawing_id,
                "drawing_number": row.drawing_number,
                "event_order": row.event_order,
                "sport": row.sport,
                "league": row.league,
                "match_status": row.match_status,
                "provider_event_id": row.provider_event_id,
                "probability_source": row.probability_source,
                "eligible_bookmaker_count": row.eligible_bookmaker_count,
                "fallback_reason": row.fallback_reason,
                "requests_made": row.requests_made,
            }
        )
    for metric in (
        audit.total,
        *audit.by_sport,
        *audit.by_league,
        *audit.by_drawing,
    ):
        writer.writerow(_metric_csv_row(metric))
    return output.getvalue()


def _metric_csv_row(metric: CoverageMetrics) -> dict[str, object]:
    return {
        "row_type": "aggregate",
        "scope": metric.scope,
        "name": metric.name,
        "target_count": metric.target_count,
        "explicit_dispositions": metric.explicit_dispositions,
        "unique_match_count": metric.unique_match_count,
        "unique_match_rate": f"{metric.unique_match_rate:.12f}",
        "missing_count": metric.missing_count,
        "missing_rate": f"{metric.missing_rate:.12f}",
        "ambiguous_count": metric.ambiguous_count,
        "ambiguous_rate": f"{metric.ambiguous_rate:.12f}",
        "unknown_sport_count": metric.unknown_sport_count,
        "unknown_sport_rate": f"{metric.unknown_sport_rate:.12f}",
        "consensus_1_count": metric.consensus_1_count,
        "consensus_1_rate": f"{metric.consensus_1_rate:.12f}",
        "consensus_2_count": metric.consensus_2_count,
        "consensus_2_rate": f"{metric.consensus_2_rate:.12f}",
        "consensus_3_count": metric.consensus_3_count,
        "consensus_3_rate": f"{metric.consensus_3_rate:.12f}",
        "usable_consensus_count": metric.usable_consensus_count,
        "usable_consensus_rate": f"{metric.usable_consensus_rate:.12f}",
        "stale_count": metric.stale_count,
        "semantic_count": metric.semantic_count,
        "incomplete_market_count": metric.incomplete_market_count,
        "fallback_count": metric.fallback_count,
        "quota_count": metric.quota_count,
        "provider_error_count": metric.provider_error_count,
    }


def _render_markdown(audit: CoverageAudit) -> str:
    lines = [
        "# External Odds Coverage Audit",
        "",
        "## Configuration",
        "",
        f"- provider: {audit.provider}",
        f"- requested drawings: {audit.requested_last}",
        f"- audited latest complete drawings: {audit.drawings}",
        f"- minimum bookmakers: {audit.minimum_bookmakers}",
        "- gate sample floor: 30 drawings and 450 events",
        "- unique match threshold: 80%",
        "- usable consensus threshold: 70%",
        "- ambiguous matches must not be consumed",
        "- every event must have explicit external or fallback disposition",
        "- coverage is not probability quality",
        "- coverage is not profitability evidence",
        "",
        "## Provenance and Quota",
        "",
        f"- average requests per drawing: {audit.average_requests_per_drawing:.6f}",
        f"- maximum requests per drawing: {audit.maximum_requests_per_drawing}",
        (
            "- median fallback events per drawing: "
            f"{audit.fallback_median_per_drawing:.6f}"
        ),
        f"- p90 fallback events per drawing: {audit.fallback_p90_per_drawing:.6f}",
        "",
        "## Gate",
        "",
        f"- decision: {audit.gate.decision}",
        f"- reasons: {', '.join(audit.gate.reasons) if audit.gate.reasons else 'none'}",
        f"- drawings: {audit.gate.drawings}",
        f"- events: {audit.gate.events}",
        f"- unique match rate: {audit.gate.unique_match_rate:.6f}",
        f"- consensus rate: {audit.gate.consensus_rate:.6f}",
        f"- ambiguous matches: {audit.gate.ambiguous_matches}",
        f"- explicit dispositions: {audit.gate.explicit_dispositions}",
        f"- operational failures: {audit.gate.operational_failures}",
        "",
        "## Overall Metrics",
        "",
        _metric_bullets(audit.total),
        "",
        "## Sport Metrics",
        "",
        *_metric_table(audit.by_sport),
        "",
        "## League Metrics",
        "",
        *_metric_table(audit.by_league),
        "",
        "## Fallback Reason Counts",
        "",
    ]
    if audit.fallback_reason_counts:
        for reason, count in audit.fallback_reason_counts.items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none: 0")
    lines.extend(
        [
            "",
            "## Drawing Metrics",
            "",
            *_metric_table(audit.by_drawing),
            "",
        ]
    )
    return "\n".join(lines)


def _metric_bullets(metric: CoverageMetrics) -> str:
    return "\n".join(
        [
            f"- target count: {metric.target_count}",
            f"- explicit dispositions: {metric.explicit_dispositions}",
            (
                f"- unique matches: {metric.unique_match_count} "
                f"({metric.unique_match_rate:.6f})"
            ),
            (
                f"- usable consensus: {metric.usable_consensus_count} "
                f"({metric.usable_consensus_rate:.6f})"
            ),
            f"- missing: {metric.missing_count} ({metric.missing_rate:.6f})",
            f"- ambiguous: {metric.ambiguous_count} ({metric.ambiguous_rate:.6f})",
            (
                f"- unknown sport: {metric.unknown_sport_count} "
                f"({metric.unknown_sport_rate:.6f})"
            ),
            f"- consensus at 1 bookmaker: {metric.consensus_1_count}",
            f"- consensus at 2 bookmakers: {metric.consensus_2_count}",
            f"- consensus at 3 bookmakers: {metric.consensus_3_count}",
            f"- stale: {metric.stale_count}",
            f"- semantic: {metric.semantic_count}",
            f"- incomplete market: {metric.incomplete_market_count}",
            f"- quota: {metric.quota_count}",
            f"- provider error: {metric.provider_error_count}",
            f"- fallback: {metric.fallback_count}",
        ]
    )


def _metric_table(metrics: tuple[CoverageMetrics, ...]) -> list[str]:
    lines = [
        "| Scope | Target | Explicit | Unique Match | Missing | Ambiguous | "
        "Unknown Sport | Consensus >=1 | Consensus >=2 | Consensus >=3 | "
        "Usable Consensus | Stale | Semantic | Incomplete Market | Quota | "
        "Provider Error | Fallback |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric in metrics:
        usable_consensus = _count_rate(
            metric.usable_consensus_count,
            metric.usable_consensus_rate,
        )
        lines.append(
            f"| {metric.name} | {metric.target_count} | "
            f"{metric.explicit_dispositions} | "
            f"{_count_rate(metric.unique_match_count, metric.unique_match_rate)} | "
            f"{_count_rate(metric.missing_count, metric.missing_rate)} | "
            f"{_count_rate(metric.ambiguous_count, metric.ambiguous_rate)} | "
            f"{_count_rate(metric.unknown_sport_count, metric.unknown_sport_rate)} | "
            f"{_count_rate(metric.consensus_1_count, metric.consensus_1_rate)} | "
            f"{_count_rate(metric.consensus_2_count, metric.consensus_2_rate)} | "
            f"{_count_rate(metric.consensus_3_count, metric.consensus_3_rate)} | "
            f"{usable_consensus} | "
            f"{metric.stale_count} | {metric.semantic_count} | "
            f"{metric.incomplete_market_count} | {metric.quota_count} | "
            f"{metric.provider_error_count} | {metric.fallback_count} |"
        )
    if not metrics:
        values = [
            "none",
            "0",
            "0",
            *(["0 (0.000000)"] * 8),
            *(["0"] * 6),
        ]
        lines.append(f"| {' | '.join(values)} |")
    return lines


def _count_rate(count: int, rate: float) -> str:
    return f"{count} ({rate:.6f})"


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
            temporary_path = _write_temp_file(final_path, content)
            temporary_paths.append(temporary_path)
            rendered.append((temporary_path, final_path))

        for _, final_path in rendered:
            if not final_path.exists():
                backups[final_path] = None
                continue
            backup_path = _write_temp_file(final_path, final_path.read_bytes(), ".bak")
            temporary_paths.append(backup_path)
            shutil.copystat(final_path, backup_path)
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


def _write_temp_file(
    final_path: Path,
    content: bytes,
    infix: str = "",
) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=final_path.parent,
        prefix=f".{final_path.name}{infix}.",
        suffix=".tmp",
    ) as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
        return Path(output.name)
