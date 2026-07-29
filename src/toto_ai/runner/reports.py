"""Deterministic rollback-safe drawing runner reports."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from toto_ai.ev.reports import (
    ev_package_report_paths,
    ev_package_report_paths_for_config,
    write_ev_package_reports,
)
from toto_ai.external_odds.reports import (
    external_coverage_report_paths,
    external_coverage_report_paths_for_config,
    write_external_coverage_reports,
)
from toto_ai.path_safety import (
    ArtifactPublicationTransaction,
    probe_writable_directory,
    validate_output_paths,
)
from toto_ai.runner.models import (
    DrawingRunnerConfig,
    DrawingRunnerResult,
    PinnedDrawing,
)

RUNNER_REPORT_SCHEMA_VERSION = 5
LEGACY_RUNNER_REPORT_SCHEMA_VERSION = 4
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


@dataclass(frozen=True)
class DrawingRunPublication:
    result: DrawingRunnerResult
    external: tuple[Path, ...]
    ev: tuple[Path, ...]
    runner: tuple[Path, Path]

    @property
    def paths(self) -> tuple[Path, ...]:
        return (*self.external, *self.ev, *self.runner)


class _PublicationDeadlineReached(RuntimeError):
    def __init__(self, observed_at: datetime) -> None:
        super().__init__("safety cutoff reached before publication")
        self.observed_at = observed_at


def drawing_run_id(result: DrawingRunnerResult) -> str:
    """Return the deterministic 12-character identity for one invocation."""
    _require_result(result)
    identity = _run_identity_values(
        result.config,
        result.target,
        result.preflight_at,
    )
    encoded = _canonical_json(identity).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def drawing_run_report_paths_for_target(
    config: DrawingRunnerConfig,
    target: PinnedDrawing,
    preflight_at: datetime,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    """Return runner paths before waiting or collecting provider data."""
    _require_preflight_identity(config, target, preflight_at)
    target_value = target.target
    drawing_label = target_value.drawing_number or target_value.drawing_id
    deadline = target_value.deadline.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    identity = _run_identity_values(config, target, preflight_at)
    encoded = _canonical_json(identity).encode("utf-8")
    run_id = hashlib.sha256(encoded).hexdigest()[:12]
    stem = f"drawing_run_{drawing_label}_{deadline}_{run_id}"
    output_dir = Path(report_dir)
    return output_dir / f"{stem}.json", output_dir / f"{stem}.md"


def drawing_run_report_paths(
    result: DrawingRunnerResult,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    """Return deterministic JSON and Markdown paths for one runner result."""
    _require_result(result)
    return drawing_run_report_paths_for_target(
        result.config,
        result.target,
        result.preflight_at,
        report_dir,
    )


def drawing_run_candidate_paths(
    config: DrawingRunnerConfig,
    target: PinnedDrawing,
    preflight_at: datetime,
    report_dir: str | Path = "reports",
) -> tuple[Path, ...]:
    """Return every child or runner path a successful run could publish."""
    _require_preflight_identity(config, target, preflight_at)
    target_value = target.target
    external = external_coverage_report_paths_for_config(
        requested_last=30,
        minimum_bookmakers=3,
        report_dir=report_dir,
    )
    ev = ev_package_report_paths_for_config(
        drawing_id=target_value.drawing_id,
        drawing_number=target_value.drawing_number,
        mode=config.mode,
        bank=config.bank,
        report_dir=report_dir,
    )
    runner = drawing_run_report_paths_for_target(
        config,
        target,
        preflight_at,
        report_dir,
    )
    return (*external, *ev, *runner)


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


def publish_drawing_run_artifacts(
    result: DrawingRunnerResult,
    *,
    report_dir: str | Path = "reports",
    protected_paths: Iterable[str | Path] = (),
    protected_roots: Iterable[str | Path] = (),
    now: Callable[[], datetime],
) -> DrawingRunPublication:
    """Publish all linked artifacts as one deadline-aware transaction."""
    _require_result(result)
    protected = _normalize_protected_paths(protected_paths)
    roots = _normalize_protected_paths(protected_roots)
    current = result

    while True:
        if current.decision != "NO BET":
            observed_at = _publication_now(now)
            if _publication_closed(current, observed_at):
                current = _suppress_for_publication(current, observed_at)

        external_candidates = (
            external_coverage_report_paths(current.audit, report_dir)
            if current.audit is not None
            else ()
        )
        ev_candidates = (
            ev_package_report_paths(current.ev_run, report_dir)
            if current.decision != "NO BET" and current.ev_run is not None
            else ()
        )
        runner_candidates = drawing_run_report_paths(current, report_dir)
        candidates = (
            *external_candidates,
            *ev_candidates,
            *runner_candidates,
        )
        validate_output_paths(
            candidates,
            protected_paths=protected,
            protected_roots=roots,
        )
        probe_writable_directory(report_dir)
        for root in roots:
            probe_writable_directory(root)
        writer_inputs = (*protected, *roots)

        try:
            transaction = ArtifactPublicationTransaction(candidates)
            publication: DrawingRunPublication | None = None
            try:
                with transaction:
                    external_paths: tuple[Path, ...] = ()
                    if current.audit is not None:
                        external_paths = write_external_coverage_reports(
                            current.audit,
                            report_dir=report_dir,
                            input_paths=writer_inputs,
                        )

                    ev_paths: tuple[Path, ...] = ()
                    if current.decision != "NO BET" and current.ev_run is not None:
                        _require_open_for_actionable_publication(current, now)
                        ev_paths = write_ev_package_reports(
                            current.ev_run,
                            report_dir=report_dir,
                            input_paths=writer_inputs,
                        )

                    if current.decision != "NO BET":
                        _require_open_for_actionable_publication(current, now)
                    runner_paths = write_drawing_run_reports(
                        current,
                        links=RunnerReportLinks(
                            external=external_paths,
                            ev=ev_paths,
                        ),
                        report_dir=report_dir,
                        input_paths=writer_inputs,
                    )
                    publication = DrawingRunPublication(
                        result=current,
                        external=external_paths,
                        ev=ev_paths,
                        runner=runner_paths,
                    )
                    transaction.commit()
            except BaseException:
                if transaction.committed and publication is not None:
                    return publication
                raise
            assert publication is not None
            return publication
        except _PublicationDeadlineReached as error:
            current = _suppress_for_publication(current, error.observed_at)


def _run_identity(result: DrawingRunnerResult) -> dict[str, Any]:
    _require_result(result)
    return _run_identity_values(result.config, result.target, result.preflight_at)


def _run_identity_values(
    config: DrawingRunnerConfig,
    pinned: PinnedDrawing,
    preflight_at: datetime,
) -> dict[str, Any]:
    target = pinned.target
    return {
        "config": {
            "bank": config.bank,
            "final_lead_minutes": config.final_lead_minutes,
            "mode": config.mode,
            "provider": RUNNER_PROVIDER,
            "safety_stop_minutes": config.safety_stop_minutes,
            "stake": config.stake,
        },
        "preflight_at": _timestamp(preflight_at),
        "target": {
            "deadline": _timestamp(target.deadline),
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "fingerprint": pinned.fingerprint,
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
        "schema_version": (
            RUNNER_REPORT_SCHEMA_VERSION
            if result.final_input is not None
            else LEGACY_RUNNER_REPORT_SCHEMA_VERSION
        ),
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
        "replay": _offline_replay_payload(result),
        "final_input": _final_input_payload(result),
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


def _final_input_payload(result: DrawingRunnerResult) -> dict[str, Any] | None:
    provenance = result.final_input
    if provenance is None:
        return None
    return {
        "path": provenance.path,
        "captured_at": _timestamp(provenance.captured_at),
        "snapshot_sha256": provenance.snapshot_sha256,
        "detail_payload_sha256": provenance.detail_payload_sha256,
        "probability_input_sha256": provenance.probability_input_sha256,
        "attempt_id": provenance.attempt_id,
    }


def _offline_replay_payload(result: DrawingRunnerResult) -> dict[str, Any] | None:
    replay = result.offline_replay
    if replay is None:
        return None
    return {
        "mode": "offline-replay",
        "replay_root": replay.replay_root,
        "replay_as_of": _timestamp(replay.replay_as_of),
        "target_cache_path": replay.target_cache_path,
        "target_cache_sha256": replay.target_cache_sha256,
        "target_payload_sha256": replay.target_payload_sha256,
        "schedule_cache_path": replay.schedule_cache_path,
        "schedule_cache_sha256": replay.schedule_cache_sha256,
        "schedule_payload_sha256": replay.schedule_payload_sha256,
        "provider": replay.provider,
        "actionable": replay.actionable,
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
        "pinned_revalidation": _pinned_revalidation_payload(
            collection.snapshot.pinned_revalidation
        ),
    }


def _pinned_revalidation_payload(summary: object | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return asdict(summary)


def _eligibility_payload(result: DrawingRunnerResult) -> dict[str, Any]:
    effective_timing = result.timing_eligibility
    raw_timing = result.raw_timing_eligibility
    assert raw_timing is not None
    collection_eligibility = (
        None if result.collection is None else result.collection.eligibility
    )
    raw_details = _stored_timing_details(collection_eligibility)
    override = result.timing_override
    if override is None:
        effective_details = raw_details
    elif override.status == "applied" and override.overlay_summary is not None:
        effective_details = _summary_timing_details(override.overlay_summary)
    else:
        effective_details = _empty_timing_details()
    raw_payload = _timing_eligibility_details(raw_timing, raw_details)
    effective_payload = _timing_eligibility_details(
        effective_timing,
        effective_details,
    )
    return {
        **effective_payload,
        "raw": raw_payload,
        "effective": effective_payload,
        "override": _timing_override_payload(result),
    }


def _timing_eligibility_details(
    timing: object,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": timing.status,
        "reason": timing.reason,
        "target_fingerprint": timing.target_fingerprint,
        "fingerprint_match": timing.fingerprint_match,
        **details,
    }


def _stored_timing_details(eligibility: object | None) -> dict[str, Any]:
    if eligibility is None:
        return _empty_timing_details(operator_override_count=0)
    return {
        "span_days": eligibility.span_days,
        "missing_event_orders": list(eligibility.missing_event_orders),
        "totobrief_count": eligibility.totobrief_count,
        "provider_count": eligibility.provider_count,
        "operator_override_count": 0,
        "earliest_start": _optional_timestamp(eligibility.earliest_start),
        "latest_start": _optional_timestamp(eligibility.latest_start),
    }


def _summary_timing_details(summary: object) -> dict[str, Any]:
    return {
        "span_days": summary.span_days,
        "missing_event_orders": list(summary.missing_event_orders),
        "totobrief_count": summary.totobrief_count,
        "provider_count": summary.provider_count,
        "operator_override_count": summary.operator_override_count,
        "earliest_start": _optional_timestamp(summary.earliest_start),
        "latest_start": _optional_timestamp(summary.latest_start),
    }


def _empty_timing_details(
    *,
    operator_override_count: int | None = None,
) -> dict[str, Any]:
    return {
        "span_days": None,
        "missing_event_orders": [],
        "totobrief_count": None,
        "provider_count": None,
        "operator_override_count": operator_override_count,
        "earliest_start": None,
        "latest_start": None,
    }


def _timing_override_payload(
    result: DrawingRunnerResult,
) -> dict[str, Any] | None:
    override = result.timing_override
    if override is None:
        return None
    return {
        "status": override.status,
        "preflight_catalog_sha256": override.preflight_catalog_sha256,
        "timing_catalog_sha256": override.timing_catalog_sha256,
        "package_catalog_sha256": override.package_catalog_sha256,
        "override_id": override.override_id,
        "reviewer": override.reviewer,
        "reviewed_at": _optional_timestamp(override.reviewed_at),
        "source_ref": override.source_ref,
        "overlay_complete": override.overlay_complete,
        "applied_events": [
            {
                "event_order": event.event_order,
                "event_id": event.event_id,
                "starts_at": _timestamp(event.starts_at),
                "source_ref": event.source_ref,
            }
            for event in override.applied_events
        ],
        "preserved_event_orders": list(override.preserved_event_orders),
        "diagnostics": list(override.diagnostics),
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
            "requested_bank": result.config.bank,
            "effective_budget": None,
            "selected_cost": None,
            "unused_requested_bank": None,
            "input_fetched_at": None,
            "minimum_gross_ev": None,
            "prize_fund_factor": None,
            "possible_winnings_source": None,
            "jackpot_source": None,
            "self_dilution_ratio": None,
            "model_supported": None,
            "model_warning": None,
            "package_safety": None,
            "package": {
                "decision": "NO BET",
                "decision_reason": result.terminal_reason,
                "coupons": [],
                "selected_count": None,
                "cost": None,
                "unused_bank": None,
                "expected_payout": None,
                "modeled_roi": None,
                "derived_brief": [],
            },
            "sensitivity": [],
        }
    package = ev_run.package
    _validate_computed_ev_payload(result)
    selected_coupons = (
        package.coupons
        if result.decision in ("PLAY", "RESEARCH ONLY")
        else ()
    )
    decision_reason = package.decision_reason
    if package.decision == "NO BET" and decision_reason is None:
        decision_reason = result.terminal_reason
    return {
        "computed": True,
        "requested_bank": ev_run.requested_bank,
        "effective_budget": ev_run.effective_budget,
        "selected_cost": ev_run.selected_cost,
        "unused_requested_bank": ev_run.unused_requested_bank,
        "input_fetched_at": ev_run.ev_input.fetched_at,
        "minimum_gross_ev": ev_run.config.min_gross_ev,
        "prize_fund_factor": ev_run.config.prize_fund_factor,
        "possible_winnings_source": ev_run.possible_winnings_source,
        "jackpot_source": ev_run.jackpot_source,
        "self_dilution_ratio": ev_run.self_dilution_ratio,
        "model_supported": ev_run.model_supported,
        "model_warning": ev_run.model_warning,
        "package_safety": (
            None
            if ev_run.package_safety is None
            else ev_run.package_safety.to_dict()
        ),
        "package": {
            "decision": package.decision,
            "decision_reason": decision_reason,
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


def _validate_computed_ev_payload(result: DrawingRunnerResult) -> None:
    ev_run = result.ev_run
    assert ev_run is not None
    package = ev_run.package
    requested_bank = ev_run.requested_bank
    effective_budget = ev_run.effective_budget
    selected_cost = ev_run.selected_cost
    selected_count = len(package.coupons)

    if requested_bank != result.config.bank:
        raise ValueError("EV requested bank must match runner requested bank")
    if (
        type(effective_budget) is not int
        or effective_budget < 0
        or effective_budget > requested_bank
        or effective_budget % result.config.stake
    ):
        raise ValueError("EV effective budget must be an exact stake-aligned cap")
    if selected_cost != package.cost:
        raise ValueError("EV selected cost must match package cost")
    if selected_cost != selected_count * result.config.stake:
        raise ValueError("EV selected cost must match selected coupon count")
    if selected_cost > effective_budget:
        raise ValueError("EV selected cost cannot exceed effective budget")
    if ev_run.unused_requested_bank != requested_bank - selected_cost:
        raise ValueError("EV unused requested bank is inconsistent")
    if package.unused_bank != ev_run.unused_requested_bank:
        raise ValueError("EV package unused bank is inconsistent")
    if result.decision == "PLAY" and (
        ev_run.config.effective_budget is None
        or effective_budget <= 0
        or selected_count <= 0
        or selected_cost <= 0
    ):
        raise ValueError(
            "PLAY requires a positive explicit effective budget and selected package"
        )
    if package.decision == "NO BET" and (
        selected_count != 0 or selected_cost != 0
    ):
        raise ValueError("NO BET must not contain a selected package")


def _warnings(result: DrawingRunnerResult) -> list[str]:
    if result.ev_run is None or result.ev_run.model_warning is None:
        return []
    return [result.ev_run.model_warning]


def _render_markdown(payload: dict[str, Any]) -> str:
    target = payload["target"]
    config = payload["config"]
    replay = payload["replay"]
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
        "## Offline Replay",
        "",
        *_offline_replay_markdown(replay),
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
            *_timing_eligibility_markdown(eligibility),
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


def _offline_replay_markdown(replay: dict[str, Any] | None) -> list[str]:
    if replay is None:
        return ["- live production path"]
    return [
        "- mode: offline-replay",
        f"- isolation root: {replay['replay_root']}",
        f"- replay as of: {replay['replay_as_of']}",
        f"- actionable: {_yes_no(replay['actionable'])}",
        f"- provider: {replay['provider']}",
        f"- target cache: {replay['target_cache_path']}",
        f"- target cache SHA-256: {replay['target_cache_sha256']}",
        f"- target payload SHA-256: {replay['target_payload_sha256']}",
        f"- schedule cache: {replay['schedule_cache_path']}",
        f"- schedule cache SHA-256: {replay['schedule_cache_sha256']}",
        f"- schedule payload SHA-256: {replay['schedule_payload_sha256']}",
    ]


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


def _timing_eligibility_markdown(eligibility: dict[str, Any]) -> list[str]:
    raw = eligibility["raw"]
    effective = eligibility["effective"]
    return [
        f"- raw status: {raw['status']}",
        f"- raw reason: {raw['reason']}",
        f"- raw fingerprint match: {_yes_no(raw['fingerprint_match'])}",
        f"- raw target fingerprint: {_display(raw['target_fingerprint'])}",
        f"- raw span days: {_display(raw['span_days'])}",
        f"- raw TotoBrief timing count: {_display(raw['totobrief_count'])}",
        f"- raw provider timing count: {_display(raw['provider_count'])}",
        "- raw operator override count: "
        f"{_display(raw['operator_override_count'])}",
        "- raw missing event orders: "
        f"{_display_list(raw['missing_event_orders'])}",
        f"- raw earliest start: {_display(raw['earliest_start'])}",
        f"- raw latest start: {_display(raw['latest_start'])}",
        f"- effective status: {effective['status']}",
        f"- effective reason: {effective['reason']}",
        "- effective fingerprint match: "
        f"{_yes_no(effective['fingerprint_match'])}",
        "- effective target fingerprint: "
        f"{_display(effective['target_fingerprint'])}",
        f"- effective span days: {_display(effective['span_days'])}",
        "- effective TotoBrief timing count: "
        f"{_display(effective['totobrief_count'])}",
        "- effective provider timing count: "
        f"{_display(effective['provider_count'])}",
        "- effective operator override count: "
        f"{_display(effective['operator_override_count'])}",
        "- effective missing event orders: "
        f"{_display_list(effective['missing_event_orders'])}",
        f"- effective earliest start: {_display(effective['earliest_start'])}",
        f"- effective latest start: {_display(effective['latest_start'])}",
        "",
        "### Timing Override",
        "",
        *_timing_override_markdown(eligibility["override"]),
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


def _timing_override_markdown(override: dict[str, Any] | None) -> list[str]:
    if override is None:
        return ["- no timing override catalog supplied"]
    lines = [
        f"- status: {override['status']}",
        "- preflight catalog SHA-256: "
        f"{_display(override['preflight_catalog_sha256'])}",
        "- timing catalog SHA-256: "
        f"{_display(override['timing_catalog_sha256'])}",
        "- package catalog SHA-256: "
        f"{_display(override['package_catalog_sha256'])}",
        f"- override ID: {_display(override['override_id'])}",
        f"- reviewer: {_display(override['reviewer'])}",
        f"- reviewed at: {_display(override['reviewed_at'])}",
        f"- source: {_display(override['source_ref'])}",
        f"- complete overlay: {_yes_no(override['overlay_complete'])}",
        "- preserved event orders: "
        f"{_display_list(override['preserved_event_orders'])}",
        f"- diagnostics: {_display_list(override['diagnostics'])}",
    ]
    if not override["applied_events"]:
        lines.append("- applied events: none")
        return lines
    lines.extend(
        [
            "",
            "| Order | Event ID | UTC start | Source |",
            "| ---: | ---: | --- | --- |",
        ]
    )
    for event in override["applied_events"]:
        lines.append(
            f"| {event['event_order']} | {event['event_id']} | "
            f"{event['starts_at']} | {event['source_ref']} |"
        )
    return lines


def _ev_markdown(ev: dict[str, Any]) -> list[str]:
    package = ev["package"]
    lines = [
        f"- EV package computation: {'computed' if ev['computed'] else 'not run'}",
        f"- decision: {package['decision']}",
        f"- decision reason: {_display(package['decision_reason'])}",
        f"- requested bank: {ev['requested_bank']}",
        f"- effective cap: {_display(ev['effective_budget'])}",
        f"- selected count: {_display(package['selected_count'])}",
        f"- selected cost: {_display(ev['selected_cost'])}",
        f"- cost: {_display(package['cost'])}",
        "- unused requested bank: "
        f"{_display(ev['unused_requested_bank'])}",
        f"- unused bank: {_display(package['unused_bank'])}",
        f"- expected payout: {_display(package['expected_payout'])}",
        f"- modeled ROI: {_display(package['modeled_roi'])}",
    ]
    if not ev["computed"]:
        lines.append("- selected coupons: none")
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


def _normalize_protected_paths(
    paths: Iterable[str | Path],
) -> tuple[Path, ...]:
    try:
        return tuple(Path(path) for path in paths)
    except TypeError as error:
        raise ValueError("protected inputs must contain filesystem paths") from error


def _require_preflight_identity(
    config: object,
    target: object,
    preflight_at: object,
) -> None:
    if not isinstance(config, DrawingRunnerConfig):
        raise ValueError("config must be a DrawingRunnerConfig")
    if not isinstance(target, PinnedDrawing):
        raise ValueError("target must be a PinnedDrawing")
    _require_utc_datetime("preflight_at", preflight_at)


def _publication_now(now: Callable[[], datetime]) -> datetime:
    if not callable(now):
        raise ValueError("now must be callable")
    observed_at = now()
    _require_utc_datetime("publication time", observed_at)
    return observed_at


def _publication_closed(
    result: DrawingRunnerResult,
    observed_at: datetime,
) -> bool:
    cutoff = result.target.target.deadline - timedelta(
        minutes=result.config.safety_stop_minutes
    )
    return observed_at >= cutoff


def _require_open_for_actionable_publication(
    result: DrawingRunnerResult,
    now: Callable[[], datetime],
) -> None:
    observed_at = _publication_now(now)
    if _publication_closed(result, observed_at):
        raise _PublicationDeadlineReached(observed_at)


def _suppress_for_publication(
    result: DrawingRunnerResult,
    observed_at: datetime,
) -> DrawingRunnerResult:
    finished_at = max(result.finished_at, observed_at)
    elapsed_seconds = result.elapsed_seconds + (
        finished_at - result.finished_at
    ).total_seconds()
    return replace(
        result,
        finished_at=finished_at,
        elapsed_seconds=elapsed_seconds,
        decision="NO BET",
        terminal_reason="safety cutoff reached before publication",
        ev_run=None,
    )


def _require_utc_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _require_result(result: object) -> None:
    if not isinstance(result, DrawingRunnerResult):
        raise ValueError("result must be a DrawingRunnerResult")
