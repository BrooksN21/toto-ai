"""Independent synthetic acceptance oracles; no repository/model imports.

These validate review fixtures and a future adapter's observed journal/ranking.
They are NOT an integration test or an ACCEPT verdict for an implementation.
Only four uncertain events are enumerated (81 states), never real drawing data.
"""

import json
import math
from fractions import Fraction
from itertools import product

OUTCOMES = "1X2"
PREFIX = "1" * 11
COUPONS = (PREFIX + "1111", PREFIX + "2222")
ROWS = ((Fraction(1, 10), Fraction(1, 10), Fraction(8, 10)),) * 4


def exact_fixture_categories(coupons):
    assert coupons and all(len(c) == 15 and c.startswith(PREFIX) for c in coupons)
    assert all(set(c) <= set(OUTCOMES) for c in coupons)
    totals = [Fraction(0)] * 3
    for tail in product(range(3), repeat=4):
        outcome = PREFIX + "".join(OUTCOMES[d] for d in tail)
        weight = math.prod(ROWS[i][d] for i, d in enumerate(tail))
        hits = max(
            sum(a == b for a, b in zip(c, outcome, strict=True)) for c in coupons
        )
        for index, threshold in enumerate((13, 14, 15)):
            if hits >= threshold:
                totals[index] += weight
    return tuple(totals)


def assert_primary_first(journal):
    """Adapter supplies ordered phase names from actual publication/call spies."""
    required = ("PRIMARY_PACKAGE_VERIFIED", "PRIMARY_DELIVERY_READY")
    assert all(name in journal for name in required)
    barrier = max(journal.index(name) for name in required)
    for phase in ("PRIMARY_RANK_START", "O1_START", "G1_START"):
        if phase in journal:
            assert barrier < journal.index(phase), "optional work preceded primary"


def assert_primary_rank_not_waiting_for_g1(journal):
    """Use with an intentionally blocked G1 stub, after primary was delivered."""
    assert_primary_first(journal)
    assert "G1_BLOCKED" in journal and "G1_DONE" not in journal
    assert "PRIMARY_RANK_AVAILABLE" in journal


def assert_primary_unchanged(before_bytes, after_bytes):
    assert isinstance(before_bytes, bytes) and isinstance(after_bytes, bytes)
    assert before_bytes == after_bytes, "optional path changed exact primary bytes"


def assert_fixture_ranking(payload, coupons=COUPONS):
    """Validate public ranking fields without assuming the first row wins."""
    values = [exact_fixture_categories((coupon,)) for coupon in coupons]
    best = max(range(len(coupons)), key=lambda i: values[i][0])
    assert payload["criterion"] == "maximum_probability_at_least_13"
    assert payload["reference_model"] == "bk"
    assert payload["package_position"] == best + 1
    assert payload["coupon"] == coupons[best]
    assert (
        payload["package_order_semantics"]
        == "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK"
    )
    for key, expected in zip(
        (
            "probability_at_least_13",
            "probability_at_least_14",
            "probability_at_least_15",
        ),
        values[best],
        strict=True,
    ):
        actual = payload[key]
        assert type(actual) in (int, float) and math.isfinite(actual)
        assert abs(actual - float(expected)) <= 1e-12


def self_check():
    singles = [exact_fixture_categories((c,)) for c in COUPONS]
    assert singles == [
        (Fraction(523, 10000), Fraction(37, 10000), Fraction(1, 10000)),
        (Fraction(9728, 10000), Fraction(8192, 10000), Fraction(4096, 10000)),
    ]
    union = exact_fixture_categories(COUPONS)
    assert union == (
        Fraction(9867, 10000),
        Fraction(8229, 10000),
        Fraction(4097, 10000),
    )
    assert union[0] != sum(value[0] for value in singles)
    assert_primary_first(
        [
            "PRIMARY_PACKAGE_VERIFIED",
            "PRIMARY_DELIVERY_READY",
            "PRIMARY_RANK_START",
            "O1_START",
            "G1_START",
        ]
    )
    assert_primary_rank_not_waiting_for_g1(
        [
            "PRIMARY_PACKAGE_VERIFIED",
            "PRIMARY_DELIVERY_READY",
            "G1_START",
            "G1_BLOCKED",
            "PRIMARY_RANK_AVAILABLE",
        ]
    )
    try:
        assert_primary_first(
            ["PRIMARY_PACKAGE_VERIFIED", "G1_START", "PRIMARY_DELIVERY_READY"]
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("primary-first negative witness was not rejected")
    return {
        "scope": "oracle self-check only; integration tests not run",
        "uncertain_events": 4,
        "enumerated_states_per_call": 81,
        "coupons": list(COUPONS),
        "full_probability_rows": [[1.0, 0.0, 0.0]] * 11 + [[0.1, 0.1, 0.8]] * 4,
        "single_coupon_categories": [[float(x) for x in values] for values in singles],
        "package_union_categories": [float(x) for x in union],
        "unique_highest_p13_package_position": 2,
        "primary_first_positive_and_negative_witnesses": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(self_check(), sort_keys=True))
