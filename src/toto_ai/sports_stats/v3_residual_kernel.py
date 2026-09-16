"""Shared native A5 numerical loop only; no data admission or release authority."""

import time

import numpy as np


def softmax(logits):
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    values = np.exp(shifted)
    return values / values.sum(axis=-1, keepdims=True)


def fit_residual(
    matrix,
    targets,
    prior,
    reliability_weights,
    *,
    l2,
    steps,
    started,
    time_budget_seconds,
):
    """Exactly the legacy fixed-step L2 BK-residual optimizer.

    Inputs are prevalidated numeric matrices by the caller. The monotonic budget
    begins at the wrapper's original start, including validation/preparation.
    """
    weights = np.zeros((matrix.shape[1], 3))
    rate = 1.0 / (l2 + 0.5 * np.max(np.sum(matrix * matrix, axis=1)) * 0.2**2)
    for _ in range(steps):
        if time.monotonic() - started > time_budget_seconds:
            raise TimeoutError("FIT_TIME_BUDGET")
        prediction = softmax(
            prior
            + reliability_weights
            * np.einsum("ij,jk->ik", matrix, weights, optimize=False)
        )
        gradient = (
            np.einsum(
                "ij,ik->jk",
                matrix,
                reliability_weights * (prediction - targets),
                optimize=False,
            )
            / len(matrix)
            + l2 * weights
        )
        weights -= rate * gradient
        weights -= weights.mean(axis=1, keepdims=True)
    return weights
