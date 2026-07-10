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

            new_coverage = coverage_set(coupon, variants, max_errors) - covered
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
