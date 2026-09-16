from __future__ import annotations

import json

import pytest

from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.research.fixed_bank_coverage_comparison import (
    build_restricted_brief,
    select_fixed_bank_packages,
)


def _matrix():
    return (
        (0.34, 0.33, 0.33),
        (0.40, 0.30, 0.30),
        (0.50, 0.25, 0.25),
        (0.60, 0.20, 0.20),
        (0.34, 0.33, 0.33),
        (0.40, 0.30, 0.30),
        *((0.70, 0.20, 0.10),) * 9,
    )


def test_uniform_weights_match_unweighted_greedy_selection():
    matrix = ((1 / 3, 1 / 3, 1 / 3),) * 15
    brief = build_restricted_brief(matrix)

    result = select_fixed_bank_packages(brief, matrix)

    assert (
        result["weighted"]["greedy_coupons"] == result["unweighted"]["greedy_coupons"]
    )


def test_selection_is_deterministic_and_fills_exactly_166_unique_coupons():
    brief = build_restricted_brief(_matrix())

    first = select_fixed_bank_packages(brief, _matrix())
    second = select_fixed_bank_packages(brief, _matrix())

    for arm in ("weighted", "unweighted"):
        assert first[arm]["coupons"] == second[arm]["coupons"]
        assert len(first[arm]["coupons"]) == 166
        assert len(set(first[arm]["coupons"])) == 166
        assert first[arm]["greedy_count"] + first[arm]["fill_count"] == 166


def test_category_13_uses_two_errors_and_reports_coverage_not_naive_probability_sum():
    brief = ["1X2"] * 6 + ["1"] * 9
    matrix = ((0.5, 0.25, 0.25),) * 15

    result = select_fixed_bank_packages(brief, matrix)

    for arm in ("weighted", "unweighted"):
        assert result[arm]["category"] == 13
        assert result[arm]["max_errors"] == 2
        assert 0.0 <= result[arm]["conditional_brief_mass_coverage_fraction"] <= 1.0
        assert result[arm]["covered_variants_count"] <= result["variant_count"]


def test_overlapping_coupons_use_exact_union_not_naive_sum():
    matrix = ((0.5, 0.25, 0.25),) * 15
    coupons = ("1" * 15, "X" + "1" * 14)

    union_p13 = exact_category_probabilities(coupons, matrix)[0]
    naive_sum = sum(
        exact_category_probabilities((coupon,), matrix)[0] for coupon in coupons
    )

    assert union_p13 < naive_sum


def test_invalid_budget_or_duplicate_candidate_rejected():
    with pytest.raises(ValueError, match="166"):
        select_fixed_bank_packages(
            build_restricted_brief(_matrix()), _matrix(), coupon_count=165
        )

    with pytest.raises(ValueError, match="fifteen"):
        select_fixed_bank_packages(["1"] * 14, _matrix())


def test_target_label_mutation_is_not_an_input_to_selection(tmp_path):
    """The selection API accepts only sealed probability input, never labels."""
    brief = build_restricted_brief(_matrix())
    before = select_fixed_bank_packages(brief, _matrix())["weighted"]["coupons"]
    labels = tmp_path / "later-labels.json"
    labels.write_text(json.dumps({"actual": "2" * 15}), encoding="utf-8")

    after = select_fixed_bank_packages(brief, _matrix())["weighted"]["coupons"]

    assert before == after


def test_reporting_separates_conditional_coverage_and_probability_mass(tmp_path):
    from toto_ai.research.fixed_bank_coverage_comparison import (
        DIAGNOSTIC_SEMANTICS,
        _coverage_metrics,
        _write_reports,
    )

    variants = ("1" * 15, "XXX" + "1" * 12)
    metrics = _coverage_metrics(
        (variants[0],), variants, dict(zip(variants, (0.1, 0.2), strict=True))
    )
    assert metrics["brief_mass_total"] == pytest.approx(0.3)
    assert metrics["conditional_brief_mass_coverage_fraction"] == pytest.approx(1 / 3)
    assert "brief_mass_covered" not in metrics
    metrics.pop("constraint_diagnostics")
    report = {
        "timing": {"wall_seconds": 1.0},
        "diagnostic_semantics": DIAGNOSTIC_SEMANTICS,
        "arms": [
            {
                "name": "fixture",
                "selection": dict(metrics, greedy_count=1, fill_count=0),
                "exact_union": dict(
                    exact_union_p13=0.4, exact_union_p14=0.2, exact_union_p15=0.1
                ),
            }
        ],
    }
    _write_reports(tmp_path, report)
    saved = json.loads((tmp_path / "result.json").read_text())
    semantics = saved["diagnostic_semantics"]
    assert semantics["distinct_forecast_count"] == 1
    assert semantics["api_aliases"] == {"common_bk_duplicate": "common_bk"}
    assert semantics["training_stream_used_by_greedy"] is False
    assert semantics["alias_results_combined"] is False
    csv = (tmp_path / "summary.csv").read_text()
    assert "conditional_brief_mass_coverage_fraction,brief_mass_total" in csv
    markdown = (tmp_path / "summary.md").read_text()
    assert "unconditional brief probability" in markdown
    assert "one distinct BK forecast" in markdown
    assert "training_* fields are diagnostic-only" in markdown
    assert "outcomes outside the brief" in markdown
