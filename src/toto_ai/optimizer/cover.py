from __future__ import annotations

import csv
from itertools import product
from pathlib import Path
from typing import Any

OUTCOMES = ("1", "X", "2")
CATEGORY_MAX_ERRORS = {
    13: 2,
    14: 1,
    15: 0,
}


def expand_brief(brief: list[str]) -> list[str]:
    positions = [_parse_position(position) for position in brief]
    return ["".join(variant) for variant in product(*positions)]


def hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        raise ValueError("Values must have the same length.")
    return sum(left != right for left, right in zip(a, b, strict=True))


def coverage_set(coupon: str, variants: list[str], max_errors: int) -> set[int]:
    return {
        index
        for index, variant in enumerate(variants)
        if hamming(coupon, variant) <= max_errors
    }


def greedy_cover(
    brief: list[str],
    category: int,
    max_coupons: int,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    if max_coupons < 0:
        raise ValueError("max_coupons must be non-negative.")

    variants = expand_brief(brief)
    max_errors = category_max_errors(category)
    variant_weights = {
        variant: _variant_weight(variant, weights)
        for variant in variants
    }
    cover_sets = {
        coupon: coverage_set(coupon, variants, max_errors)
        for coupon in variants
    }
    selected = []
    covered: set[int] = set()

    while len(selected) < max_coupons and len(covered) < len(variants):
        best_coupon = None
        best_new_coverage: set[int] = set()
        best_weighted_coverage = -1.0
        best_coupon_weight = -1.0

        for coupon in variants:
            if coupon in selected:
                continue

            new_coverage = cover_sets[coupon] - covered
            weighted_coverage = sum(
                variant_weights[variants[index]]
                for index in new_coverage
            )
            coupon_weight = variant_weights[coupon]
            if (
                weighted_coverage > best_weighted_coverage
                or (
                    weighted_coverage == best_weighted_coverage
                    and coupon_weight > best_coupon_weight
                )
                or (
                    weighted_coverage == best_weighted_coverage
                    and coupon_weight == best_coupon_weight
                    and (best_coupon is None or coupon < best_coupon)
                )
            ):
                best_coupon = coupon
                best_new_coverage = new_coverage
                best_weighted_coverage = weighted_coverage
                best_coupon_weight = coupon_weight

        if best_coupon is None or not best_new_coverage:
            break

        selected.append(best_coupon)
        covered |= best_new_coverage

    full_count = len(variants)
    covered_count = len(covered)
    return {
        "selected_coupons": selected,
        "full_variants_count": full_count,
        "covered_variants_count": covered_count,
        "coverage_rate": covered_count / full_count if full_count else 0.0,
    }


def category_max_errors(category: int) -> int:
    try:
        return CATEGORY_MAX_ERRORS[category]
    except KeyError as error:
        raise ValueError("Category must be one of 13, 14, or 15.") from error


def parse_brief(brief: str) -> list[str]:
    return [position.strip().upper() for position in brief.split(",")]


def write_cover_package_csv(
    selected_coupons: list[str],
    output_path: str | Path = "reports/cover_package.csv",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["index", "coupon"])
        for index, coupon in enumerate(selected_coupons, start=1):
            writer.writerow([index, coupon])
    return path


def load_cover_package_csv(package_path: str | Path) -> list[str]:
    path = Path(package_path)
    with path.open(newline="", encoding="utf-8") as package_file:
        reader = csv.DictReader(package_file)
        if reader.fieldnames and "coupon" in reader.fieldnames:
            return [
                row["coupon"].strip().upper()
                for row in reader
                if row.get("coupon", "").strip()
            ]

    with path.open(newline="", encoding="utf-8") as package_file:
        return [
            row[0].strip().upper()
            for row in csv.reader(package_file)
            if row and row[0].strip()
        ]


def verify_cover_package(
    brief: list[str],
    category: int,
    coupons: list[str],
) -> dict[str, Any]:
    variants = expand_brief(brief)
    max_errors = category_max_errors(category)
    minimum_distances = [
        _minimum_distance(variant, coupons)
        for variant in variants
    ]

    fully_covered = [
        variant
        for variant, distance in zip(variants, minimum_distances, strict=True)
        if distance is not None and distance <= max_errors
    ]
    uncovered = [
        variant
        for variant, distance in zip(variants, minimum_distances, strict=True)
        if distance is None or distance > max_errors
    ]
    finite_distances = [
        distance
        for distance in minimum_distances
        if distance is not None
    ]

    return {
        "total_variants": len(variants),
        "fully_covered_variants": len(fully_covered),
        "uncovered_variants": len(uncovered),
        "worst_minimum_distance": max(finite_distances)
        if finite_distances
        else None,
        "distance_distribution": _minimum_distance_distribution(minimum_distances),
        "guarantee_pass": len(uncovered) == 0,
        "first_uncovered_variants": uncovered[:20],
    }


def _parse_position(position: str) -> tuple[str, ...]:
    normalized = position.strip().upper()
    if not normalized:
        raise ValueError("Brief positions cannot be empty.")
    if set(normalized) - set(OUTCOMES):
        raise ValueError("Brief positions may contain only 1, X, and 2.")
    return tuple(outcome for outcome in OUTCOMES if outcome in normalized)


def _variant_weight(variant: str, weights: dict[str, float] | None) -> float:
    if weights is None:
        return 1.0
    return float(weights.get(variant, 1.0))


def _minimum_distance(variant: str, coupons: list[str]) -> int | None:
    if not coupons:
        return None
    return min(hamming(variant, coupon) for coupon in coupons)


def _minimum_distance_distribution(
    minimum_distances: list[int | None],
) -> dict[int | str, int]:
    distribution: dict[int | str, int] = {0: 0, 1: 0, 2: 0, "3+": 0}
    for distance in minimum_distances:
        if distance is None or distance >= 3:
            distribution["3+"] += 1
        else:
            distribution[distance] += 1
    return distribution
