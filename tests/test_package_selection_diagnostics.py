from dataclasses import asdict

import pytest

from toto_ai.research.package_selection_diagnostics import evaluate_fixed_package


def args():
    return dict(
        coupons=("1" * 15, "2" * 15),
        probability_models={
            "bk": ((0.6, 0.2, 0.2),) * 15,
            "flat": ((0.5, 0.25, 0.25),) * 15,
        },
        category=13,
        selection_seed_material="frozen-selector",
        selection_sample_count=40,
        evaluation_sample_count=80,
    )


def test_fixed_package_evaluation_has_independent_streams_and_exact_reference(
    monkeypatch,
):
    from toto_ai.research import package_selection_diagnostics as m

    original = m.sample_scenarios
    calls = []

    def capture(probabilities, count, seed):
        calls.append((count, seed))
        return original(probabilities, count, seed)

    monkeypatch.setattr(m, "sample_scenarios", capture)
    first = evaluate_fixed_package(**args())
    assert first == evaluate_fixed_package(**args())
    assert all(a[1] != b[1] for a, b in zip(calls[:4:2], calls[1:4:2], strict=True))
    assert [x[0] for x in calls[:4]] == [40, 80, 40, 80]
    assert first.operator_compatible is False
    assert first.automatic_wagering is False
    assert first.calibrated_win_probability is None
    assert first.scope == "FIXED_PACKAGE_MODEL_DIAGNOSTIC_NOT_CALIBRATION"
    for row in first.models:
        assert row.training_seed != row.evaluation_seed
        assert row.exact_p13 >= row.exact_p14 >= row.exact_p15 > 0
        assert 0 <= row.training_sample_coverage <= 1
        assert 0 <= row.independent_sample_coverage <= 1
    assert asdict(first)["coupon_order_sha256"]


def test_hash_binds_probability_matrix_and_original_coupon_order():
    a = args()
    x = evaluate_fixed_package(**a)
    a["coupons"] = tuple(reversed(a["coupons"]))
    y = evaluate_fixed_package(**a)
    assert x.coupon_order_sha256 != y.coupon_order_sha256
    assert x.probability_models_sha256 == y.probability_models_sha256
    assert x.models == y.models
    a["probability_models"]["bk"] = ((0.5, 0.2, 0.3),) * 15
    assert (
        evaluate_fixed_package(**a).probability_models_sha256
        != x.probability_models_sha256
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("coupons", ("1" * 15,) * 2),
        ("selection_sample_count", 0),
        ("evaluation_sample_count", 0),
        ("evaluation_sample_count", 100001),
        ("selection_seed_material", ""),
        ("category", 12),
        ("coupons", ("1" * 14,)),
    ],
)
def test_invalid_diagnostic_inputs_rejected(field, value):
    a = args()
    a[field] = value
    with pytest.raises(ValueError):
        evaluate_fixed_package(**a)
