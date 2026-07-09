from dataclasses import dataclass
from itertools import product

OUTCOMES = ("1", "X", "2")
ALLOWED_CATEGORIES = (13, 14, 15)


@dataclass(frozen=True)
class MvpPackageResult:
    label: str
    bank: int
    stake: int
    category: int
    max_errors: int
    full_brief_size: int
    selected_coupons: list[str]
    cost: int
    covered_variants: int
    full_brief_variants: int

    @property
    def estimated_coverage(self) -> float:
        if self.full_brief_variants == 0:
            return 0.0
        return self.covered_variants / self.full_brief_variants


def generate_mvp_package(
    brief: str,
    bank: int,
    stake: int = 30,
    category: int = 13,
) -> MvpPackageResult:
    if bank <= 0:
        raise ValueError("Bank must be any positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("Category must be one of 13, 14, or 15.")

    max_errors = 15 - category
    full_variants = expand_full_brief(brief)
    max_coupons = bank // stake
    selected = _select_covering_coupons(full_variants, max_errors, max_coupons)
    covered = _covered_variants(full_variants, selected, max_errors)

    return MvpPackageResult(
        label="MVP covering approximation",
        bank=bank,
        stake=stake,
        category=category,
        max_errors=max_errors,
        full_brief_size=len(full_variants),
        selected_coupons=selected,
        cost=len(selected) * stake,
        covered_variants=len(covered),
        full_brief_variants=len(full_variants),
    )


def expand_full_brief(brief: str) -> list[str]:
    positions = _parse_brief_positions(brief)
    return ["".join(variant) for variant in product(*positions)]


def _parse_brief_positions(brief: str) -> list[tuple[str, ...]]:
    raw_positions = (
        [part.strip().upper() for part in brief.split(",")]
        if "," in brief
        else list(brief.strip().upper())
    )
    positions = []
    for position in raw_positions:
        if not position:
            raise ValueError("Brief positions cannot be empty.")
        unique_outcomes = tuple(outcome for outcome in OUTCOMES if outcome in position)
        if not unique_outcomes or set(position) - set(OUTCOMES):
            raise ValueError("Brief positions may contain only 1, X, and 2.")
        positions.append(unique_outcomes)
    if len(positions) != 15:
        raise ValueError("Brief must contain exactly 15 positions.")
    return positions


def _select_covering_coupons(
    full_variants: list[str],
    max_errors: int,
    max_coupons: int,
) -> list[str]:
    if max_coupons <= 0:
        return []

    uncovered = set(full_variants)
    selected = []
    value_scores = {
        coupon: len(_covered_variants(full_variants, [coupon], max_errors))
        for coupon in full_variants
    }
    ranked_coupons = sorted(
        full_variants,
        key=lambda coupon: (-value_scores[coupon], coupon),
    )

    while uncovered and len(selected) < max_coupons:
        best_coupon = max(
            ranked_coupons,
            key=lambda coupon: (
                len(_covered_variants(list(uncovered), [coupon], max_errors)),
                value_scores[coupon],
                _reverse_lex_key(coupon),
            ),
        )
        newly_covered = _covered_variants(list(uncovered), [best_coupon], max_errors)
        if not newly_covered:
            break
        selected.append(best_coupon)
        uncovered -= newly_covered
        ranked_coupons = [
            coupon for coupon in ranked_coupons if coupon not in selected
        ]
    return selected


def _covered_variants(
    variants: list[str],
    coupons: list[str],
    max_errors: int,
) -> set[str]:
    return {
        variant
        for variant in variants
        if any(_hamming_distance(variant, coupon) <= max_errors for coupon in coupons)
    }


def _hamming_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("Coupons must have the same length.")
    return sum(
        left_item != right_item
        for left_item, right_item in zip(left, right, strict=True)
    )


def _reverse_lex_key(value: str) -> tuple[int, ...]:
    return tuple(-ord(character) for character in value)
