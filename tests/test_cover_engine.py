import pytest

from toto_ai.optimizer.cover import (
    category_max_errors,
    coverage_set,
    expand_brief,
    greedy_cover,
    hamming,
)


def test_expand_brief_uses_cartesian_product():
    assert expand_brief(["1", "1X", "X2"]) == ["11X", "112", "1XX", "1X2"]


@pytest.mark.parametrize(
    ("category", "max_errors"),
    [(13, 2), (14, 1), (15, 0)],
)
def test_category_maps_to_max_errors(category, max_errors):
    assert category_max_errors(category) == max_errors


def test_hamming_counts_different_positions():
    assert hamming("111X2", "12112") == 2


def test_coverage_set_returns_variant_indexes_within_distance():
    variants = ["111", "11X", "1XX", "222"]

    assert coverage_set("111", variants, max_errors=1) == {0, 1}


def test_category_15_requires_exact_coverage():
    result = greedy_cover(
        brief=["1X", "12"],
        category=15,
        max_coupons=1,
    )

    assert result["selected_coupons"] == ["11"]
    assert result["full_variants_count"] == 4
    assert result["covered_variants_count"] == 1
    assert result["coverage_rate"] == 0.25


def test_category_13_covers_more_variants_than_category_14_with_same_coupons():
    brief = ["1X", "12", "X2", "1X"]

    category_13 = greedy_cover(brief=brief, category=13, max_coupons=1)
    category_14 = greedy_cover(brief=brief, category=14, max_coupons=1)

    assert category_13["covered_variants_count"] > category_14[
        "covered_variants_count"
    ]


def test_greedy_cover_uses_weights_for_tie_breaking():
    result = greedy_cover(
        brief=["1X", "12"],
        category=15,
        max_coupons=1,
        weights={"X2": 10, "11": 1, "12": 1, "X1": 1},
    )

    assert result["selected_coupons"] == ["X2"]


def test_arbitrary_bank_and_stake_translate_to_max_coupons():
    bank = 95
    stake = 30
    result = greedy_cover(
        brief=["1X", "12", "1", "1", "1"],
        category=15,
        max_coupons=bank // stake,
    )

    assert len(result["selected_coupons"]) == 3
    assert len(result["selected_coupons"]) * stake == 90
