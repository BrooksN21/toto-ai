import pytest

from toto_ai.operations.retrospective_payouts import cumulative_payout_comparison

COEFFICIENTS = {
    9: "5.99407",
    10: "9.07765",
    11: "17.95485",
    12: "43.75455",
    13: "322.36119",
    14: "10982.73283",
    15: "0.00000",
}
# Exact hits, not cumulative category counts; actual 4996 receipt contains no
# private receipt identifier in this regression fixture.
HISTOGRAM = {2: 3, 3: 11, 4: 12, 5: 25, 6: 34, 7: 47, 8: 22, 9: 7, 10: 4, 11: 1}


def test_4996_receipt_reconciles_after_aggregate_rounding():
    result = cumulative_payout_comparison(
        HISTOGRAM, COEFFICIENTS, stake=30, actual_return="4058.16"
    )
    assert result["unrounded_estimated_return_rub"] == "4058.15820"
    assert result["estimated_return_rub"] == result["actual_return_rub"] == "4058.16"
    assert result["actual_net_rub"] == "-921.84"
    assert result["per_coupon_rounding_scenario_rub"] == "4058.14"


def test_actual_receipt_is_not_overwritten_by_displayed_precision_estimate():
    result = cumulative_payout_comparison(
        HISTOGRAM, COEFFICIENTS, stake=30, actual_return="4000.00"
    )
    assert result["estimated_return_rub"] == "4058.16"
    assert result["actual_return_rub"] == "4000.00"


def test_replay_estimate_does_not_invent_actual_wager():
    result = cumulative_payout_comparison(HISTOGRAM, COEFFICIENTS, stake=30)
    assert result["actual_return_rub"] is None
    assert result["actual_net_rub"] is None


def test_incomplete_coefficient_table_fails_closed():
    with pytest.raises(ValueError, match="complete category"):
        cumulative_payout_comparison(HISTOGRAM, {9: "5.99407"}, stake=30)
