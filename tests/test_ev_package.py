import numpy as np
import pytest

import toto_ai.ev.package as package_module
from toto_ai.ev.models import EVConfig, EVSurface
from toto_ai.ev.package import derive_brief, rank_coupon_indices, select_ev_package
from toto_ai.ev.ternary import coupon_from_index


def surface(values, event_count=2):
    return EVSurface(
        gross_ev=np.array(values, dtype=np.float64),
        event_count=event_count,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def test_research_mode_fills_comparison_package_even_below_one():
    package = select_ev_package(
        surface([0.8, 0.9, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]),
        EVConfig(bank=60, stake=30, mode="research"),
    )

    assert package.decision == "RESEARCH ONLY"
    assert [row.coupon for row in package.coupons] == ["1X", "11"]
    assert package.cost == 60
    assert package.unused_bank == 0
    assert package.expected_payout == pytest.approx(51.0)
    assert package.modeled_roi == pytest.approx(-0.15)


def test_playable_mode_returns_no_bet_below_threshold():
    package = select_ev_package(
        surface([0.99] * 9),
        EVConfig(bank=60, stake=30, mode="playable", min_gross_ev=1.0),
    )

    assert package.decision == "NO BET"
    assert package.coupons == ()
    assert package.cost == 0
    assert package.unused_bank == 60
    assert package.expected_payout == 0.0
    assert package.modeled_roi is None
    assert package.derived_brief == ("", "")


def test_playable_mode_does_not_spend_bank_on_low_ev_coupons():
    package = select_ev_package(
        surface([1.2, 1.1, 0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.93]),
        EVConfig(bank=90, stake=30, mode="playable", min_gross_ev=1.0),
    )

    assert len(package.coupons) == 2
    assert package.cost == 60
    assert package.unused_bank == 30
    assert package.decision == "PLAY"


def test_equal_ev_uses_coupon_base_three_index_order():
    order = rank_coupon_indices(surface([1.0] * 9))

    assert [coupon_from_index(int(index), 2) for index in order[:3]] == [
        "11",
        "1X",
        "12",
    ]


def test_tolerance_ties_use_ascending_coupon_index():
    order = rank_coupon_indices(
        surface([1.0, 1.0 + 0.5e-12, 1.0 - 0.5e-12] + [0.5] * 6),
    )

    assert order[:3].tolist() == [0, 1, 2]


def test_unsigned_ev_ranking_does_not_wrap_zero_to_the_front():
    ev_surface = EVSurface(
        gross_ev=np.array([0, 8, 7, 6, 5, 4, 3, 2, 1], dtype=np.uint64),
        event_count=2,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )

    assert rank_coupon_indices(ev_surface).tolist() == [1, 2, 3, 4, 5, 6, 7, 8, 0]


def test_tolerance_tie_runs_use_first_value_instead_of_transitive_chaining():
    order = rank_coupon_indices(
        surface([1.0, 1.0 + 0.75e-12, 1.0 + 1.5e-12] + [0.5] * 6),
    )

    assert order[:3].tolist() == [1, 2, 0]


def test_rank_is_complete_order_position_after_threshold_filtering():
    package = select_ev_package(
        surface([1.0 - 0.5e-12, 1.0] + [0.5] * 7),
        EVConfig(bank=30, stake=30, mode="playable", min_gross_ev=1.0),
    )

    assert len(package.coupons) == 1
    assert package.coupons[0].coupon == "1X"
    assert package.coupons[0].rank == 2


def test_no_tie_surface_does_not_process_singleton_candidate_blocks(monkeypatch):
    def fail_on_candidate_block(*_args):
        pytest.fail("no-tie values must not enter candidate-block processing")

    monkeypatch.setattr(
        package_module,
        "_process_tie_candidate_block",
        fail_on_candidate_block,
    )

    order = rank_coupon_indices(surface([9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]))

    assert order.tolist() == list(range(9))


def test_tie_candidate_scan_preserves_blocks_across_chunk_boundaries(monkeypatch):
    monkeypatch.setattr(package_module, "_TIE_SCAN_CHUNK_SIZE", 1)

    order = rank_coupon_indices(
        surface([1.0, 1.0 + 0.5e-12, 1.0 + 1.0e-12] + [0.5] * 6),
    )

    assert order[:3].tolist() == [0, 1, 2]


def test_rank_scans_and_returns_every_coupon_index():
    order = rank_coupon_indices(surface([0.5] * 9))

    assert order.dtype == np.int64
    assert order.size == 9
    assert order.tolist() == list(range(9))


@pytest.mark.parametrize(
    "values",
    [
        [1.0] * 8,
        [1.0] * 10,
        [1.0, np.nan] + [1.0] * 7,
        [1.0, np.inf] + [1.0] * 7,
        [1.0, -0.01] + [1.0] * 7,
    ],
)
def test_rank_rejects_invalid_ev_surface_values(values):
    with pytest.raises(ValueError, match="gross_ev"):
        rank_coupon_indices(surface(values))


def test_rank_rejects_non_vector_ev_surface():
    invalid = EVSurface(
        gross_ev=np.ones((3, 3), dtype=np.float64),
        event_count=2,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )

    with pytest.raises(ValueError, match="one-dimensional"):
        rank_coupon_indices(invalid)


@pytest.mark.parametrize("threshold", [0.90, 0.95, 1.00, 1.05])
def test_playable_threshold_matrix_preserves_configured_threshold(threshold):
    config = EVConfig(bank=270, stake=30, mode="playable", min_gross_ev=threshold)

    select_ev_package(
        surface([1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70]),
        config,
    )

    assert config.min_gross_ev == threshold


def test_playable_threshold_counts_are_monotonic_non_increasing():
    ev_surface = surface([1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70])
    counts = [
        len(
            select_ev_package(
                ev_surface,
                EVConfig(bank=270, stake=30, mode="playable", min_gross_ev=threshold),
            ).coupons,
        )
        for threshold in (0.90, 0.95, 1.00, 1.05)
    ]

    assert counts == [5, 4, 3, 2]
    assert counts == sorted(counts, reverse=True)


def test_derive_brief_unions_outcomes_in_display_order():
    assert derive_brief(("21", "X2", "12"), event_count=2) == ("1X2", "12")


def test_derive_brief_empty_package_uses_the_supplied_event_count():
    assert derive_brief((), event_count=15) == ("",) * 15
