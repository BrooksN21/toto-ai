"""Research-only GOAL probe import and equal-budget package comparison.

This module deliberately has no scheduler, operator-result, or release imports.
It consumes already frozen public GOAL probe artifacts, converts them into the
existing sports-shadow contract, and writes only non-uploadable research files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import package_quality_metrics
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    SourceEvidence,
    SportsStatsRunSnapshot,
    build_event_snapshot,
    build_run_snapshot,
)
from toto_ai.sports_stats.features import build_team_window
from toto_ai.sports_stats.preliminary_comparison import _package, _package_payload
from toto_ai.sports_stats.probabilities import (
    SportsShadowArtifact,
    build_shadow_probability_artifact,
    write_shadow_probability_artifact,
)

GOAL_PROVIDER = "goal-api-v1"
RESEARCH_STATUS = "PAPER_ONLY_NOT_ACTIVATED"
ARTIFACT_CLASS = "RESEARCH_ONLY_GOAL_SPORTS_DUAL_PACKAGE"
_TERMINAL_STATUSES = {
    "FINISHED": "FT",
    "AFTER_ET": "AET",
    "AFTER_PEN": "PEN",
}
_OUTCOMES = "1X2"
_EXPECTED_ORDERS = tuple(range(15))


@dataclass(frozen=True)
class GoalProbeResearchBundle:
    """Validated in-memory GOAL shadow and its human-facing event analytics."""

    shadow: SportsShadowArtifact
    snapshot: SportsStatsRunSnapshot
    target_fingerprint: str
    drawing_payload_sha256: str
    analytics: tuple[Mapping[str, Any], ...]
    source_artifacts: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class GoalResearchReportPaths:
    manifest: Path
    comparison_json: Path
    comparison_markdown: Path
    analytics_json: Path
    analytics_csv: Path
    analytics_markdown: Path
    shadow_artifact: Path
    baseline_csv: Path
    baseline_txt: Path
    sports_csv: Path
    sports_txt: Path


@dataclass(frozen=True)
class _HistoryDiagnostics:
    declared_history_count: int
    declared_venue_count: int
    raw_count: int
    accepted_count: int
    accepted_status_counts: Mapping[str, int]
    excluded_counts: Mapping[str, int]
    source_artifact_sha256: str


@dataclass(frozen=True)
class _HistoryImport:
    fixtures: tuple[CompletedFixture, ...]
    evidence: SourceEvidence
    diagnostics: _HistoryDiagnostics
    path: Path


def load_goal_probe_shadow(
    *,
    drawing_id: int,
    as_of: datetime,
    raw_cache_dir: str | Path,
    coverage_summary_path: str | Path,
    project_root: str | Path = ".",
) -> GoalProbeResearchBundle:
    """Validate frozen GOAL binding/history artifacts and build a shadow.

    History is filtered strictly before both ``as_of`` and the target kickoff.
    GOAL ``FINISHED``, ``AFTER_ET``, and ``AFTER_PEN`` are mapped to the
    existing provider-neutral ``FT``, ``AET``, and ``PEN`` terminal contract.
    Missing usable history remains an event-level BK fallback.
    """

    _utc("as_of", as_of)
    root = Path(project_root).resolve()
    coverage_path = _contained_file(root, coverage_summary_path)
    coverage = _json_object(coverage_path)
    _require_exact(coverage.get("schema_version"), 1, "coverage schema")
    _require_exact(
        coverage.get("status"),
        "PAPER_ONLY_COVERAGE_PROBE",
        "coverage status",
    )
    _require_exact(coverage.get("drawing_id"), drawing_id, "coverage drawing id")
    _require_exact(
        coverage.get("package_influence"), "NONE", "coverage package influence"
    )
    _require_exact(
        coverage.get("automatic_wagering"),
        False,
        "coverage automatic wagering",
    )
    coverage_captured_at = _parse_utc(
        coverage.get("captured_at"), "coverage captured_at"
    )
    if coverage_captured_at > as_of:
        raise ValueError("coverage summary was captured after as_of")

    raw_root = _contained_directory(root, raw_cache_dir)
    record = load_drawing_detail_cache(
        drawing_id,
        cache_dir=raw_root,
        max_age_seconds=None,
        now=as_of,
        allowed_root=raw_root,
    )
    if record.fetched_at > as_of:
        raise ValueError("drawing detail cache was captured after as_of")
    target = parse_target_drawing(record.payload, record.fetched_at)
    if target.drawing_id != drawing_id:
        raise ValueError("drawing cache identity mismatch")
    _require_exact(
        coverage.get("drawing_number"),
        target.drawing_number,
        "coverage drawing number",
    )
    if as_of >= target.deadline:
        raise ValueError("as_of must be strictly before the drawing deadline")
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )

    schedule_path = _declared_file(
        root,
        coverage.get("source_schedule_report"),
        "source_schedule_report",
    )
    schedule = _json_object(schedule_path)
    _validate_schedule_report(
        schedule,
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        as_of=as_of,
    )
    schedule_rows = _ordered_goal_schedule_rows(schedule)
    schedule_rows_by_order = {
        _event_order(row.get("event_order")): row for row in schedule_rows
    }
    coverage_rows = _ordered_coverage_rows(coverage)
    sports_eligible_count = coverage.get("sports_eligible_count")
    history_source_count = coverage.get(
        "history_source_count",
        None
        if not isinstance(sports_eligible_count, int)
        else 2 * sports_eligible_count,
    )
    if (
        coverage.get("event_count") != 15
        or not isinstance(sports_eligible_count, int)
        or not 0 <= sports_eligible_count <= 15
        or history_source_count != 2 * sports_eligible_count
    ):
        raise ValueError("coverage summary counts are invalid")

    imported: list[
        tuple[
            Any,
            Mapping[str, Any],
            Mapping[str, Any] | None,
            datetime,
            _HistoryImport | None,
            _HistoryImport | None,
        ]
    ] = []
    source_files: dict[Path, str] = {
        coverage_path: "goal_coverage_summary",
        schedule_path: "goal_schedule_binding",
        _contained_file(root, raw_root / f"drawing_{drawing_id}.json"): (
            "frozen_totobrief_detail"
        ),
        _contained_file(root, raw_root / f"drawing_{drawing_id}.meta.json"): (
            "frozen_totobrief_detail_metadata"
        ),
    }
    for expected_order, (event, coverage_row) in enumerate(
        zip(target.events, coverage_rows, strict=True)
    ):
        schedule_row = schedule_rows_by_order.get(expected_order)
        if coverage_row.get("sports_eligible") is not True:
            _validate_fallback_binding(
                expected_order=expected_order,
                target_event=event,
                coverage_row=coverage_row,
                schedule_row=schedule_row,
            )
            imported.append(
                (
                    event,
                    coverage_row,
                    None,
                    event.starts_at or target.deadline,
                    None,
                    None,
                )
            )
            continue
        if schedule_row is None:
            raise ValueError("sports-eligible event is missing GOAL schedule binding")
        _validate_event_binding(
            expected_order=expected_order,
            target_event=event,
            coverage_row=coverage_row,
            schedule_row=schedule_row,
        )
        target_start = _parse_utc(
            coverage_row.get("target_starts_at"), "target_starts_at"
        )
        histories = _ordered_history_sources(coverage_row)
        home_history = _load_history_snapshot(
            root=root,
            probe_root=coverage_path.parent,
            source_row=histories["home"],
            team_id=str(coverage_row["provider_home_team_id"]),
            target_fixture_id=str(coverage_row["provider_fixture_id"]),
            target_starts_at=target_start,
            as_of=as_of,
            deadline=target.deadline,
        )
        away_history = _load_history_snapshot(
            root=root,
            probe_root=coverage_path.parent,
            source_row=histories["away"],
            team_id=str(coverage_row["provider_away_team_id"]),
            target_fixture_id=str(coverage_row["provider_fixture_id"]),
            target_starts_at=target_start,
            as_of=as_of,
            deadline=target.deadline,
        )
        source_files[home_history.path] = "goal_team_results"
        source_files[away_history.path] = "goal_team_results"
        imported.append(
            (
                event,
                coverage_row,
                schedule_row,
                target_start,
                home_history,
                away_history,
            )
        )

    event_snapshots = []
    pins = []
    imported_analytics = []
    schedule_captured_at = _parse_utc(
        schedule.get("captured_at"), "schedule captured_at"
    )
    for (
        event,
        coverage_row,
        _schedule_row,
        target_start,
        home_history,
        away_history,
    ) in imported:
        if home_history is None or away_history is None:
            event_snapshots.append(
                build_event_snapshot(
                    schema_version=1,
                    drawing_id=target.drawing_id,
                    drawing_number=target.drawing_number,
                    drawing_fingerprint=fingerprint,
                    event_id=str(event.event_id),
                    event_order=event.event_order,
                    sport="football",
                    provider=GOAL_PROVIDER,
                    status="missing",
                    missing_reasons=("target_fixture_missing",),
                    captured_at=as_of,
                    as_of=as_of,
                    deadline=target.deadline,
                    target_starts_at=target_start,
                    provider_fixture_id=None,
                    canonical_home_team_id=None,
                    canonical_away_team_id=None,
                    provider_home_team_id=None,
                    provider_away_team_id=None,
                    league_id=None,
                    season=None,
                    home_window=None,
                    away_window=None,
                    home_standing=None,
                    away_standing=None,
                    source_evidence=(),
                )
            )
            imported_analytics.append(
                {
                    "event_order": event.event_order,
                    "event_number": event.event_order + 1,
                    "event_id": str(event.event_id),
                    "home_team": event.home_team,
                    "away_team": event.away_team,
                    "target_starts_at": _iso(target_start),
                    "provider_fixture_id": None,
                    "provider_home_team_id": None,
                    "provider_away_team_id": None,
                    "orientation": None,
                    "home_history": _missing_history_analytics("home"),
                    "away_history": _missing_history_analytics("away"),
                }
            )
            continue
        home_provider_id = str(coverage_row["provider_home_team_id"])
        away_provider_id = str(coverage_row["provider_away_team_id"])
        fixture_id = str(coverage_row["provider_fixture_id"])
        home_window = build_team_window(
            team_id=home_provider_id,
            fixtures=home_history.fixtures,
            requested_count=10,
            target_starts_at=target_start,
            target_fixture_id=fixture_id,
            as_of=as_of,
        )
        away_window = build_team_window(
            team_id=away_provider_id,
            fixtures=away_history.fixtures,
            requested_count=10,
            target_starts_at=target_start,
            target_fixture_id=fixture_id,
            as_of=as_of,
        )
        missing_reasons = (
            () if home_window is not None and away_window is not None else (
                "no_completed_fixtures",
            )
        )
        canonical_home_id = event.event_id * 2
        canonical_away_id = event.event_id * 2 + 1
        event_snapshots.append(
            build_event_snapshot(
                schema_version=1,
                drawing_id=target.drawing_id,
                drawing_number=target.drawing_number,
                drawing_fingerprint=fingerprint,
                event_id=str(event.event_id),
                event_order=event.event_order,
                sport="football",
                provider=GOAL_PROVIDER,
                status="complete" if not missing_reasons else "partial",
                missing_reasons=missing_reasons,
                captured_at=as_of,
                as_of=as_of,
                deadline=target.deadline,
                target_starts_at=target_start,
                provider_fixture_id=fixture_id,
                canonical_home_team_id=canonical_home_id,
                canonical_away_team_id=canonical_away_id,
                provider_home_team_id=home_provider_id,
                provider_away_team_id=away_provider_id,
                league_id=None,
                season=None,
                home_window=home_window,
                away_window=away_window,
                home_standing=None,
                away_standing=None,
                source_evidence=(
                    home_history.evidence,
                    away_history.evidence,
                ),
            )
        )
        pin_payload = {
            "drawing_id": target.drawing_id,
            "drawing_fingerprint": fingerprint,
            "event_id": str(event.event_id),
            "event_order": event.event_order,
            "provider": GOAL_PROVIDER,
            "provider_fixture_id": fixture_id,
            "provider_home_team_id": home_provider_id,
            "provider_away_team_id": away_provider_id,
            "orientation": "same",
            "coverage_summary_sha256": _file_sha256(coverage_path),
            "schedule_report_sha256": _file_sha256(schedule_path),
        }
        pin_hash = _sha256_json(pin_payload)
        pins.append(
            DrawingEventPinRecord(
                id=event.event_order + 1,
                drawing_id=target.drawing_id,
                drawing_fingerprint=fingerprint,
                target_event_id=str(event.event_id),
                event_order=event.event_order,
                provider=GOAL_PROVIDER,
                canonical_home_team_id=canonical_home_id,
                canonical_away_team_id=canonical_away_id,
                provider_home_team_id=home_provider_id,
                provider_away_team_id=away_provider_id,
                provider_fixture_id=fixture_id,
                starts_at=_iso(target_start),
                collection_id=None,
                provenance={
                    "orientation": "same",
                    "artifact_class": ARTIFACT_CLASS,
                    "binding": pin_payload,
                },
                pin_hash=pin_hash,
                status="research_only",
                created_at=_iso(schedule_captured_at),
                invalidated_at=None,
                invalidation_reason=None,
                pin_set_id=f"goal-probe-{_file_sha256(coverage_path)[:16]}",
                source_provider=GOAL_PROVIDER,
                source_fixture_id=fixture_id,
                source_identity_hash=pin_hash,
                schedule_only=False,
            )
        )
        imported_analytics.append(
            {
                "event_order": event.event_order,
                "event_number": event.event_order + 1,
                "event_id": str(event.event_id),
                "home_team": event.home_team,
                "away_team": event.away_team,
                "target_starts_at": _iso(target_start),
                "provider_fixture_id": fixture_id,
                "provider_home_team_id": home_provider_id,
                "provider_away_team_id": away_provider_id,
                "orientation": "same",
                "home_history": _history_analytics(
                    home_window, home_history.diagnostics, venue="home"
                ),
                "away_history": _history_analytics(
                    away_window, away_history.diagnostics, venue="away"
                ),
            }
        )

    snapshot = build_run_snapshot(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        drawing_fingerprint=fingerprint,
        provider=GOAL_PROVIDER,
        requested_history_size=10,
        captured_at=as_of,
        as_of=as_of,
        deadline=target.deadline,
        events=tuple(event_snapshots),
        requests_made=0,
        cache_hits=int(history_source_count),
    )
    shadow = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=tuple(pins),
        as_of=as_of,
        generated_at=as_of,
    )
    analytics = tuple(
        _merge_probability_analytics(base, probability)
        for base, probability in zip(
            imported_analytics,
            shadow.events,
            strict=True,
        )
    )
    source_artifacts = tuple(
        {
            "role": role,
            "path": _relative(path, root),
            "sha256": _file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for path, role in sorted(
            source_files.items(), key=lambda item: str(item[0])
        )
    )
    return GoalProbeResearchBundle(
        shadow=shadow,
        snapshot=snapshot,
        target_fingerprint=fingerprint,
        drawing_payload_sha256=record.payload_sha256,
        analytics=analytics,
        source_artifacts=source_artifacts,
    )


def run_goal_probe_package_comparison(
    *,
    drawing_id: int,
    bank: int,
    stake: int,
    as_of: datetime,
    raw_cache_dir: str | Path,
    coverage_summary_path: str | Path,
    output_dir: str | Path,
    project_root: str | Path = ".",
    monte_carlo_samples: int = 2_048,
) -> tuple[dict[str, object], GoalResearchReportPaths]:
    """Build two equal-budget packages and research-only report artifacts."""

    if not isinstance(bank, int) or isinstance(bank, bool) or bank <= 0:
        raise ValueError("bank must be a positive integer")
    if not isinstance(stake, int) or isinstance(stake, bool) or stake <= 0:
        raise ValueError("stake must be a positive integer")
    if bank % stake:
        raise ValueError("bank must be exactly divisible by stake")
    if not isinstance(monte_carlo_samples, int) or monte_carlo_samples <= 0:
        raise ValueError("monte_carlo_samples must be positive")
    _utc("as_of", as_of)
    root = Path(project_root).resolve()
    output = _research_output_directory(root, output_dir)
    output.mkdir(parents=True, exist_ok=True)

    bundle = load_goal_probe_shadow(
        drawing_id=drawing_id,
        as_of=as_of,
        raw_cache_dir=raw_cache_dir,
        coverage_summary_path=coverage_summary_path,
        project_root=root,
    )
    raw_root = _contained_directory(root, raw_cache_dir)
    record = load_drawing_detail_cache(
        drawing_id,
        cache_dir=raw_root,
        max_age_seconds=None,
        now=as_of,
        allowed_root=raw_root,
    )
    config = EVConfig(bank=bank, stake=stake, mode="research")
    baseline_input = ev_input_from_payload(
        record.payload,
        fetched_at=record.fetched_at.isoformat(),
        stake=stake,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    sports_input = replace(
        baseline_input,
        true_probabilities=tuple(
            tuple(event.candidate_blend_probabilities)
            for event in bundle.shadow.events
        ),
        probability_sources=tuple(
            event.probability_source for event in bundle.shadow.events
        ),
    )
    baseline_package = _package(baseline_input, config)
    sports_package = _package(sports_input, config)
    baseline_coupons = tuple(item.coupon for item in baseline_package.coupons)
    sports_coupons = tuple(item.coupon for item in sports_package.coupons)
    capacity = bank // stake
    _validate_equal_full_packages(
        baseline_coupons=baseline_coupons,
        sports_coupons=sports_coupons,
        baseline_cost=baseline_package.cost,
        sports_cost=sports_package.cost,
        bank=bank,
        capacity=capacity,
    )

    baseline_quality = package_quality_metrics(
        baseline_coupons,
        baseline_input.true_probabilities,
        seed_material=f"goal-research-bk-{drawing_id}-{record.payload_sha256}",
        monte_carlo_samples=monte_carlo_samples,
    )
    sports_quality = package_quality_metrics(
        sports_coupons,
        sports_input.true_probabilities,
        seed_material=(
            f"goal-research-sports-{drawing_id}-{bundle.shadow.artifact_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    baseline_under_sports = package_quality_metrics(
        baseline_coupons,
        sports_input.true_probabilities,
        seed_material=(
            "goal-research-bk-under-sports-"
            f"{drawing_id}-{bundle.shadow.artifact_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    sports_under_bk = package_quality_metrics(
        sports_coupons,
        baseline_input.true_probabilities,
        seed_material=(
            f"goal-research-sports-under-bk-{drawing_id}-{record.payload_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    overlap = len(set(baseline_coupons) & set(sports_coupons))
    exposures = _event_exposures(baseline_coupons, sports_coupons)
    report: dict[str, object] = {
        "schema_version": 1,
        "status": RESEARCH_STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": drawing_id,
        "drawing_number": baseline_input.drawing_number,
        "drawing_fingerprint": bundle.target_fingerprint,
        "as_of": _iso(as_of),
        "bank": bank,
        "stake": stake,
        "coupon_limit": capacity,
        "frozen_input_shared_by_both_packages": True,
        "baseline_definition": "existing EV/crowd production math with TotoBrief BK",
        "sports_definition": (
            "the same EV/crowd math with GOAL venue-history candidate blend"
        ),
        "sports_shadow_status": bundle.shadow.status,
        "sports_model_status": bundle.shadow.model_status,
        "sports_coverage_count": bundle.shadow.sports_coverage_count,
        "sports_fallback_count": bundle.shadow.fallback_count,
        "baseline": _package_payload(
            baseline_package,
            baseline_coupons,
            asdict(baseline_quality),
        ),
        "sports_candidate": _package_payload(
            sports_package,
            sports_coupons,
            asdict(sports_quality),
        ),
        "cross_evaluation": {
            "baseline_under_sports": asdict(baseline_under_sports),
            "sports_candidate_under_bk": asdict(sports_under_bk),
        },
        "comparison": {
            "overlap_count": overlap,
            "overlap_share": overlap / capacity,
            "baseline_only_count": len(
                set(baseline_coupons) - set(sports_coupons)
            ),
            "sports_only_count": len(
                set(sports_coupons) - set(baseline_coupons)
            ),
            "identical_order": baseline_coupons == sports_coupons,
            "event_exposures": exposures,
        },
        "inputs": {
            "drawing_payload_sha256": record.payload_sha256,
            "sports_artifact_sha256": bundle.shadow.artifact_sha256,
            "sports_snapshot_sha256": bundle.snapshot.content_sha256,
        },
        "live_provider_requests_made": 0,
        "automatic_wagering": False,
        "real_money_actionable": False,
        "operator_compatible": False,
        "baltbet_upload_format": False,
        "scheduler_or_operator_state_mutated": False,
        "modeled_ev_is_validated_profit_forecast": False,
        "interpretation": (
            "This is one frozen paper-only comparison. It cannot establish "
            "profitability or activate sports probabilities."
        ),
    }
    report["report_sha256"] = _sha256_json(report)

    comparison_json = output / "comparison.json"
    comparison_markdown = output / "comparison.md"
    analytics_json = output / "match-analytics.json"
    analytics_csv = output / "match-analytics.csv"
    analytics_markdown = output / "match-analytics.md"
    baseline_csv = output / "baseline-research-coupons.csv"
    baseline_txt = output / "baseline-research-coupons.txt"
    sports_csv = output / "sports-shadow-research-coupons.csv"
    sports_txt = output / "sports-shadow-research-coupons.txt"

    _write_atomic(comparison_json, _pretty_json(report))
    _write_atomic(comparison_markdown, _comparison_markdown(report))
    _write_atomic(analytics_json, _pretty_json(list(bundle.analytics)))
    _write_atomic(analytics_csv, _analytics_csv(bundle.analytics))
    _write_atomic(analytics_markdown, _analytics_markdown(bundle.analytics))
    _write_atomic(
        baseline_csv,
        _research_package_csv(
            drawing_number=baseline_input.drawing_number,
            role="BASELINE_BK_PRODUCTION_MATH",
            stake=stake,
            coupons=baseline_coupons,
        ),
    )
    _write_atomic(
        baseline_txt,
        _research_package_text(
            role="BASELINE_BK_PRODUCTION_MATH",
            stake=stake,
            coupons=baseline_coupons,
        ),
    )
    _write_atomic(
        sports_csv,
        _research_package_csv(
            drawing_number=baseline_input.drawing_number,
            role="GOAL_SPORTS_SHADOW_CANDIDATE",
            stake=stake,
            coupons=sports_coupons,
        ),
    )
    _write_atomic(
        sports_txt,
        _research_package_text(
            role="GOAL_SPORTS_SHADOW_CANDIDATE",
            stake=stake,
            coupons=sports_coupons,
        ),
    )
    shadow_path = write_shadow_probability_artifact(
        bundle.shadow,
        report_dir=output,
    ).resolve()

    artifact_paths = (
        comparison_json,
        comparison_markdown,
        analytics_json,
        analytics_csv,
        analytics_markdown,
        shadow_path,
        baseline_csv,
        baseline_txt,
        sports_csv,
        sports_txt,
    )
    manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "status": RESEARCH_STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": drawing_id,
        "drawing_number": baseline_input.drawing_number,
        "drawing_fingerprint": bundle.target_fingerprint,
        "as_of": _iso(as_of),
        "configuration": {
            "bank": bank,
            "stake": stake,
            "coupon_count_each": capacity,
            "monte_carlo_samples": monte_carlo_samples,
        },
        "coverage": {
            "sports_events": bundle.shadow.sports_coverage_count,
            "fallback_events": bundle.shadow.fallback_count,
            "total_events": 15,
        },
        "source_artifacts": list(bundle.source_artifacts),
        "artifacts": [
            {
                "path": path.name,
                "sha256": _file_sha256(path),
                "bytes": path.stat().st_size,
                "operator_compatible": False,
            }
            for path in artifact_paths
        ],
        "safety": {
            "research_only": True,
            "paper_only_not_activated": True,
            "automatic_wagering": False,
            "operator_compatible": False,
            "baltbet_upload_format": False,
            "live_provider_requests_made": 0,
            "scheduler_or_operator_state_mutated": False,
            "scheduler_paths_written": [],
        },
    }
    manifest_payload["manifest_sha256"] = _sha256_json(manifest_payload)
    manifest = output / "manifest.json"
    _write_atomic(manifest, _pretty_json(manifest_payload))
    return report, GoalResearchReportPaths(
        manifest=manifest,
        comparison_json=comparison_json,
        comparison_markdown=comparison_markdown,
        analytics_json=analytics_json,
        analytics_csv=analytics_csv,
        analytics_markdown=analytics_markdown,
        shadow_artifact=shadow_path,
        baseline_csv=baseline_csv,
        baseline_txt=baseline_txt,
        sports_csv=sports_csv,
        sports_txt=sports_txt,
    )


def _validate_schedule_report(
    report: Mapping[str, Any],
    *,
    drawing_id: int,
    drawing_number: int | None,
    as_of: datetime,
) -> None:
    _require_exact(report.get("schema_version"), 2, "schedule schema")
    _require_exact(
        report.get("status"),
        "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "schedule status",
    )
    _require_exact(report.get("drawing_id"), drawing_id, "schedule drawing id")
    _require_exact(
        report.get("drawing_number"),
        drawing_number,
        "schedule drawing number",
    )
    _require_exact(report.get("ledger_mutated"), False, "schedule ledger flag")
    captured_at = _parse_utc(report.get("captured_at"), "schedule captured_at")
    if captured_at > as_of:
        raise ValueError("schedule binding was captured after as_of")
    expected_hash = report.get("report_sha256")
    if not isinstance(expected_hash, str):
        raise ValueError("schedule report hash is missing")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if expected_hash != _sha256_json(unsigned, ensure_ascii=True):
        raise ValueError("schedule report semantic hash mismatch")


def _ordered_goal_schedule_rows(
    report: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    records = report.get("records")
    if not isinstance(records, list):
        raise ValueError("schedule records must be a list")
    rows = tuple(
        sorted(
            (
                _mapping(item, "schedule record")
                for item in records
                if isinstance(item, Mapping)
                and item.get("source_provider") == GOAL_PROVIDER
                and (
                    item.get("status")
                    in {"independent_candidate", "timing_conflict"}
                    or (
                        item.get("status") is None
                        and item.get("source_event_id") is not None
                    )
                )
            ),
            key=lambda item: _event_order(item.get("event_order")),
        )
    )
    orders = tuple(_event_order(row.get("event_order")) for row in rows)
    if len(set(orders)) != len(orders):
        raise ValueError("schedule report contains duplicate GOAL event orders")
    return rows


def _ordered_coverage_rows(
    coverage: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    values = coverage.get("events")
    if not isinstance(values, list):
        raise ValueError("coverage events must be a list")
    rows = tuple(
        sorted(
            (_mapping(item, "coverage event") for item in values),
            key=lambda item: _event_order(item.get("event_order")),
        )
    )
    if len(rows) != 15 or tuple(row.get("event_order") for row in rows) != (
        _EXPECTED_ORDERS
    ):
        raise ValueError("coverage summary requires exactly 15 ordered events")
    return rows


def _validate_event_binding(
    *,
    expected_order: int,
    target_event: Any,
    coverage_row: Mapping[str, Any],
    schedule_row: Mapping[str, Any],
) -> None:
    _validate_coverage_identity(
        expected_order=expected_order,
        target_event=target_event,
        coverage_row=coverage_row,
    )
    if coverage_row.get("sports_eligible") is not True:
        raise ValueError("coverage event is not sports eligible")
    for name in (
        "provider_fixture_id",
        "provider_home_team_id",
        "provider_away_team_id",
    ):
        _nonempty_text(coverage_row.get(name), f"coverage {name}")
    schedule_expected = {
        "event_order": expected_order,
        "target_event_id": target_event.event_id,
        "target_home_team": target_event.home_team,
        "target_away_team": target_event.away_team,
        "orientation": "same",
        "source_event_id": coverage_row.get("provider_fixture_id"),
        "source_home_team_id": coverage_row.get("provider_home_team_id"),
        "source_away_team_id": coverage_row.get("provider_away_team_id"),
        "starts_at": coverage_row.get("target_starts_at"),
        "source_status": "scheduled",
        "ledger_eligible": False,
    }
    for name, value in schedule_expected.items():
        _require_exact(schedule_row.get(name), value, f"schedule {name}")


def _validate_coverage_identity(
    *,
    expected_order: int,
    target_event: Any,
    coverage_row: Mapping[str, Any],
) -> None:
    expected = {
        "event_order": expected_order,
        "event_number": expected_order + 1,
        "target_event_id": target_event.event_id,
        "home_team": target_event.home_team,
        "away_team": target_event.away_team,
    }
    for name, value in expected.items():
        _require_exact(coverage_row.get(name), value, f"coverage {name}")


def _validate_fallback_binding(
    *,
    expected_order: int,
    target_event: Any,
    coverage_row: Mapping[str, Any],
    schedule_row: Mapping[str, Any] | None,
) -> None:
    _validate_coverage_identity(
        expected_order=expected_order,
        target_event=target_event,
        coverage_row=coverage_row,
    )
    if schedule_row is not None:
        raise ValueError("fallback event unexpectedly has a GOAL schedule binding")
    expected = {
        "sports_eligible": False,
        "fallback_reason": "target_fixture_missing",
        "provider_fixture_id": None,
        "provider_home_team_id": None,
        "provider_away_team_id": None,
        "target_starts_at": None,
        "sources": [],
    }
    for name, value in expected.items():
        _require_exact(coverage_row.get(name), value, f"fallback coverage {name}")


def _ordered_history_sources(
    coverage_row: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    values = coverage_row.get("sources")
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("coverage event requires two history sources")
    sources = {
        str(source.get("side")): source
        for source in (_mapping(item, "history source") for item in values)
    }
    if set(sources) != {"home", "away"}:
        raise ValueError("coverage history sources must be home and away")
    for side, source in sources.items():
        if source.get("success") is not True or source.get("http_status") != 200:
            raise ValueError(f"{side} history source is not a successful HTTP 200")
    return sources


def _load_history_snapshot(
    *,
    root: Path,
    probe_root: Path,
    source_row: Mapping[str, Any],
    team_id: str,
    target_fixture_id: str,
    target_starts_at: datetime,
    as_of: datetime,
    deadline: datetime,
) -> _HistoryImport:
    path = _declared_file(root, source_row.get("snapshot_path"), "snapshot_path")
    try:
        path.relative_to(probe_root)
    except ValueError as error:
        raise ValueError(
            "GOAL history snapshot must be inside the probe directory"
        ) from error
    snapshot = _json_object(path)
    _require_exact(snapshot.get("schema_version"), 1, "history schema")
    _require_exact(snapshot.get("provider"), GOAL_PROVIDER, "history provider")
    _require_exact(snapshot.get("http_status"), 200, "history HTTP status")
    endpoint = _nonempty_text(snapshot.get("endpoint"), "history endpoint")
    if endpoint != f"/teams/{team_id}/results":
        raise ValueError("history endpoint team binding mismatch")
    params = _mapping(snapshot.get("params"), "history params")
    _require_exact(params.get("limit"), 10, "history limit")
    fetched_at = _parse_utc(snapshot.get("fetched_at"), "history fetched_at")
    if fetched_at > as_of or fetched_at >= deadline:
        raise ValueError("history snapshot was fetched after the frozen boundary")
    payload = _mapping(snapshot.get("payload"), "history payload")
    _require_exact(payload.get("success"), True, "history payload success")
    _require_exact(str(payload.get("teamId")), team_id, "history payload team")
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError("history payload data must contain at most ten rows")

    evidence = SourceEvidence(
        provider=GOAL_PROVIDER,
        endpoint=endpoint,
        request_fingerprint=_sha256_json(
            {"provider": GOAL_PROVIDER, "endpoint": endpoint, "params": params}
        ),
        payload_sha256=_sha256_json(payload),
        fetched_at=fetched_at,
    )
    cutoff = min(target_starts_at, as_of)
    accepted = []
    statuses: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            excluded["invalid_row"] += 1
            continue
        raw_status = raw_row.get("matchStatus")
        mapped_status = _TERMINAL_STATUSES.get(raw_status)
        if mapped_status is None:
            excluded["non_terminal_status"] += 1
            continue
        try:
            fixture_id = _nonempty_text(raw_row.get("id"), "history fixture id")
            starts_at = _parse_utc(raw_row.get("kickoffUtc"), "history kickoff")
            home_team_id = _nonempty_text(
                raw_row.get("homeTeamId"), "history home team id"
            )
            away_team_id = _nonempty_text(
                raw_row.get("awayTeamId"), "history away team id"
            )
            home_goals = _nonnegative_int(
                raw_row.get("homeTeamScore"), "history home score"
            )
            away_goals = _nonnegative_int(
                raw_row.get("awayTeamScore"), "history away score"
            )
        except ValueError:
            excluded["invalid_terminal_row"] += 1
            continue
        if fixture_id in seen_ids:
            raise ValueError("history snapshot contains duplicate fixture ids")
        seen_ids.add(fixture_id)
        if fixture_id == target_fixture_id:
            excluded["target_fixture"] += 1
            continue
        if starts_at >= as_of:
            excluded["at_or_after_as_of"] += 1
            continue
        if starts_at >= target_starts_at:
            excluded["at_or_after_target"] += 1
            continue
        if starts_at >= cutoff:
            raise ValueError("strict history cutoff validation drift")
        if team_id not in (home_team_id, away_team_id):
            excluded["unrelated_team"] += 1
            continue
        accepted.append(
            CompletedFixture(
                provider_fixture_id=fixture_id,
                starts_at=starts_at,
                status=mapped_status,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_goals=home_goals,
                away_goals=away_goals,
                source=evidence,
            )
        )
        statuses[str(raw_status)] += 1
    fixtures = tuple(
        sorted(
            accepted,
            key=lambda fixture: (fixture.starts_at, fixture.provider_fixture_id),
            reverse=True,
        )[:10]
    )
    return _HistoryImport(
        fixtures=fixtures,
        evidence=evidence,
        diagnostics=_HistoryDiagnostics(
            declared_history_count=_nonnegative_int(
                source_row.get("history_count"), "declared history count"
            ),
            declared_venue_count=_nonnegative_int(
                source_row.get("venue_count"), "declared venue count"
            ),
            raw_count=len(rows),
            accepted_count=len(fixtures),
            accepted_status_counts=dict(sorted(statuses.items())),
            excluded_counts=dict(sorted(excluded.items())),
            source_artifact_sha256=_file_sha256(path),
        ),
        path=path,
    )


def _history_analytics(
    window: Any,
    diagnostics: _HistoryDiagnostics,
    *,
    venue: str,
) -> dict[str, Any]:
    venue_wdl = None
    venue_played = 0
    overall_wdl = None
    if window is not None:
        overall_wdl = [window.wins, window.draws, window.losses]
        if venue == "home":
            venue_played = window.home_played
            venue_wdl = [window.home_wins, window.home_draws, window.home_losses]
        else:
            venue_played = window.away_played
            venue_wdl = [window.away_wins, window.away_draws, window.away_losses]
    return {
        "fixture_count": None if window is None else window.fixture_count,
        "overall_wdl": overall_wdl,
        "venue": venue,
        "venue_played": venue_played,
        "venue_wdl": venue_wdl,
        "points_per_game": None if window is None else window.points_per_game,
        "last5_form_points": (
            None if window is None else window.last5_form_points
        ),
        "rest_days": None if window is None else window.rest_days,
        "declared_history_count": diagnostics.declared_history_count,
        "declared_venue_count": diagnostics.declared_venue_count,
        "raw_count": diagnostics.raw_count,
        "accepted_count": diagnostics.accepted_count,
        "accepted_status_counts": diagnostics.accepted_status_counts,
        "excluded_counts": diagnostics.excluded_counts,
        "source_artifact_sha256": diagnostics.source_artifact_sha256,
    }


def _missing_history_analytics(venue: str) -> dict[str, Any]:
    return {
        "fixture_count": None,
        "overall_wdl": None,
        "venue": venue,
        "venue_played": 0,
        "venue_wdl": None,
        "points_per_game": None,
        "last5_form_points": None,
        "rest_days": None,
        "declared_history_count": 0,
        "declared_venue_count": 0,
        "raw_count": 0,
        "accepted_count": 0,
        "accepted_status_counts": {},
        "excluded_counts": {"target_fixture_missing": 1},
        "source_artifact_sha256": None,
    }


def _merge_probability_analytics(
    base: Mapping[str, Any],
    probability: Any,
) -> Mapping[str, Any]:
    row = dict(base)
    bk = tuple(probability.bk_probabilities)
    sports = tuple(probability.sports_probabilities)
    blend = tuple(probability.candidate_blend_probabilities)
    row.update(
        {
            "probability_source": probability.probability_source,
            "fallback_reason": probability.fallback_reason,
            "blend_weight": probability.blend_weight,
            "bk_probabilities": list(bk),
            "sports_probabilities": list(sports),
            "candidate_blend_probabilities": list(blend),
            "candidate_minus_bk": [
                blend_value - bk_value
                for blend_value, bk_value in zip(blend, bk, strict=True)
            ],
        }
    )
    return row


def _validate_equal_full_packages(
    *,
    baseline_coupons: tuple[str, ...],
    sports_coupons: tuple[str, ...],
    baseline_cost: int,
    sports_cost: int,
    bank: int,
    capacity: int,
) -> None:
    for name, coupons, cost in (
        ("baseline", baseline_coupons, baseline_cost),
        ("sports", sports_coupons, sports_cost),
    ):
        if len(coupons) != capacity or len(set(coupons)) != capacity:
            raise ValueError(f"{name} package must contain {capacity} unique coupons")
        if cost != bank:
            raise ValueError(f"{name} package must use the exact bank")
        if any(
            len(coupon) != 15 or any(outcome not in _OUTCOMES for outcome in coupon)
            for coupon in coupons
        ):
            raise ValueError(f"{name} package contains an invalid coupon")


def _event_exposures(
    baseline: tuple[str, ...], sports: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows = []
    for order in _EXPECTED_ORDERS:
        left = {
            outcome: sum(coupon[order] == outcome for coupon in baseline)
            for outcome in _OUTCOMES
        }
        right = {
            outcome: sum(coupon[order] == outcome for coupon in sports)
            for outcome in _OUTCOMES
        }
        rows.append(
            {
                "event_order": order,
                "event_number": order + 1,
                "baseline": left,
                "sports_candidate": right,
                "delta": {
                    outcome: right[outcome] - left[outcome]
                    for outcome in _OUTCOMES
                },
            }
        )
    return rows


def _research_package_csv(
    *,
    drawing_number: int | None,
    role: str,
    stake: int,
    coupons: tuple[str, ...],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "artifact_class",
            "operator_compatible",
            "drawing_number",
            "package_role",
            "coupon_number",
            "research_stake_rub",
            "coupon_compact",
            *(f"outcome_{number:02d}" for number in range(1, 16)),
        )
    )
    for number, coupon in enumerate(coupons, start=1):
        writer.writerow(
            (
                ARTIFACT_CLASS,
                "false",
                drawing_number,
                role,
                number,
                stake,
                coupon,
                *coupon,
            )
        )
    return stream.getvalue().encode("utf-8")


def _research_package_text(
    *, role: str, stake: int, coupons: tuple[str, ...]
) -> bytes:
    lines = [
        "RESEARCH ONLY / PAPER ONLY / NOT ACTIVATED / DO NOT WAGER",
        "NOT A BALTBet UPLOAD FILE; OPERATOR-COMPATIBLE FORMAT IS "
        "DELIBERATELY DISABLED",
        f"PACKAGE ROLE: {role}",
        f"RESEARCH STAKE: {stake} RUB; COUPONS: {len(coupons)}",
        "",
    ]
    lines.extend(
        f"RESEARCH_COUPON_{number:03d} | {' '.join(coupon)}"
        for number, coupon in enumerate(coupons, start=1)
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _comparison_markdown(report: Mapping[str, Any]) -> bytes:
    baseline = _mapping(report["baseline"], "baseline report")
    sports = _mapping(report["sports_candidate"], "sports report")
    comparison = _mapping(report["comparison"], "comparison report")
    lines = [
        "# GOAL sports-shadow dual-package comparison",
        "",
        "**RESEARCH ONLY / PAPER ONLY / NOT ACTIVATED / DO NOT WAGER**",
        "",
        "These files are deliberately not compatible with BaltBet operator upload.",
        "No scheduler, operator-result, PLAY marker, or wager state was written.",
        "",
        f"- Drawing: {report['drawing_number']} (id {report['drawing_id']})",
        f"- Frozen as-of: {report['as_of']}",
        f"- Bank/stake: {report['bank']} / {report['stake']} RUB",
        f"- Coupons in each package: {report['coupon_limit']}",
        f"- Sports coverage: {report['sports_coverage_count']}/15",
        f"- BK package cost: {baseline['cost']}",
        f"- Sports package cost: {sports['cost']}",
        f"- Coupon overlap: {comparison['overlap_count']} / {report['coupon_limit']}",
        f"- Baseline only: {comparison['baseline_only_count']}",
        f"- Sports only: {comparison['sports_only_count']}",
        "",
        "## Exposure deltas (sports minus baseline)",
        "",
        "| Match | 1 | X | 2 |",
        "|---:|---:|---:|---:|",
    ]
    for row in comparison["event_exposures"]:
        delta = row["delta"]
        lines.append(
            f"| {row['event_number']} | {delta['1']:+d} | "
            f"{delta['X']:+d} | {delta['2']:+d} |"
        )
    lines.extend(
        (
            "",
            "Modeled probability/EV values are diagnostics, not a profit forecast.",
            "One drawing cannot establish superiority or profitability.",
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _analytics_markdown(rows: Sequence[Mapping[str, Any]]) -> bytes:
    lines = [
        "# Per-match GOAL sports-shadow analytics",
        "",
        "**RESEARCH ONLY / PAPER ONLY / NOT ACTIVATED / DO NOT WAGER**",
        "",
        "Only strictly pre-as-of, pre-kickoff terminal history is included. ",
        "Venue evidence is home-team home W-D-L plus away-team away W-D-L; ",
        "the sample-size weight shrinks the candidate toward TotoBrief BK.",
        "",
        "| # | Match | Home venue W-D-L | Away venue W-D-L | Weight | "
        "BK 1/X/2 | Candidate 1/X/2 | Delta 1/X/2 |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        home = row["home_history"]
        away = row["away_history"]
        lines.append(
            "| {number} | {home_team} — {away_team} | {home_wdl} | {away_wdl} | "
            "{weight:.4f} | {bk} | {candidate} | {delta} |".format(
                number=row["event_number"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                home_wdl=_wdl(home["venue_wdl"]),
                away_wdl=_wdl(away["venue_wdl"]),
                weight=row["blend_weight"],
                bk=_probability_text(row["bk_probabilities"]),
                candidate=_probability_text(
                    row["candidate_blend_probabilities"]
                ),
                delta=" / ".join(
                    f"{value:+.4f}" for value in row["candidate_minus_bk"]
                ),
            )
        )
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _analytics_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    fieldnames = (
        "artifact_class",
        "event_number",
        "event_id",
        "home_team",
        "away_team",
        "target_starts_at",
        "home_venue_played",
        "home_venue_wdl",
        "away_venue_played",
        "away_venue_wdl",
        "blend_weight",
        "bk_1",
        "bk_x",
        "bk_2",
        "sports_1",
        "sports_x",
        "sports_2",
        "blend_1",
        "blend_x",
        "blend_2",
        "delta_1",
        "delta_x",
        "delta_2",
        "fallback_reason",
    )
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        home = row["home_history"]
        away = row["away_history"]
        writer.writerow(
            {
                "artifact_class": ARTIFACT_CLASS,
                "event_number": row["event_number"],
                "event_id": row["event_id"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "target_starts_at": row["target_starts_at"],
                "home_venue_played": home["venue_played"],
                "home_venue_wdl": _wdl(home["venue_wdl"]),
                "away_venue_played": away["venue_played"],
                "away_venue_wdl": _wdl(away["venue_wdl"]),
                "blend_weight": row["blend_weight"],
                "bk_1": row["bk_probabilities"][0],
                "bk_x": row["bk_probabilities"][1],
                "bk_2": row["bk_probabilities"][2],
                "sports_1": row["sports_probabilities"][0],
                "sports_x": row["sports_probabilities"][1],
                "sports_2": row["sports_probabilities"][2],
                "blend_1": row["candidate_blend_probabilities"][0],
                "blend_x": row["candidate_blend_probabilities"][1],
                "blend_2": row["candidate_blend_probabilities"][2],
                "delta_1": row["candidate_minus_bk"][0],
                "delta_x": row["candidate_minus_bk"][1],
                "delta_2": row["candidate_minus_bk"][2],
                "fallback_reason": row["fallback_reason"],
            }
        )
    return stream.getvalue().encode("utf-8")


def _research_output_directory(root: Path, output_dir: str | Path) -> Path:
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    research_root = (root / "reports" / "research").resolve()
    try:
        output.relative_to(research_root)
    except ValueError as error:
        raise ValueError("output_dir must be inside reports/research") from error
    return output


def _declared_file(root: Path, value: object, name: str) -> Path:
    declared = _nonempty_text(value, name)
    path = Path(declared)
    if not path.is_absolute():
        path = root / path
    return _contained_file(root, path)


def _contained_file(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("input file must be inside the project root") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError("input must be a regular non-symlink file")
    return resolved


def _contained_directory(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("input directory must be inside the project root") from error
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("input must be a regular non-symlink directory")
    return resolved


def _json_object(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, f"JSON object {path.name}")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _event_order(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in range(15):
        raise ValueError("event order must be in range 0 through 14")
    return value


def _require_exact(observed: object, expected: object, name: str) -> None:
    if observed != expected or type(observed) is not type(expected):
        raise ValueError(f"{name} mismatch")


def _nonempty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if result < 0 or str(result) != str(value).strip():
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO UTC datetime")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO UTC datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _iso(value: datetime) -> str:
    _utc("datetime", value)
    return value.isoformat().replace("+00:00", "Z")


def _sha256_json(value: object, *, ensure_ascii: bool = False) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _pretty_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _wdl(value: object) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return "n/a"
    return "-".join(str(item) for item in value)


def _probability_text(values: Sequence[float]) -> str:
    if len(values) != 3 or any(not math.isfinite(value) for value in values):
        raise ValueError("probability row is invalid")
    return " / ".join(f"{value:.4f}" for value in values)
