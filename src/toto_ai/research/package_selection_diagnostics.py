"""Opt-in fixed-package diagnostics; never imported by an operational selector.

Training-sample coverage is resubstitution, NOT a calibrated win chance.
Independent streams can contain coincident outcomes; independence does not mean
removing shared outcomes (that would bias the evaluation distribution).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.optimizer.coupon_candidates import sample_scenarios
from toto_ai.optimizer.cover import category_max_errors
from toto_ai.optimizer.robust_package import _model_seed, _normalize_models


@dataclass(frozen=True)
class FixedModelEvaluation:
    model: str
    training_seed: int
    evaluation_seed: int
    training_sample_count: int
    evaluation_sample_count: int
    training_sample_coverage: float
    independent_sample_coverage: float
    exact_p13: float
    exact_p14: float
    exact_p15: float


@dataclass(frozen=True)
class FixedPackageEvaluation:
    coupon_order_sha256: str
    probability_models_sha256: str
    category: int
    models: tuple[FixedModelEvaluation, ...]
    scope: str = "FIXED_PACKAGE_MODEL_DIAGNOSTIC_NOT_CALIBRATION"
    operator_compatible: bool = False
    automatic_wagering: bool = False
    calibrated_win_probability: None = None
    sampling_protocol: str = "independent-rng-streams-v1"
    coupon_hash_protocol: str = "UTF8_COUPONS_LF_JOIN_NO_TRAILING_LF"


def _coverage(coupons, scenarios, max_errors):
    encoded = np.array([list(s.encode("ascii")) for s in scenarios], dtype=np.uint8)
    digits = np.array([list(s.encode("ascii")) for s in coupons], dtype=np.uint8)
    covered = np.zeros(len(encoded), dtype=bool)
    for start in range(0, len(digits), 16):
        covered |= (
            (digits[start : start + 16, None, :] != encoded[None, :, :]).sum(axis=2)
            <= max_errors
        ).any(axis=0)
    weights = np.fromiter(scenarios.values(), dtype=np.int64)
    return float(weights[covered].sum() / weights.sum())


def evaluate_fixed_package(
    *,
    coupons: Sequence[str],
    probability_models: Mapping[str, Sequence[Sequence[float]]],
    category: int,
    selection_seed_material: str,
    selection_sample_count: int,
    evaluation_sample_count: int = 10_000,
) -> FixedPackageEvaluation:
    """Score immutable coupons, never optimize them or access actual outcomes.

    Caller supplies the EXACT native selector seed, including qv3's '-selector'
    suffix, not its candidate-generation seed. No historical-asof, archive,
    prospective or release authority is created by this numerical function.
    """
    cs = tuple(coupons)
    if (
        not cs
        or len(cs) > 1000
        or len(set(cs)) != len(cs)
        or any(
            not isinstance(c, str) or len(c) != 15 or set(c) - set("1X2") for c in cs
        )
    ):
        raise ValueError("need 1..1000 unique fifteen-event coupons")
    if type(category) is not int or category not in (13, 14, 15):
        raise ValueError("category must be13/14/15")
    for count in (selection_sample_count, evaluation_sample_count):
        if type(count) is not int or not 1 <= count <= 100_000:
            raise ValueError("sample counts must be1..100000")
    if not isinstance(selection_seed_material, str) or not selection_seed_material:
        raise ValueError("exact nonempty selection seed required")
    models = _normalize_models(probability_models)
    if any(len(matrix) != 15 for _, matrix in models):
        raise ValueError("fifteen-event probability matrices required")
    coupon_hash = hashlib.sha256("\n".join(cs).encode()).hexdigest()
    probability_hash = hashlib.sha256(
        json.dumps(models, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    results = []
    for name, matrix in models:
        train_seed = _model_seed(selection_seed_material, name)
        eval_seed = _model_seed(
            selection_seed_material + "\0heldout-evaluation-v1", name
        )
        if train_seed == eval_seed:
            raise ValueError("evaluation seed collision")
        train = sample_scenarios(matrix, selection_sample_count, train_seed)
        validation = sample_scenarios(matrix, evaluation_sample_count, eval_seed)
        exact = exact_category_probabilities(cs, matrix)
        results.append(
            FixedModelEvaluation(
                name,
                train_seed,
                eval_seed,
                selection_sample_count,
                evaluation_sample_count,
                _coverage(cs, train, category_max_errors(category)),
                _coverage(cs, validation, category_max_errors(category)),
                *exact,
            )
        )
    return FixedPackageEvaluation(
        coupon_hash, probability_hash, category, tuple(results)
    )
