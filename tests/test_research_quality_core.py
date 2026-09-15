"""Numeric parity uses explicitly synthetic native test evidence, not history."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.ev.package import select_ev_package
from toto_ai.research.native_quality_core import select_numeric_candidate

spec = importlib.util.spec_from_file_location(
    "native_quality_test_support",
    Path(__file__).with_name("test_ev_package_quality.py"),
)
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
_provenance, _surface = support._provenance, support._surface


@pytest.mark.parametrize("events,count", [(3, 5), (4, 7), (5, 9)])
def test_ordered_numeric_parity_with_native_guarded_wrapper(tmp_path, events, count):
    probabilities = ((0.45, 0.30, 0.25),) * events
    config = EVConfig(
        bank=count * 30,
        mode="playable",
        package_safety_enabled=True,
        package_provenance_required=True,
    )
    surface = _surface(np.random.default_rng(47).uniform(1.1, 4, 3**events), events)
    provenance = _provenance(probabilities, tmp_path, config)
    native = select_ev_package(
        surface, config, probabilities=probabilities, provenance=provenance
    )
    candidate = select_numeric_candidate(
        surface,
        config=config,
        probabilities=probabilities,
        seed_material=provenance.seed_material_sha256,
    )
    assert candidate.coupons == tuple(c.coupon for c in native.paper_coupons)
    assert candidate.coupons
    assert candidate.operator_compatible is False
    assert candidate.equivalence_status == "NOT_NATIVE_EQUIVALENT"


def test_research_mode_is_rejected_not_silently_ev_topn():
    config = EVConfig(bank=90, mode="research", package_safety_enabled=True)
    with pytest.raises(ValueError, match="safety-aware"):
        select_numeric_candidate(
            _surface([2.0] * 27, 3),
            config=config,
            probabilities=((0.5, 0.3, 0.2),) * 3,
            seed_material="a" * 64,
        )


def test_insufficient_eligible_universe_is_not_filled_with_ineligible_ev():
    config = EVConfig(
        bank=150,
        mode="playable",
        package_safety_enabled=True,
        package_provenance_required=True,
    )
    result = select_numeric_candidate(
        _surface([0.0] * 27, 3),
        config=config,
        probabilities=((0.5, 0.3, 0.2),) * 3,
        seed_material="a" * 64,
    )
    assert result.coupons == ()
    assert result.reason
