import csv

from toto_ai.optimizer.cover import (
    load_cover_package_csv,
    verify_cover_package,
)


def test_verify_cover_package_passes_when_all_variants_are_within_category():
    result = verify_cover_package(
        brief=["1X", "12"],
        category=13,
        coupons=["11"],
    )

    assert result["total_variants"] == 4
    assert result["fully_covered_variants"] == 4
    assert result["uncovered_variants"] == 0
    assert result["worst_minimum_distance"] == 2
    assert result["distance_distribution"] == {0: 1, 1: 2, 2: 1, "3+": 0}
    assert result["guarantee_pass"] is True
    assert result["first_uncovered_variants"] == []


def test_verify_cover_package_fails_when_any_variant_exceeds_category_distance():
    result = verify_cover_package(
        brief=["1X", "12", "X2"],
        category=14,
        coupons=["11X"],
    )

    assert result["total_variants"] == 8
    assert result["fully_covered_variants"] == 4
    assert result["uncovered_variants"] == 4
    assert result["worst_minimum_distance"] == 3
    assert result["distance_distribution"] == {0: 1, 1: 3, 2: 3, "3+": 1}
    assert result["guarantee_pass"] is False
    assert result["first_uncovered_variants"] == ["122", "X12", "X2X", "X22"]


def test_category_15_verifier_requires_exact_coupon_match_for_each_variant():
    result = verify_cover_package(
        brief=["1X", "12"],
        category=15,
        coupons=["11", "X2"],
    )

    assert result["fully_covered_variants"] == 2
    assert result["uncovered_variants"] == 2
    assert result["guarantee_pass"] is False
    assert result["first_uncovered_variants"] == ["12", "X1"]


def test_verify_cover_package_handles_empty_package():
    result = verify_cover_package(
        brief=["1X"],
        category=13,
        coupons=[],
    )

    assert result["fully_covered_variants"] == 0
    assert result["uncovered_variants"] == 2
    assert result["worst_minimum_distance"] is None
    assert result["distance_distribution"] == {0: 0, 1: 0, 2: 0, "3+": 2}
    assert result["guarantee_pass"] is False
    assert result["first_uncovered_variants"] == ["1", "X"]


def test_load_cover_package_csv_reads_coupon_column(tmp_path):
    package_path = tmp_path / "cover_package.csv"
    with package_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["index", "coupon"])
        writer.writerow([1, "111"])
        writer.writerow([2, "1X2"])

    assert load_cover_package_csv(package_path) == ["111", "1X2"]
