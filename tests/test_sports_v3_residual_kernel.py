"""Pre-refactor native byte-parity fixtures frozen before numerical extraction."""

import runpy
from pathlib import Path

import pytest

from toto_ai.sports_stats import v3_probability as v3

fixture = runpy.run_path(str(Path(__file__).with_name("test_sports_v3_probability.py")))
EXPECTED = {
    "A2": (
        "3ba3f975dcee9b2b8add4461ae23e028feb24e28c0a6c6fbd413296f549dd597",
        "99b754c66ce441aa7833668c5dba7a2d7031101ce54fcb84b8b664f8f4258698",
    ),
    "A3": (
        "01bba96f0464f6c178205f8c283ab3cc0ca3f3230f9e5791a0916b5fd831dd44",
        "c71e41a32314522bc5969f217e8fee1c2a905ef1976eed24777858d51f0117e3",
    ),
    "A4": (
        "c00d876deec565ed378ac0c7ddaa689bd909dc46b7cf992442a506d2f68d3a14",
        "ebf43ce8a5eb4f52e4caa9758684a35ee7b82b36bd3b6a76d0ed16b8f6d356e2",
    ),
    "A5": (
        "39273256517322a1586478bc5565a1dcd3aadd6d3e8cdba121f8842785876d10",
        "fedd612697dd1e2e3cbbb0eb8b1b1b2f48b63a1292dec17a3067436e2f432582",
    ),
    "missing": (
        "a4576f5cf8a6124300530e1810d2a2c19509c163da5c94345fe4bd4ddbfdeced",
        "fd13a476d72c979c8d135d2940eef512f4e323abebad17427436e6c2ea1c8a83",
    ),
    "cold": (
        "a11d57e131501a7bf00462c10ff6bd501137757437bf527327176a81d8baff9d",
        "ec37b484480617401c84aeef7ac74df3ca5ab16d74bd3c8e86ea5a55764aae9c",
    ),
    "no_scope": (
        "95b750fc8e35e395dc5e57527f89a4cd468ee6a26130f43017a49559a2deed0b",
        "57daec69d8226c556b3ab76ecb79158c84469b02030b546a42883f93c8b9e590",
    ),
    "alternate": (
        "501994f7b59d2cf2b8167ea7061314f00fa6468c34c3768b691a4123d91d4d6b",
        "fec39ec037edc3241480120ae1bbe418fdf13e89faa6b55bd660c9baf65245ab",
    ),
}


@pytest.mark.parametrize("case", EXPECTED)
def test_pre_extraction_native_model_and_prediction_exact_hashes(case):
    rows = fixture["training"](2 if case == "cold" else 3)
    if case in ("missing", "no_scope"):
        for row in rows:
            if case == "missing":
                row["features"]["features"]["home_rest_days"] = None
            else:
                row["features"]["scope_verified"] = False
            row["features"] = v3.seal(row["features"])
    config = {"variant": case if case in v3.VARIANTS else "A5"}
    if case == "alternate":
        config.update(l2=0.3, steps=7)
    model = v3.train_v3(
        rows,
        target_drawing=10,
        prediction_as_of=fixture["feature"](10)["as_of"],
        training_domain="SYNTHETIC_TEST_ONLY",
        **config,
    )
    prediction = v3.infer_v3(model, fixture["feature"](10))
    assert (model["sha256"], prediction["sha256"]) == EXPECTED[case]


def test_research_domain_is_still_rejected_by_production():
    with pytest.raises(ValueError, match="training domain"):
        v3.train_v3(
            fixture["training"](),
            target_drawing=10,
            prediction_as_of=fixture["feature"](10)["as_of"],
            training_domain="RETROSPECTIVE_SPORTS_V3_RESEARCH_V1",
        )


def test_shared_kernel_timeout_is_not_a_fitted_model():
    import numpy as np

    from toto_ai.sports_stats.v3_residual_kernel import fit_residual

    with pytest.raises(TimeoutError, match="FIT_TIME_BUDGET"):
        fit_residual(
            np.ones((3, 2)),
            np.eye(3),
            np.zeros((3, 3)),
            np.ones((3, 1)) * 0.2,
            l2=0.1,
            steps=240,
            started=0,
            time_budget_seconds=1e-12,
        )
