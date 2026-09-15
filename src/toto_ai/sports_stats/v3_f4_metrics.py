"""Fixed F4 metrics and paired drawing-cluster bootstrap; no fit or authority."""

import math

import numpy as np

from toto_ai.sports_stats.v3_probability import _bk, _check

BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260904


def _components(probabilities, labels):
    _check(len(probabilities) == len(labels), "metric lengths")
    loss, brier, draw_brier, correct, non_draw = [], [], [], [], []
    bins = np.zeros((10, 3), dtype=float)  # count, confidence sum, correct sum
    for row, actual in zip(probabilities, labels, strict=True):
        row = _bk(row)
        _check(type(actual) is int and actual in (0, 1, 2), "metric label")
        loss.append(-math.log(max(row[actual], 1e-15)))
        brier.append(math.fsum((p - int(i == actual)) ** 2 for i, p in enumerate(row)))
        draw_brier.append((row[1] - int(actual == 1)) ** 2)
        confidence = max(row)
        hit = int(row.index(confidence) == actual)
        correct.append(hit)
        non_draw.append(actual != 1)
        bins[min(int(confidence * 10), 9)] += (1, confidence, hit)
    return loss, brier, draw_brier, correct, non_draw, bins


def probability_metrics(probabilities, labels):
    loss, brier, draw, correct, non_draw, bins = _components(probabilities, labels)
    count = len(labels)
    if not count:
        return {
            "event_count": 0,
            "log_loss": None,
            "brier": None,
            "draw_brier": None,
            "ece": None,
            "top_correct": 0,
            "non_draw_count": 0,
            "non_draw_log_loss": None,
        }
    non_draw_loss = [v for v, keep in zip(loss, non_draw, strict=True) if keep]
    return {
        "event_count": count,
        "log_loss": math.fsum(loss) / count,
        "brier": math.fsum(brier) / count,
        "draw_brier": math.fsum(draw) / count,
        "ece": float(np.abs(bins[:, 1] - bins[:, 2]).sum()) / count,
        "top_correct": sum(correct),
        "non_draw_count": len(non_draw_loss),
        "non_draw_log_loss": (
            math.fsum(non_draw_loss) / len(non_draw_loss) if non_draw_loss else None
        ),
    }


def paired_cluster_bootstrap(folds):
    """Resample whole drawings, maintaining all15 events and paired A4/A0 rows.

    ECE is recomputed after cluster aggregation, not averaged over fold ECEs.
    Fixed PCG64 seed, sample count and linear quantiles are not caller-tunable.
    """
    count = len(folds)
    _check(0 < count <= 128, "bootstrap drawing count")
    sizes = np.array([len(f["labels"]) for f in folds])
    _check(all(n == 15 for n in sizes), "bootstrap complete drawings")
    index = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED)).integers(
        0, count, size=(BOOTSTRAP_SAMPLES, count)
    )
    denominator = sizes[index].sum(axis=1)
    estimates = {}
    for variant in ("A0", "A4"):
        parts = [_components(f[variant], f["labels"]) for f in folds]
        totals = np.array([[math.fsum(p[i]) for i in range(3)] for p in parts])
        bins = np.array([p[-1] for p in parts])
        sampled = totals[index].sum(axis=1) / denominator[:, None]
        aggregate_bins = bins[index].sum(axis=1)
        ece = np.abs(aggregate_bins[:, :, 1] - aggregate_bins[:, :, 2]).sum(axis=1)
        estimates[variant] = np.column_stack((sampled, ece / denominator))
    paired = estimates["A4"] - estimates["A0"]
    names = ("log_loss", "brier", "draw_brier", "ece")
    return {
        "method": "PAIRED_WHOLE_DRAWING_PCG64_LINEAR_QUANTILE",
        "sample_count": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
        "cluster_count": count,
        **{
            name + "_95_ci": np.quantile(
                paired[:, i], [0.025, 0.975], method="linear"
            ).tolist()
            for i, name in enumerate(names)
        },
        "superiority_proven": False,
        "small_cluster_warning": count < 30,
    }
