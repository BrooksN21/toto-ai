"""Core computability and optional missingness cannot manufacture authority."""

import pytest

from toto_ai.sports_stats.v3_feature_disposition import feature_disposition
from toto_ai.sports_stats.v3_probability import CORE_NAMES, FEATURE_NAMES


def row():
    return {
        "features": dict.fromkeys(FEATURE_NAMES, 1.0),
        "source_rejected": False,
        "exact_target": True,
        "scope_verified": True,
        "prior_counts": [10, 10],
    }


def test_optional_absence_changes_missingness_not_core_contract():
    value = row()
    for name in set(FEATURE_NAMES) - set(CORE_NAMES):
        value["features"][name] = None
    result = feature_disposition(value)
    assert result["core_source_computable"]
    assert result["A2_A3"]["input_contract_satisfied"]
    assert result["A4_A5"]["input_contract_satisfied"]
    assert result["optional_missing"]
    value["features"][CORE_NAMES[0]] = None
    result = feature_disposition(value)
    assert not result["A2_A3"]["input_contract_satisfied"]
    assert result["A4_A5"]["input_contract_satisfied"]


@pytest.mark.parametrize(
    "changes",
    [
        {"source_rejected": True},
        {"exact_target": False},
        {"prior_counts": [10, 0]},
        {"scope_verified": False},
    ],
)
def test_computable_features_never_override_common_proof(changes):
    result = feature_disposition(row() | changes)
    assert result["core_numeric_complete"]
    assert not result["A2_A3"]["input_contract_satisfied"]
    assert not result["A4_A5"]["input_contract_satisfied"]
    assert not result["training_authorized"]
