from __future__ import annotations

import csv
from functools import lru_cache
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
    return list(_expand_brief_cached(tuple(brief)))


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

    variants, cover_bits = _coverage_bits_for_brief(tuple(brief), category)
    variant_weights = tuple(_variant_weight(variant, weights) for variant in variants)
    unit_weights = weights is None
    selected = []
    selected_set = set()
    covered_bits = 0
    full_coverage_bits = (1 << len(variants)) - 1

    while len(selected) < max_coupons and covered_bits != full_coverage_bits:
        best_coupon = None
        best_new_coverage_bits = 0
        best_weighted_coverage = -1.0
        best_coupon_weight = -1.0

        for index, coupon in enumerate(variants):
            if coupon in selected_set:
                continue

            new_coverage_bits = cover_bits[index] & ~covered_bits
            weighted_coverage = _weighted_coverage(
                new_coverage_bits,
                variant_weights,
                unit_weights=unit_weights,
            )
            coupon_weight = variant_weights[index]
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
                best_new_coverage_bits = new_coverage_bits
                best_weighted_coverage = weighted_coverage
                best_coupon_weight = coupon_weight

        if best_coupon is None or not best_new_coverage_bits:
            break

        selected.append(best_coupon)
        selected_set.add(best_coupon)
        covered_bits |= best_new_coverage_bits

    full_count = len(variants)
    covered_count = covered_bits.bit_count()
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
    minimum_distances = _minimum_distances(variants, coupons)

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


@lru_cache(maxsize=2048)
def _expand_brief_cached(brief: tuple[str, ...]) -> tuple[str, ...]:
    positions = [_parse_position(position) for position in brief]
    return tuple("".join(variant) for variant in product(*positions))


@lru_cache(maxsize=1024)
def _coverage_bits_for_brief(
    brief: tuple[str, ...],
    category: int,
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    variants = _expand_brief_cached(brief)
    max_errors = category_max_errors(category)
    positions = tuple(_parse_position(position) for position in brief)
    variant_index = {variant: index for index, variant in enumerate(variants)}
    cover_bits = tuple(
        _coverage_bits_for_coupon(
            coupon=coupon,
            positions=positions,
            variant_index=variant_index,
            max_errors=max_errors,
        )
        for coupon in variants
    )
    return variants, cover_bits


def _coverage_bits_for_coupon(
    coupon: str,
    positions: tuple[tuple[str, ...], ...],
    variant_index: dict[str, int],
    max_errors: int,
) -> int:
    bits = 0
    coupon_chars = list(coupon)

    def visit(start: int, remaining_errors: int) -> None:
        nonlocal bits
        variant = "".join(coupon_chars)
        index = variant_index.get(variant)
        if index is not None:
            bits |= 1 << index
        if remaining_errors == 0:
            return

        for position in range(start, len(coupon_chars)):
            original = coupon_chars[position]
            for outcome in positions[position]:
                if outcome == original:
                    continue
                coupon_chars[position] = outcome
                visit(position + 1, remaining_errors - 1)
            coupon_chars[position] = original

    visit(0, max_errors)
    return bits


def _variant_weight(variant: str, weights: dict[str, float] | None) -> float:
    if weights is None:
        return 1.0
    return float(weights.get(variant, 1.0))


def _weighted_coverage(
    bits: int,
    weights: tuple[float, ...],
    unit_weights: bool,
) -> float:
    if not bits:
        return 0.0
    if unit_weights:
        return float(bits.bit_count())
    return sum(weights[index] for index in _bit_indices(bits))


def _bit_indices(bits: int):
    while bits:
        least_significant = bits & -bits
        yield least_significant.bit_length() - 1
        bits ^= least_significant


def _minimum_distance(variant: str, coupons: list[str]) -> int | None:
    if not coupons:
        return None
    return min(hamming(variant, coupon) for coupon in coupons)


def _minimum_distances(variants: list[str], coupons: list[str]) -> list[int | None]:
    if not coupons:
        return [None for _ in variants]
    encoded_coupons = [_encode_variant(coupon) for coupon in coupons]
    return [
        min(
            _encoded_hamming(encoded_variant, encoded_coupon)
            for encoded_coupon in encoded_coupons
        )
        for encoded_variant in (_encode_variant(variant) for variant in variants)
    ]


def _encode_variant(variant: str) -> tuple[int, ...]:
    return tuple(OUTCOMES.index(outcome) for outcome in variant)


def _encoded_hamming(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    if len(left) != len(right):
        raise ValueError("Values must have the same length.")
    return sum(
        left_item != right_item
        for left_item, right_item in zip(left, right, strict=True)
    )


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
