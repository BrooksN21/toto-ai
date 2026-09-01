from __future__ import annotations

import numpy as np
import pytest

from toto_ai.optimizer.category_hit import (
    CategoryHitSeedInfeasibleError,
    _bounded_allocation,
    cover_14_bk_fill_seed,
)


def test_bounded_allocation_rejects_negative_capacity() -> None:
    allocation = _bounded_allocation(
        (0.4, 0.3, 0.3),
        0,
        np.zeros(3, dtype=np.int32),
        np.asarray((-1, 0, 0), dtype=np.int32),
    )

    assert allocation is None


def test_small_category_seed_fails_with_domain_error_not_numpy_error() -> None:
    probabilities = ((0.34, 0.33, 0.33),) * 15

    with pytest.raises(
        CategoryHitSeedInfeasibleError,
        match="infeasible at 6 coupons",
    ):
        cover_14_bk_fill_seed(probabilities, 180, 30)
