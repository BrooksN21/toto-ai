"""Independent numerical oracles, not historical evidence or fitted weights."""

import math

import pytest


def test_uniform_probability_metrics_match_closed_form():
    from toto_ai.sports_stats.v3_f4_metrics import probability_metrics

    value = probability_metrics([[1 / 3] * 3] * 3, [0, 1, 2])
    assert value["log_loss"] == pytest.approx(math.log(3))
    assert value["brier"] == pytest.approx(2 / 3)
    assert value["draw_brier"] == pytest.approx(2 / 9)
    assert value["ece"] == pytest.approx(0)
    assert value["top_correct"] == 1
    assert value["non_draw_log_loss"] == pytest.approx(math.log(3))


def test_cluster_bootstrap_is_deterministic_and_preserves_constant_pairing():
    from toto_ai.sports_stats.v3_f4_metrics import paired_cluster_bootstrap

    folds = [
        {
            "A0": [[0.4, 0.3, 0.3]] * 15,
            "A4": [[0.5, 0.25, 0.25]] * 15,
            "labels": [0] * 15,
        }
        for _ in range(7)
    ]
    result = paired_cluster_bootstrap(folds)
    assert result == paired_cluster_bootstrap(folds)
    assert result["sample_count"] == 10_000
    assert result["cluster_count"] == 7
    assert result["log_loss_95_ci"] == pytest.approx([math.log(0.4 / 0.5)] * 2)
    assert result["superiority_proven"] is False


@pytest.mark.parametrize(
    "bad", [[[0, 0.5, 0.5]], [[0.2, 0.3, 0.6]], [[float("nan"), 0.5, 0.5]]]
)
def test_invalid_probability_rows_are_rejected(bad):
    from toto_ai.sports_stats.v3_f4_metrics import probability_metrics

    with pytest.raises(ValueError):
        probability_metrics(bad, [0])
