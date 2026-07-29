"""Canonical package metadata and exact union-brief audit."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import chain, product
from numbers import Real
from pathlib import Path
from typing import Any, Literal

AUDIT_SCHEMA_VERSION = 1
EVENT_COUNT = 15
OUTCOMES = ("1", "X", "2")
DEFAULT_NEAR_FIXED_SHARE = 0.95
DEFAULT_LOW_PROBABILITY_THRESHOLD = 0.20
DEFAULT_MAX_DISTANCE_COMPARISONS = 10_000_000


class PackageStrategy(str, Enum):
    COVER = "cover"
    EV = "ev"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class PackageSafetyConfig:
    """Fail-closed thresholds applied before a playable package is published."""

    near_fixed_share: float = DEFAULT_NEAR_FIXED_SHARE
    low_probability_threshold: float = DEFAULT_LOW_PROBABILITY_THRESHOLD
    material_probability_threshold: float = DEFAULT_LOW_PROBABILITY_THRESHOLD

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "near_fixed_share",
            _probability_threshold(
                self.near_fixed_share,
                "near_fixed_share",
                lower_inclusive=False,
            ),
        )
        object.__setattr__(
            self,
            "low_probability_threshold",
            _probability_threshold(
                self.low_probability_threshold,
                "low_probability_threshold",
            ),
        )
        object.__setattr__(
            self,
            "material_probability_threshold",
            _probability_threshold(
                self.material_probability_threshold,
                "material_probability_threshold",
                lower_inclusive=False,
            ),
        )


@dataclass(frozen=True)
class PackageSafetyResult:
    decision: Literal["PLAY", "NO BET"]
    reason_codes: tuple[str, ...]
    reasons: tuple[dict[str, Any], ...]
    config: PackageSafetyConfig
    evaluated_coupons: tuple[str, ...]
    package_sha256: str
    probability_input_sha256: str
    probabilities: tuple[tuple[float, float, float], ...]
    uploadable_coupons: tuple[str, ...]
    safety_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_package_safety(
    coupons: Sequence[str],
    probabilities: Sequence[Sequence[float]],
    *,
    config: PackageSafetyConfig | None = None,
) -> PackageSafetyResult:
    """Reject unsafe concentration without changing Cover Engine mathematics."""
    config = PackageSafetyConfig() if config is None else config
    if not isinstance(config, PackageSafetyConfig):
        raise ValueError("config must be a PackageSafetyConfig")
    canonical = validate_coupons(coupons)
    probability_rows = _validate_probabilities(probabilities)
    if probability_rows is None:  # pragma: no cover - required by the signature
        raise ValueError("probabilities are required for package safety")
    exposures = _event_exposures(canonical)
    reasons = _warnings(
        exposures,
        probability_rows,
        config.near_fixed_share,
        config.low_probability_threshold,
    )
    for exposure, row in zip(exposures, probability_rows, strict=True):
        for outcome, probability in zip(OUTCOMES, row, strict=True):
            if (
                probability >= config.material_probability_threshold
                and exposure.counts[outcome] == 0
            ):
                reasons.append(
                    {
                        "code": "zero_exposure_material_outcome",
                        "event": exposure.event,
                        "outcome": outcome,
                        "probability": probability,
                        "threshold": config.material_probability_threshold,
                    }
                )
    reason_codes = tuple(sorted({str(reason["code"]) for reason in reasons}))
    decision = "NO BET" if reasons else "PLAY"
    probability_hash = canonical_probability_input_sha256(probability_rows)
    package_hash = hashlib.sha256(",".join(canonical).encode("utf-8")).hexdigest()
    uploadable = () if reasons else canonical
    safety_hash = _sha256(
        {
            "decision": decision,
            "reason_codes": reason_codes,
            "reasons": reasons,
            "config": asdict(config),
            "evaluated_coupons": canonical,
            "package_sha256": package_hash,
            "probability_input_sha256": probability_hash,
            "probabilities": probability_rows,
            "uploadable_coupons": uploadable,
        }
    )
    return PackageSafetyResult(
        decision=decision,
        reason_codes=reason_codes,
        reasons=tuple(reasons),
        config=config,
        evaluated_coupons=canonical,
        package_sha256=package_hash,
        probability_input_sha256=probability_hash,
        probabilities=probability_rows,
        uploadable_coupons=uploadable,
        safety_sha256=safety_hash,
    )


def canonical_probability_input_sha256(
    probabilities: Sequence[Sequence[float]],
) -> str:
    """Hash one validated 15×3 probability matrix for every package boundary."""
    rows = _validate_probabilities(probabilities)
    if rows is None:  # pragma: no cover - required by the public signature
        raise ValueError("probabilities are required")
    return _sha256([list(row) for row in rows])


@dataclass(frozen=True)
class BankMetadata:
    requested: int
    effective: int
    used: int
    stake: int
    coupon_count: int


@dataclass(frozen=True)
class EventExposure:
    event: int
    counts: dict[str, int]
    percentages: dict[str, float]
    fixed_outcome: str | None
    maximum_share: float


@dataclass(frozen=True)
class PackageAudit:
    schema_version: int
    strategy: str
    drawing_id: int | None
    target_category: int | None
    bank: BankMetadata
    coupons: tuple[str, ...]
    package_sha256: str
    union_brief: tuple[str, ...]
    union_brief_variant_count: int
    event_exposures: tuple[EventExposure, ...]
    fixed_events: tuple[int, ...]
    near_fixed_events: tuple[int, ...]
    worst_minimum_distance: int
    guaranteed_hits: int
    guaranteed_category: int | None
    minimum_distance_distribution: dict[int, int]
    category_coverage: dict[int, dict[str, int | float | bool]]
    conditional_category_probabilities: dict[int, float] | None
    union_brief_probability: float | None
    probability_input_sha256: str | None
    audit_config: dict[str, int | float]
    audit_hash_payload: dict[str, Any]
    warnings: tuple[dict[str, Any], ...]
    audit_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_package(
    path: str | Path,
    *,
    max_coupons: int | None = None,
) -> tuple[str, ...]:
    """Load CSV or line-oriented coupons and validate the canonical package."""
    if max_coupons is not None and (
        isinstance(max_coupons, bool)
        or not isinstance(max_coupons, int)
        or max_coupons <= 0
    ):
        raise ValueError("max_coupons must be a positive integer.")
    package_path = Path(path)
    with package_path.open(newline="", encoding="utf-8") as source:
        raw = []
        rows = csv.reader(source)
        first = next(rows, None)
        if first is None:
            raise ValueError("Package must contain at least one coupon.")
        header = [value.strip().lower() for value in first]
        coupon_index = header.index("coupon") if "coupon" in header else None
        pending = rows if coupon_index is not None else chain((first,), rows)
        start = 2 if coupon_index is not None else 1
        for line, row in enumerate(pending, start=start):
            if coupon_index is not None:
                if len(row) <= coupon_index or not row[coupon_index].strip():
                    raise ValueError(f"Malformed package row at line {line}.")
                raw.append(row[coupon_index])
                if max_coupons is not None and len(raw) > max_coupons:
                    raise ValueError(
                        f"Package exceeds maximum {max_coupons} coupons at line {line}."
                    )
                continue
            if not row or not any(cell.strip() for cell in row):
                raise ValueError(f"Blank package row at line {line}.")
            if len(row) == 1:
                semicolon_cells = [value.strip() for value in row[0].split(";")]
                if len(semicolon_cells) == 16 and semicolon_cells[0].isdigit():
                    raw.append("".join(semicolon_cells[1:]))
                elif ";" in row[0]:
                    raise ValueError(f"Malformed package row at line {line}.")
                else:
                    raw.append(row[0])
            else:
                cells = [cell.strip() for cell in row]
                if len(cells) == 16 and cells[0].isdigit():
                    raw.append("".join(cells[1:]))
                else:
                    raise ValueError(f"Unrecognized package row at line {line}.")
            if max_coupons is not None and len(raw) > max_coupons:
                raise ValueError(
                    f"Package exceeds maximum {max_coupons} coupons at line {line}."
                )
    return validate_coupons(raw)


def validate_coupons(coupons: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(str(coupon).strip().upper() for coupon in coupons)
    if not normalized:
        raise ValueError("Package must contain at least one coupon.")
    for index, coupon in enumerate(normalized, start=1):
        if len(coupon) != EVENT_COUNT:
            raise ValueError(f"Coupon {index} must contain exactly 15 outcomes.")
        if set(coupon) - set(OUTCOMES):
            raise ValueError(f"Coupon {index} may contain only 1, X, and 2.")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Package coupons must be unique.")
    return normalized


def validate_bank(
    *,
    requested: int,
    effective: int | None,
    stake: int,
    coupon_count: int,
) -> BankMetadata:
    for name, value in (("requested bank", requested), ("stake", stake)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    if requested % stake:
        raise ValueError("Requested bank must be a multiple of stake.")
    effective_value = requested if effective is None else effective
    if (
        isinstance(effective_value, bool)
        or not isinstance(effective_value, int)
        or effective_value <= 0
    ):
        raise ValueError("Effective bank must be a positive integer.")
    if effective_value % stake:
        raise ValueError("Effective bank must be a multiple of stake.")
    if effective_value > requested:
        raise ValueError("Effective bank cannot exceed requested bank.")
    used = coupon_count * stake
    if used > effective_value:
        raise ValueError("Package cost exceeds effective bank.")
    return BankMetadata(
        requested=requested,
        effective=effective_value,
        used=used,
        stake=stake,
        coupon_count=coupon_count,
    )


def build_package_audit(
    coupons: Sequence[str],
    *,
    strategy: PackageStrategy | str,
    requested_bank: int,
    stake: int = 30,
    effective_bank: int | None = None,
    drawing_id: int | None = None,
    target_category: int | None = None,
    probabilities: Sequence[Sequence[float]] | None = None,
    near_fixed_share: float = DEFAULT_NEAR_FIXED_SHARE,
    low_probability_threshold: float = DEFAULT_LOW_PROBABILITY_THRESHOLD,
    max_distance_comparisons: int = DEFAULT_MAX_DISTANCE_COMPARISONS,
) -> PackageAudit:
    canonical = validate_coupons(coupons)
    strategy_value = PackageStrategy(strategy).value
    if (
        strategy_value == PackageStrategy.COVER.value
        and target_category not in (13, 14, 15)
    ):
        raise ValueError("Target category must be one of 13, 14, or 15.")
    if strategy_value != PackageStrategy.COVER.value and target_category is not None:
        raise ValueError("Only cover packages may declare a target category.")
    if not 0 < near_fixed_share <= 1:
        raise ValueError("near_fixed_share must be in (0, 1].")
    if not 0 <= low_probability_threshold <= 1:
        raise ValueError("low_probability_threshold must be in [0, 1].")

    bank = validate_bank(
        requested=requested_bank,
        effective=effective_bank,
        stake=stake,
        coupon_count=len(canonical),
    )
    probability_rows = _validate_probabilities(probabilities)
    exposures = _event_exposures(canonical)
    brief = tuple(
        "".join(outcome for outcome in OUTCOMES if exposure.counts[outcome])
        for exposure in exposures
    )
    variant_count = math.prod(len(position) for position in brief)
    if (
        isinstance(max_distance_comparisons, bool)
        or not isinstance(max_distance_comparisons, int)
        or max_distance_comparisons <= 0
    ):
        raise ValueError("max_distance_comparisons must be a positive integer.")
    comparisons = variant_count * len(canonical)
    if comparisons > max_distance_comparisons:
        raise ValueError(
            f"Exact audit requires {comparisons} variant*coupon comparisons; "
            f"configured limit is {max_distance_comparisons}."
        )
    distribution: dict[int, int] = {}
    probability_masses = {category: 0.0 for category in range(15, 8, -1)}
    brief_mass = 0.0
    for values in product(*brief):
        variant = "".join(values)
        distance = min(
            sum(a != b for a, b in zip(variant, coupon, strict=True))
            for coupon in canonical
        )
        distribution[distance] = distribution.get(distance, 0) + 1
        if probability_rows is not None:
            mass = math.prod(
                probability_rows[index][OUTCOMES.index(outcome)]
                for index, outcome in enumerate(variant)
            )
            brief_mass += mass
            for category in probability_masses:
                if distance <= EVENT_COUNT - category:
                    probability_masses[category] += mass
    worst_distance = max(distribution)
    coverage = _category_coverage(distribution, variant_count)
    if target_category is not None and not coverage[target_category]["guarantee"]:
        raise ValueError(
            f"Cover target category {target_category} does not verify exactly."
        )
    warnings = _warnings(
        exposures,
        probability_rows,
        near_fixed_share,
        low_probability_threshold,
    )
    package_hash = hashlib.sha256(",".join(canonical).encode("utf-8")).hexdigest()
    probability_hash = (
        _sha256([list(row) for row in probability_rows])
        if probability_rows is not None
        else None
    )
    guaranteed_hits = EVENT_COUNT - worst_distance
    guaranteed_category = guaranteed_hits if guaranteed_hits >= 9 else None
    conditional = (
        {
            category: mass / brief_mass if brief_mass else 0.0
            for category, mass in probability_masses.items()
        }
        if probability_rows is not None
        else None
    )
    base: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "strategy": strategy_value,
        "drawing_id": drawing_id,
        "target_category": target_category,
        "bank": asdict(bank),
        "coupons": list(canonical),
        "package_sha256": package_hash,
        "union_brief": list(brief),
        "union_brief_variant_count": variant_count,
        "event_exposures": [asdict(item) for item in exposures],
        "fixed_events": [
            exposure.event for exposure in exposures if exposure.fixed_outcome
        ],
        "near_fixed_events": [
            exposure.event
            for exposure in exposures
            if exposure.maximum_share >= near_fixed_share
        ],
        "worst_minimum_distance": worst_distance,
        "guaranteed_hits": guaranteed_hits,
        "guaranteed_category": guaranteed_category,
        "minimum_distance_distribution": distribution,
        "category_coverage": coverage,
        "conditional_category_probabilities": conditional,
        "union_brief_probability": brief_mass if probability_rows is not None else None,
        "probability_input_sha256": probability_hash,
        "audit_config": {
            "near_fixed_share": near_fixed_share,
            "low_probability_threshold": low_probability_threshold,
            "max_distance_comparisons": max_distance_comparisons,
        },
        "warnings": warnings,
    }
    audit_hash_payload = json.loads(
        json.dumps(base, ensure_ascii=False, sort_keys=True)
    )
    audit_hash = _sha256(audit_hash_payload)
    return PackageAudit(
        schema_version=AUDIT_SCHEMA_VERSION,
        strategy=strategy_value,
        drawing_id=drawing_id,
        target_category=target_category,
        bank=bank,
        coupons=canonical,
        package_sha256=package_hash,
        union_brief=brief,
        union_brief_variant_count=variant_count,
        event_exposures=exposures,
        fixed_events=tuple(base["fixed_events"]),
        near_fixed_events=tuple(base["near_fixed_events"]),
        worst_minimum_distance=worst_distance,
        guaranteed_hits=guaranteed_hits,
        guaranteed_category=guaranteed_category,
        minimum_distance_distribution=distribution,
        category_coverage=coverage,
        conditional_category_probabilities=base[
            "conditional_category_probabilities"
        ],
        union_brief_probability=base["union_brief_probability"],
        probability_input_sha256=probability_hash,
        audit_config=base["audit_config"],
        audit_hash_payload=audit_hash_payload,
        warnings=tuple(warnings),
        audit_sha256=audit_hash,
    )


def recompute_audit_sha256(
    payload_or_report: dict[str, Any],
) -> str:
    """Recompute and verify an audit hash from its payload or complete report."""
    if not isinstance(payload_or_report, dict):
        raise ValueError("Audit report must be a JSON object.")
    is_report = "audit_hash_payload" in payload_or_report
    embedded_payload = payload_or_report.get("audit_hash_payload")
    payload = embedded_payload if is_report else payload_or_report
    if not isinstance(payload, dict):
        raise ValueError("Audit hash payload must be a JSON object.")
    if is_report:
        for field, expected in payload.items():
            if field not in payload_or_report:
                raise ValueError(
                    f"Audit report is missing hash-bound field {field!r}."
                )
            displayed = _json_compatible(payload_or_report[field])
            if displayed != expected:
                raise ValueError(
                    f"Audit report hash-bound field {field!r} does not match "
                    "audit_hash_payload."
                )
    recomputed = _sha256(payload)
    stored_hash = payload_or_report.get("audit_sha256")
    if is_report and stored_hash != recomputed:
        raise ValueError("Audit report audit_sha256 does not match its payload.")
    return recomputed


def _json_compatible(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _event_exposures(coupons: tuple[str, ...]) -> tuple[EventExposure, ...]:
    result = []
    total = len(coupons)
    for position in range(EVENT_COUNT):
        counts = {outcome: 0 for outcome in OUTCOMES}
        for coupon in coupons:
            counts[coupon[position]] += 1
        percentages = {
            outcome: counts[outcome] / total for outcome in OUTCOMES
        }
        fixed = next(
            (outcome for outcome in OUTCOMES if counts[outcome] == total),
            None,
        )
        result.append(
            EventExposure(
                event=position + 1,
                counts=counts,
                percentages=percentages,
                fixed_outcome=fixed,
                maximum_share=max(percentages.values()),
            )
        )
    return tuple(result)


def _category_coverage(
    distribution: dict[int, int],
    variant_count: int,
) -> dict[int, dict[str, int | float | bool]]:
    return {
        category: {
            "covered_variants": sum(
                count
                for distance, count in distribution.items()
                if distance <= EVENT_COUNT - category
            ),
            "total_variants": variant_count,
            "share": sum(
                count
                for distance, count in distribution.items()
                if distance <= EVENT_COUNT - category
            )
            / variant_count,
            "guarantee": max(distribution) <= EVENT_COUNT - category,
        }
        for category in range(15, 8, -1)
    }


def _validate_probabilities(
    probabilities: Sequence[Sequence[float]] | None,
) -> tuple[tuple[float, float, float], ...] | None:
    if probabilities is None:
        return None
    if len(probabilities) != EVENT_COUNT:
        raise ValueError("Probabilities must contain exactly 15 event triplets.")
    result = []
    for index, row in enumerate(probabilities, start=1):
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
            raise ValueError(f"Event {index} probabilities must contain 1/X/2.")
        if len(row) != 3:
            raise ValueError(f"Event {index} probabilities must contain 1/X/2.")
        if any(
            isinstance(value, bool) or not isinstance(value, Real) for value in row
        ):
            raise ValueError(
                f"Event {index} probabilities must be real numeric values."
            )
        values = tuple(float(value) for value in row)
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError(
                f"Event {index} probabilities must be finite and non-negative."
            )
        if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"Event {index} probabilities must sum to 1.")
        result.append(values)
    return tuple(result)


def _conditional_probabilities(
    variant_distances: tuple[tuple[str, int | None], ...],
    probabilities: tuple[tuple[float, float, float], ...] | None,
) -> dict[int, float] | None:
    if probabilities is None:
        return None
    masses: list[tuple[int, float]] = []
    for variant, distance in variant_distances:
        if distance is None:
            continue
        mass = math.prod(
            probabilities[index][OUTCOMES.index(outcome)]
            for index, outcome in enumerate(variant)
        )
        masses.append((distance, mass))
    brief_mass = sum(mass for _, mass in masses)
    if brief_mass == 0:
        return {category: 0.0 for category in range(15, 8, -1)}
    return {
        category: sum(
            mass
            for distance, mass in masses
            if distance <= EVENT_COUNT - category
        )
        / brief_mass
        for category in range(15, 8, -1)
    }


def _warnings(
    exposures: tuple[EventExposure, ...],
    probabilities: tuple[tuple[float, float, float], ...] | None,
    near_fixed_share: float,
    low_probability_threshold: float,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for exposure in exposures:
        if exposure.maximum_share >= near_fixed_share:
            outcome = max(OUTCOMES, key=exposure.counts.__getitem__)
            warnings.append(
                {
                    "code": "extreme_concentration",
                    "event": exposure.event,
                    "outcome": outcome,
                    "share": exposure.maximum_share,
                }
            )
        if probabilities is not None and exposure.fixed_outcome is not None:
            probability = probabilities[exposure.event - 1][
                OUTCOMES.index(exposure.fixed_outcome)
            ]
            if probability < low_probability_threshold:
                warnings.append(
                    {
                        "code": "fixed_low_probability_outcome",
                        "event": exposure.event,
                        "outcome": exposure.fixed_outcome,
                        "probability": probability,
                        "threshold": low_probability_threshold,
                    }
                )
    return warnings


def _probability_threshold(
    value: object,
    name: str,
    *,
    lower_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number")
    normalized = float(value)
    lower_ok = normalized >= 0 if lower_inclusive else normalized > 0
    if not math.isfinite(normalized) or not lower_ok or normalized > 1:
        interval = "[0, 1]" if lower_inclusive else "(0, 1]"
        raise ValueError(f"{name} must be in {interval}")
    return normalized


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
