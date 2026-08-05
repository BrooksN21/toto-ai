import pytest

from toto_ai.package.mvp import expand_full_brief, generate_mvp_package


def test_bank_can_be_any_positive_integer_and_cost_uses_full_coupon_count():
    result = generate_mvp_package(
        brief="1X,12,1,1,1,1,1,1,1,1,1,1,1,1,1",
        bank=95,
        stake=30,
        category=15,
    )

    assert result.bank == 95
    assert result.stake == 30
    assert len(result.selected_coupons) == 3
    assert result.cost == 90


@pytest.mark.parametrize(
    ("category", "max_errors"),
    [(13, 2), (14, 1), (15, 0)],
)
def test_category_sets_max_errors(category, max_errors):
    result = generate_mvp_package(
        brief="1,1,1,1,1,1,1,1,1,1,1,1,1,1,1",
        bank=30,
        category=category,
    )

    assert result.max_errors == max_errors


def test_coverage_selection_uses_hamming_distance_for_uncovered_variants():
    result = generate_mvp_package(
        brief="1X,12,1,1,1,1,1,1,1,1,1,1,1,1,1",
        bank=30,
        stake=30,
        category=14,
    )

    assert result.full_brief_size == 4
    assert result.selected_coupons == ["111111111111111"]
    assert result.covered_variants == 3
    assert result.estimated_coverage == 0.75


def test_category_15_requires_exact_coupon_coverage():
    result = generate_mvp_package(
        brief="1X,12,1,1,1,1,1,1,1,1,1,1,1,1,1",
        bank=30,
        stake=30,
        category=15,
    )

    assert result.max_errors == 0
    assert result.covered_variants == 1
    assert result.estimated_coverage == 0.25


def test_expand_full_brief_accepts_single_pick_string():
    assert expand_full_brief("111111111111111") == ["111111111111111"]


def test_bank_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        generate_mvp_package(
            brief="111111111111111",
            bank=0,
        )
