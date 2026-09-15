"""Predeclared bounded draw-vs-nondraw residual; earlier training labels only."""

import math
import time

import numpy as np


def _raw(rows, reliability):
    return np.array(
        [
            [
                np.nan if r.get("bk_margin") is None else r["bk_margin"],
                -math.fsum(p * math.log(p) for p in r["bk_probabilities"]),
                float(w),
            ]
            for r, w in zip(rows, reliability, strict=True)
        ]
    )


def _matrix(raw, transform):
    filled = np.where(np.isnan(raw), transform["medians"], raw)
    standardized = np.clip((filled - transform["means"]) / transform["scales"], -8, 8)
    return np.column_stack((np.ones(len(raw)), standardized))


def fit_draw_calibrator(
    rows, outcomes, probabilities, reliability, *, l2, steps, deadline
):
    raw = _raw(rows, reliability)
    medians = [
        float(np.median(c[~np.isnan(c)])) if np.any(~np.isnan(c)) else 0.0
        for c in raw.T
    ]
    filled = np.where(np.isnan(raw), medians, raw)
    scales = filled.std(axis=0)
    transform = {
        "medians": medians,
        "means": filled.mean(axis=0).tolist(),
        "scales": np.where(scales > 1e-12, scales, 1.0).tolist(),
    }
    matrix = _matrix(raw, transform)
    weights = np.zeros(4)
    base_draw = probabilities[:, 1]
    base_logit = np.log(base_draw) - np.log1p(-base_draw)
    targets = np.array([float(y == 1) for y in outcomes])
    reliability = np.asarray(reliability)
    rate = 1 / (l2 + 0.5 * np.max(np.sum(matrix * matrix, axis=1)))
    for _ in range(steps):
        if time.monotonic() > deadline:
            raise TimeoutError("DRAW_FIT_TIME_BUDGET")
        residual = np.tanh(np.einsum("ij,j->i", matrix, weights, optimize=False))
        logits = np.clip(base_logit + reliability * residual, -40, 40)
        fitted = 1 / (1 + np.exp(-logits))
        gradient = (
            np.einsum(
                "ij,i->j",
                matrix,
                (fitted - targets) * reliability * (1 - residual**2),
                optimize=False,
            )
            / len(rows)
            + l2 * weights
        )
        weights -= rate * gradient
    return {
        "status": "EXPERIMENTAL_NOT_SCREENED",
        "feature_names": ["bk_margin", "bk_entropy", "reliability"],
        "transform": transform,
        "weights": weights.tolist(),
        "raw_shift_bound": 1.0,
    }


def draw_logit_shift(calibrator, row, reliability):
    if calibrator is None:
        return 0.0
    matrix = _matrix(_raw([row], [reliability]), calibrator["transform"])
    value = float(
        np.einsum("i,i->", matrix[0], np.array(calibrator["weights"]), optimize=False)
    )
    return reliability * math.tanh(value)
