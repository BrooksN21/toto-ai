"""Paper-only comparison of BK and experimental sports-shadow packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.models import EVConfig, EVInput
from toto_ai.ev.package import select_ev_package_with_top_coupons
from toto_ai.ev.package_quality import package_quality_metrics
from toto_ai.ev.ternary import compute_ev_components, materialize_ev_surface
from toto_ai.sports_stats.probabilities import load_shadow_probability_artifact


def compare_preliminary_packages(
    *,
    drawing_id: int,
    bank: int,
    stake: int,
    as_of: datetime,
    raw_cache_dir: str | Path,
    sports_artifact_path: str | Path,
    output_dir: str | Path,
    monte_carlo_samples: int = 2_048,
) -> tuple[dict[str, object], Path, Path, Path]:
    """Build two equal-budget research packages and compare their evidence."""

    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    observed = as_of.astimezone(timezone.utc)
    raw_root = Path(raw_cache_dir).resolve()
    record = load_drawing_detail_cache(
        drawing_id,
        cache_dir=raw_root,
        max_age_seconds=None,
        now=observed,
        allowed_root=raw_root,
    )
    if record.fetched_at > observed:
        raise ValueError("drawing detail cache was captured after comparison as-of")
    sports = load_shadow_probability_artifact(sports_artifact_path)
    if sports.drawing_id != drawing_id:
        raise ValueError("sports shadow drawing identity mismatch")
    if sports.as_of > observed:
        raise ValueError("sports shadow was generated after comparison as-of")
    config = EVConfig(bank=bank, stake=stake, mode="research")
    baseline_input = ev_input_from_payload(
        record.payload,
        fetched_at=record.fetched_at.isoformat(),
        stake=stake,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    sports_probabilities = tuple(
        tuple(event.candidate_blend_probabilities) for event in sports.events
    )
    sports_input = replace(
        baseline_input,
        true_probabilities=sports_probabilities,
        probability_sources=tuple(
            event.probability_source for event in sports.events
        ),
    )
    baseline = _package(baseline_input, config)
    candidate = _package(sports_input, config)
    baseline_coupons = tuple(item.coupon for item in baseline.coupons)
    candidate_coupons = tuple(item.coupon for item in candidate.coupons)
    overlap = len(set(baseline_coupons) & set(candidate_coupons))
    baseline_quality = package_quality_metrics(
        baseline_coupons,
        baseline_input.true_probabilities,
        seed_material=f"preliminary-bk-{drawing_id}-{record.payload_sha256}",
        monte_carlo_samples=monte_carlo_samples,
    )
    candidate_quality = package_quality_metrics(
        candidate_coupons,
        sports_input.true_probabilities,
        seed_material=(
            f"preliminary-sports-{drawing_id}-{sports.artifact_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    baseline_under_sports = package_quality_metrics(
        baseline_coupons,
        sports_input.true_probabilities,
        seed_material=(
            f"preliminary-bk-under-sports-{drawing_id}-{sports.artifact_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    candidate_under_bk = package_quality_metrics(
        candidate_coupons,
        baseline_input.true_probabilities,
        seed_material=(
            f"preliminary-sports-under-bk-{drawing_id}-{record.payload_sha256}"
        ),
        monte_carlo_samples=monte_carlo_samples,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "PAPER_ONLY_NOT_ACTIVATED",
        "drawing_id": drawing_id,
        "drawing_number": baseline_input.drawing_number,
        "as_of": observed.isoformat().replace("+00:00", "Z"),
        "bank": bank,
        "stake": stake,
        "coupon_limit": bank // stake,
        "sports_shadow_status": sports.status,
        "sports_model_status": sports.model_status,
        "sports_coverage_count": sports.sports_coverage_count,
        "sports_fallback_count": sports.fallback_count,
        "sports_validation_failures": list(sports.validation_failures),
        "analytics_effective": sports.sports_coverage_count > 0,
        "baseline": _package_payload(
            baseline,
            baseline_coupons,
            asdict(baseline_quality),
        ),
        "sports_candidate": _package_payload(
            candidate,
            candidate_coupons,
            asdict(candidate_quality),
        ),
        "cross_evaluation": {
            "baseline_under_sports": asdict(baseline_under_sports),
            "sports_candidate_under_bk": asdict(candidate_under_bk),
        },
        "comparison": {
            "overlap_count": overlap,
            "overlap_share": overlap / len(baseline_coupons),
            "baseline_only_count": len(set(baseline_coupons) - set(candidate_coupons)),
            "sports_only_count": len(set(candidate_coupons) - set(baseline_coupons)),
            "identical": baseline_coupons == candidate_coupons,
            "event_exposure_differences": _exposure_differences(
                baseline_coupons, candidate_coupons
            ),
        },
        "inputs": {
            "drawing_payload_sha256": record.payload_sha256,
            "sports_artifact_sha256": sports.artifact_sha256,
        },
        "automatic_wagering": False,
        "real_money_actionable": False,
        "modeled_ev_is_validated_profit_forecast": False,
        "interpretation": (
            "sports evidence changed no event probability; both packages are "
            "the same BK-control package"
            if sports.sports_coverage_count == 0
            else "sports evidence changed at least one event probability; "
            "the candidate remains shadow-only"
        ),
    }
    unsigned = _canonical(report)
    report["report_sha256"] = hashlib.sha256(unsigned).hexdigest()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "preliminary-package-comparison.json"
    baseline_path = output / "baseline-bk-package.txt"
    sports_path = output / "sports-shadow-package.txt"
    markdown_path = output / "preliminary-package-comparison.md"
    _write_replace(json_path, _pretty(report))
    _write_replace(baseline_path, _package_text(stake, baseline_coupons))
    _write_replace(sports_path, _package_text(stake, candidate_coupons))
    _write_replace(markdown_path, _markdown(report).encode("utf-8"))
    return report, json_path, baseline_path, sports_path


def _package(ev_input: EVInput, config: EVConfig):
    components = compute_ev_components(ev_input)
    surface = materialize_ev_surface(
        components,
        ev_input.possible_winnings,
        ev_input.jackpot,
    )
    package, _top = select_ev_package_with_top_coupons(
        surface,
        config,
        diagnostic_limit=0,
    )
    return package


def _package_payload(package, coupons, quality):
    return {
        "coupon_count": len(coupons),
        "cost": package.cost,
        "unused_bank": package.unused_bank,
        "expected_payout": package.expected_payout,
        "modeled_roi": package.modeled_roi,
        "package_sha256": hashlib.sha256(",".join(coupons).encode()).hexdigest(),
        "quality": quality,
    }


def _exposure_differences(
    left: tuple[str, ...], right: tuple[str, ...]
) -> list[dict[str, object]]:
    rows = []
    for order in range(15):
        left_counts = {
            outcome: sum(c[order] == outcome for c in left)
            for outcome in "1X2"
        }
        right_counts = {
            outcome: sum(c[order] == outcome for c in right) for outcome in "1X2"
        }
        if left_counts != right_counts:
            rows.append(
                {
                    "event_order": order,
                    "event_number": order + 1,
                    "baseline": left_counts,
                    "sports_candidate": right_counts,
                }
            )
    return rows


def _package_text(stake: int, coupons: tuple[str, ...]) -> bytes:
    return "".join(
        f"{stake}; " + "; ".join(coupon) + "\n" for coupon in coupons
    ).encode("utf-8")


def _markdown(report: dict[str, object]) -> str:
    baseline = report["baseline"]
    candidate = report["sports_candidate"]
    comparison = report["comparison"]
    baseline_quality = baseline["quality"]
    candidate_quality = candidate["quality"]
    return "\n".join(
        (
            "# Preliminary package comparison",
            "",
            "**PAPER ONLY / NOT ACTIVATED / DO NOT WAGER**",
            "",
            f"- Drawing: {report['drawing_number']}",
            f"- Bank/stake: {report['bank']} / {report['stake']}",
            f"- Sports coverage: {report['sports_coverage_count']}/15",
            f"- Sports fallback: {report['sports_fallback_count']}/15",
            f"- BK coupons/cost: {baseline['coupon_count']} / {baseline['cost']}",
            f"- Sports coupons/cost: {candidate['coupon_count']} / {candidate['cost']}",
            f"- Coupon overlap: {comparison['overlap_count']}",
            f"- Identical: {comparison['identical']}",
            f"- BK modeled P(13+): {baseline_quality['probability_at_least_13']:.8f}",
            "- Sports modeled P(13+): "
            f"{candidate_quality['probability_at_least_13']:.8f}",
            f"- Interpretation: {report['interpretation']}",
            "- EV/ROI fields are unvalidated model diagnostics, not a profit forecast.",
            "",
        )
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
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


def _write_replace(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
