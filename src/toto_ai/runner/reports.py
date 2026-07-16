"""Deterministic rollback-safe drawing runner reports."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.runner.models import DrawingRunnerResult

RUNNER_REPORT_SCHEMA_VERSION = 1
RUNNER_PROVIDER = "api-sports"


def _normalize_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    try:
        return tuple(Path(path) for path in paths)
    except TypeError as error:
        raise ValueError("report links must contain paths") from error


@dataclass(frozen=True)
class RunnerReportLinks:
    external: tuple[Path, ...] = ()
    ev: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "external", _normalize_paths(self.external))
        object.__setattr__(self, "ev", _normalize_paths(self.ev))


_EMPTY_REPORT_LINKS = RunnerReportLinks()


def drawing_run_id(result: DrawingRunnerResult) -> str:
    """Return the deterministic 12-character identity for one invocation."""
    identity = _run_identity(result)
    encoded = _canonical_json(identity).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def drawing_run_report_paths(
    result: DrawingRunnerResult,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    """Return deterministic JSON and Markdown paths for one runner result."""
    _require_result(result)
    target = result.target.target
    drawing_label = target.drawing_number or target.drawing_id
    deadline = target.deadline.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    stem = f"drawing_run_{drawing_label}_{deadline}_{drawing_run_id(result)}"
    output_dir = Path(report_dir)
    return output_dir / f"{stem}.json", output_dir / f"{stem}.md"


def write_drawing_run_reports(
    result: DrawingRunnerResult,
    links: RunnerReportLinks = _EMPTY_REPORT_LINKS,
    report_dir: str | Path = "reports",
    input_paths: Iterable[str | Path] = (),
) -> tuple[Path, Path]:
    """Render and publish one rollback-safe manifest and Markdown pair."""
    _require_result(result)
    if not isinstance(links, RunnerReportLinks):
        raise ValueError("links must be RunnerReportLinks")

    json_path, markdown_path = drawing_run_report_paths(result, report_dir)
    output_paths = {json_path.resolve(), markdown_path.resolve()}
    resolved_inputs = {Path(path).resolve() for path in input_paths}
    if output_paths & resolved_inputs:
        raise ValueError("runner report and input paths must be distinct")

    payload = _report_payload(result, links)
    json_bytes = _canonical_json(payload).encode("utf-8")
    markdown_bytes = _render_markdown(payload).encode("utf-8")
    _write_atomic_pair(
        (
            (json_path, json_bytes),
            (markdown_path, markdown_bytes),
        )
    )
    return json_path, markdown_path


def _run_identity(result: DrawingRunnerResult) -> dict[str, Any]:
    _require_result(result)
    target = result.target.target
    config = result.config
    return {
        "config": {
            "bank": config.bank,
            "final_lead_minutes": config.final_lead_minutes,
            "mode": config.mode,
            "provider": RUNNER_PROVIDER,
            "safety_stop_minutes": config.safety_stop_minutes,
            "stake": config.stake,
        },
        "preflight_at": _timestamp(result.preflight_at),
        "target": {
            "deadline": _timestamp(target.deadline),
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "fingerprint": result.target.fingerprint,
        },
    }


def _report_payload(
    result: DrawingRunnerResult,
    links: RunnerReportLinks,
) -> dict[str, Any]:
    target = result.target.target
    config = result.config
    warnings = _warnings(result)
    return {
        "schema_version": RUNNER_REPORT_SCHEMA_VERSION,
        "run_id": drawing_run_id(result),
        "command_status": "success",
        "decision": result.decision,
        "terminal_reason": result.terminal_reason,
        "target": {
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "deadline": _timestamp(target.deadline),
            "preflight_fingerprint": result.target.fingerprint,
            "final_fingerprint": result.final_fingerprint,
        },
        "config": {
            "bank": config.bank,
            "stake": config.stake,
            "mode": config.mode,
            "final_lead_minutes": config.final_lead_minutes,
            "safety_stop_minutes": config.safety_stop_minutes,
            "provider": RUNNER_PROVIDER,
        },
        "timeline": {
            "preflight_at": _timestamp(result.preflight_at),
            "final_started_at": _optional_timestamp(result.final_started_at),
            "collection_finished_at": _optional_timestamp(
                result.collection_finished_at
            ),
            "timing_finished_at": _optional_timestamp(result.timing_finished_at),
            "audit_finished_at": _optional_timestamp(result.audit_finished_at),
            "ev_finished_at": _optional_timestamp(result.ev_finished_at),
            "finished_at": _timestamp(result.finished_at),
            "elapsed_seconds": float(result.elapsed_seconds),
        },
        "collection": _collection_payload(result),
        "eligibility": _eligibility_payload(result),
        "coverage": _coverage_payload(result),
        "ev": _ev_payload(result),
        "report_links": {
            "external": [str(path) for path in links.external],
            "ev": [str(path) for path in links.ev],
        },
        "warnings": warnings,
    }


def _collection_payload(result: DrawingRunnerResult) -> dict[str, Any] | None:
    collection = result.collection
    if collection is None:
        return None
    return {
        "final_collection_id": collection.snapshot.collection_id,
        "collection_ids": [
            collection_pass.snapshot.collection_id
            for collection_pass in collection.passes
        ],
        "pass_count": len(collection.passes),
        "base_pass_count": collection.base_pass_count,
        "expansion_pass_count": collection.expansion_pass_count,
        "expanded": collection.expanded,
        "final_horizon_days": collection.final_horizon_days,
        "stop_reason": collection.stop_reason,
        "total_requests": collection.total_requests,
        "total_cache_hits": collection.total_cache_hits,
        "requested_schedule_date_count": (
            collection.total_requested_schedule_dates
        ),
        "successful_schedule_date_count": (
            collection.total_successful_schedule_dates
        ),
        "failed_schedule_date_count": collection.total_failed_schedule_dates,
        "elapsed_seconds": float(collection.elapsed_seconds),
    }


def _eligibility_payload(result: DrawingRunnerResult) -> dict[str, Any]:
    timing = result.timing_eligibility
    collection_eligibility = (
        None if result.collection is None else result.collection.eligibility
    )
    return {
        "status": timing.status,
        "reason": timing.reason,
        "target_fingerprint": timing.target_fingerprint,
        "fingerprint_match": timing.fingerprint_match,
        "span_days": (
            None
            if collection_eligibility is None
            else collection_eligibility.span_days
        ),
        "missing_event_orders": (
            []
            if collection_eligibility is None
            else list(collection_eligibility.missing_event_orders)
        ),
        "totobrief_count": (
            None
            if collection_eligibility is None
            else collection_eligibility.totobrief_count
        ),
        "provider_count": (
            None
            if collection_eligibility is None
            else collection_eligibility.provider_count
        ),
        "earliest_start": (
            None
            if collection_eligibility is None
            else _optional_timestamp(collection_eligibility.earliest_start)
        ),
        "latest_start": (
            None
            if collection_eligibility is None
            else _optional_timestamp(collection_eligibility.latest_start)
        ),
    }


def _coverage_payload(result: DrawingRunnerResult) -> dict[str, Any] | None:
    audit = result.audit
    if audit is None:
        return None
    gate = audit.gate
    return {
        "gate_decision": gate.decision,
        "gate_reasons": list(gate.reasons),
        "drawings": gate.drawings,
        "events": gate.events,
        "unique_match_rate": gate.unique_match_rate,
        "consensus_rate": gate.consensus_rate,
        "ambiguous_matches": gate.ambiguous_matches,
        "explicit_dispositions": gate.explicit_dispositions,
        "operational_failures": gate.operational_failures,
    }


def _ev_payload(result: DrawingRunnerResult) -> dict[str, Any]:
    ev_run = result.ev_run
    if ev_run is None:
        return {
            "computed": False,
            "input_fetched_at": None,
            "minimum_gross_ev": None,
            "prize_fund_factor": None,
            "possible_winnings_source": None,
            "jackpot_source": None,
            "self_dilution_ratio": None,
            "model_supported": None,
            "model_warning": None,
            "package": {
                "decision": "NO BET",
                "coupons": [],
                "selected_count": 0,
                "cost": 0,
                "unused_bank": result.config.bank,
                "expected_payout": 0.0,
                "modeled_roi": None,
                "derived_brief": [],
            },
            "sensitivity": [],
        }
    package = ev_run.package
    selected_coupons = (
        package.coupons
        if result.decision in ("PLAY", "RESEARCH ONLY")
        else ()
    )
    return {
        "computed": True,
        "input_fetched_at": ev_run.ev_input.fetched_at,
        "minimum_gross_ev": ev_run.config.min_gross_ev,
        "prize_fund_factor": ev_run.config.prize_fund_factor,
        "possible_winnings_source": ev_run.possible_winnings_source,
        "jackpot_source": ev_run.jackpot_source,
        "self_dilution_ratio": ev_run.self_dilution_ratio,
        "model_supported": ev_run.model_supported,
        "model_warning": ev_run.model_warning,
        "package": {
            "decision": package.decision,
            "coupons": [
                {
                    "rank": coupon.rank,
                    "coupon": coupon.coupon,
                    "gross_ev": coupon.gross_ev,
                    "net_ev": coupon.net_ev,
                }
                for coupon in selected_coupons
            ],
            "selected_count": len(selected_coupons),
            "cost": package.cost,
            "unused_bank": package.unused_bank,
            "expected_payout": package.expected_payout,
            "modeled_roi": package.modeled_roi,
            "derived_brief": list(package.derived_brief),
        },
        "sensitivity": [
            {
                "prize_fund_factor": row.prize_fund_factor,
                "possible_winnings": row.possible_winnings,
                "decision": row.decision,
                "selected_count": row.selected_count,
                "cost": row.cost,
                "unused_bank": row.unused_bank,
                "expected_payout": row.expected_payout,
                "modeled_roi": row.modeled_roi,
            }
            for row in ev_run.sensitivity
        ],
    }


def _warnings(result: DrawingRunnerResult) -> list[str]:
    if result.ev_run is None or result.ev_run.model_warning is None:
        return []
    return [result.ev_run.model_warning]


def _render_markdown(payload: dict[str, Any]) -> str:
    target = payload["target"]
    config = payload["config"]
    timeline = payload["timeline"]
    collection = payload["collection"]
    eligibility = payload["eligibility"]
    coverage = payload["coverage"]
    ev = payload["ev"]
    links = payload["report_links"]
    drawing_label = target["drawing_number"] or target["drawing_id"]
    lines = [
        f"# Drawing Run {drawing_label}",
        "",
        "## Decision",
        "",
        f"- command status: {payload['command_status']}",
        f"- decision: {payload['decision']}",
        f"- terminal reason: {payload['terminal_reason']}",
        f"- run ID: {payload['run_id']}",
        f"- schema version: {payload['schema_version']}",
        "",
        "## Target",
        "",
        f"- drawing ID: {target['drawing_id']}",
        f"- drawing number: {_display(target['drawing_number'])}",
        f"- deadline: {target['deadline']}",
        f"- preflight fingerprint: {target['preflight_fingerprint']}",
        f"- final fingerprint: {_display_null(target['final_fingerprint'])}",
        "",
        "## Configuration",
        "",
        f"- provider: {config['provider']}",
        f"- bank: {config['bank']}",
        f"- stake: {config['stake']}",
        f"- mode: {config['mode']}",
        f"- final lead minutes: {config['final_lead_minutes']}",
        f"- safety stop minutes: {config['safety_stop_minutes']}",
        "",
        "## Timeline",
        "",
        f"- preflight at: {timeline['preflight_at']}",
        f"- final started at: {_display(timeline['final_started_at'])}",
        "- collection finished at: "
        f"{_display(timeline['collection_finished_at'])}",
        f"- timing finished at: {_display(timeline['timing_finished_at'])}",
        f"- audit finished at: {_display(timeline['audit_finished_at'])}",
        f"- EV finished at: {_display(timeline['ev_finished_at'])}",
        f"- finished at: {timeline['finished_at']}",
        f"- elapsed seconds: {timeline['elapsed_seconds']}",
        "",
        "## Collection",
        "",
    ]
    lines.extend(_collection_markdown(collection))
    lines.extend(
        [
            "",
            "## Timing Eligibility",
            "",
            f"- status: {eligibility['status']}",
            f"- reason: {eligibility['reason']}",
            "- fingerprint match: "
            f"{_yes_no(eligibility['fingerprint_match'])}",
            "- target fingerprint: "
            f"{_display(eligibility['target_fingerprint'])}",
            f"- span days: {_display(eligibility['span_days'])}",
            "- TotoBrief timing count: "
            f"{_display(eligibility['totobrief_count'])}",
            "- provider timing count: "
            f"{_display(eligibility['provider_count'])}",
            "- missing event orders: "
            f"{_display_list(eligibility['missing_event_orders'])}",
            "- earliest start: "
            f"{_display(eligibility['earliest_start'])}",
            f"- latest start: {_display(eligibility['latest_start'])}",
            "",
            "## Coverage Audit",
            "",
        ]
    )
    lines.extend(_coverage_markdown(coverage))
    lines.extend(["", "## EV Package", ""])
    lines.extend(_ev_markdown(ev))
    lines.extend(["", "## Associated Reports", ""])
    lines.extend(_link_markdown("external", links["external"]))
    lines.extend(_link_markdown("EV", links["ev"]))
    lines.extend(["", "## Warnings", ""])
    warnings = payload["warnings"]
    lines.extend(
        [f"- {warning}" for warning in warnings]
        if warnings
        else ["- none"]
    )
    lines.append("")
    return "\n".join(lines)


def _collection_markdown(collection: dict[str, Any] | None) -> list[str]:
    if collection is None:
        return ["- collection not run"]
    return [
        f"- final collection ID: {collection['final_collection_id']}",
        "- collection IDs: "
        f"{_display_list(collection['collection_ids'])}",
        f"- pass count: {collection['pass_count']}",
        f"- base pass count: {collection['base_pass_count']}",
        f"- expansion pass count: {collection['expansion_pass_count']}",
        f"- expanded: {_yes_no(collection['expanded'])}",
        f"- final horizon days: {collection['final_horizon_days']}",
        f"- stop reason: {collection['stop_reason']}",
        f"- total requests: {collection['total_requests']}",
        f"- total cache hits: {collection['total_cache_hits']}",
        "- requested schedule dates: "
        f"{collection['requested_schedule_date_count']}",
        "- successful schedule dates: "
        f"{collection['successful_schedule_date_count']}",
        "- failed schedule dates: "
        f"{collection['failed_schedule_date_count']}",
        f"- elapsed seconds: {collection['elapsed_seconds']}",
    ]


def _coverage_markdown(coverage: dict[str, Any] | None) -> list[str]:
    if coverage is None:
        return ["- coverage audit not run"]
    return [
        f"- gate decision: {coverage['gate_decision']} (diagnostic only)",
        f"- gate reasons: {_display_list(coverage['gate_reasons'])}",
        f"- drawings: {coverage['drawings']}",
        f"- events: {coverage['events']}",
        f"- unique match rate: {coverage['unique_match_rate']}",
        f"- consensus rate: {coverage['consensus_rate']}",
        f"- ambiguous matches: {coverage['ambiguous_matches']}",
        f"- explicit dispositions: {coverage['explicit_dispositions']}",
        f"- operational failures: {coverage['operational_failures']}",
    ]


def _ev_markdown(ev: dict[str, Any]) -> list[str]:
    package = ev["package"]
    lines = [
        f"- decision: {package['decision']}",
        f"- selected count: {package['selected_count']}",
        f"- cost: {package['cost']}",
        f"- unused bank: {package['unused_bank']}",
        f"- expected payout: {package['expected_payout']}",
        f"- modeled ROI: {_display(package['modeled_roi'])}",
    ]
    if not ev["computed"]:
        lines.extend(
            [
                "- EV package computation: not run",
                "- selected coupons: none",
            ]
        )
        return lines
    lines.extend(
        [
            f"- input fetched at: {ev['input_fetched_at']}",
            f"- minimum gross EV: {ev['minimum_gross_ev']}",
            f"- prize fund factor: {ev['prize_fund_factor']}",
            f"- possible winnings source: {ev['possible_winnings_source']}",
            f"- jackpot source: {ev['jackpot_source']}",
            f"- self-dilution ratio: {ev['self_dilution_ratio']}",
            f"- model supported: {_yes_no(ev['model_supported'])}",
            "- modeled ROI is not observed ROI",
        ]
    )
    if not package["coupons"]:
        lines.append("- selected coupons: none")
        return lines
    lines.extend(
        [
            "",
            "| Rank | Coupon | Gross EV | Net EV |",
            "| ---: | --- | ---: | ---: |",
        ]
    )
    for coupon in package["coupons"]:
        lines.append(
            f"| {coupon['rank']} | {coupon['coupon']} | "
            f"{coupon['gross_ev']} | {coupon['net_ev']} |"
        )
    return lines


def _link_markdown(label: str, paths: list[str]) -> list[str]:
    if not paths:
        return [f"- {label}: none"]
    return [f"- {label}: {path}" for path in paths]


def _write_atomic_pair(
    artifacts: tuple[tuple[Path, bytes], tuple[Path, bytes]],
) -> None:
    token = secrets.token_hex(16)
    transaction = tuple(
        (
            final_path,
            content,
            final_path.with_name(f".{final_path.name}.{token}.tmp"),
            final_path.with_name(f".{final_path.name}.{token}.bak.tmp"),
        )
        for final_path, content in artifacts
    )
    transaction_paths = tuple(
        path
        for _, _, temporary_path, backup_path in transaction
        for path in (temporary_path, backup_path)
    )
    originals: dict[Path, bool] = {}
    publication_started = False

    try:
        for final_path, _, _, _ in transaction:
            final_path.parent.mkdir(parents=True, exist_ok=True)

        for _, content, temporary_path, _ in transaction:
            _write_exclusive(temporary_path, content)

        for final_path, _, _, backup_path in transaction:
            original_exists = final_path.exists()
            originals[final_path] = original_exists
            if original_exists:
                _copy_exclusive(final_path, backup_path)

        publication_started = True
        for final_path, _, temporary_path, _ in transaction:
            os.replace(temporary_path, final_path)
    except BaseException:
        if publication_started:
            for final_path, _, _, backup_path in transaction:
                if not originals[final_path]:
                    final_path.unlink(missing_ok=True)
                else:
                    os.replace(backup_path, final_path)
        raise
    finally:
        for path in transaction_paths:
            path.unlink(missing_ok=True)


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as output:
        output.write(content)


def _copy_exclusive(source: Path, destination: Path) -> None:
    with source.open("rb") as input_file, destination.open("xb") as output:
        shutil.copyfileobj(input_file, output)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _timestamp(value)


def _display(value: object) -> str:
    return "n/a" if value is None else str(value)


def _display_null(value: object) -> str:
    return "null" if value is None else str(value)


def _display_list(values: list[object]) -> str:
    return "none" if not values else ", ".join(str(value) for value in values)


def _yes_no(value: object) -> str:
    return "yes" if value else "no"


def _require_result(result: object) -> None:
    if not isinstance(result, DrawingRunnerResult):
        raise ValueError("result must be a DrawingRunnerResult")
