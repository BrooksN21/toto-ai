import csv

import pytest

from toto_ai.optimizer.strategy_backtest import StrategyBacktestRow
from toto_ai.optimizer.strategy_diagnostics import (
    development_drawing_ids,
    load_frozen_development_rows,
)


def test_development_ids_exclude_holdout():
    manifest = {"last": 5, "holdout_size": 2, "drawing_ids": [1, 2, 3, 4, 5]}

    assert development_drawing_ids(manifest) == [1, 2, 3]


def test_development_ids_reject_duplicate_manifest_ids():
    manifest = {"last": 3, "holdout_size": 1, "drawing_ids": [1, 2, 2]}

    with pytest.raises(ValueError, match="duplicate drawing IDs"):
        development_drawing_ids(manifest)


def test_frozen_rows_require_one_row_per_development_strategy(tmp_path):
    path = write_frozen_rows(tmp_path, drawing_ids=[1], omit="weighted_coverage")

    with pytest.raises(ValueError, match="exactly one frozen row"):
        load_frozen_development_rows(
            path,
            {"last": 2, "holdout_size": 1, "drawing_ids": [1, 2]},
        )


def test_frozen_rows_require_development_segment(tmp_path):
    path = write_frozen_rows(tmp_path, drawing_ids=[1], segment="holdout")

    with pytest.raises(ValueError, match="development segment"):
        load_frozen_development_rows(
            path,
            {"last": 2, "holdout_size": 1, "drawing_ids": [1, 2]},
        )


def write_frozen_rows(tmp_path, drawing_ids, omit=None, segment="development"):
    path = tmp_path / "frozen.csv"
    fieldnames = list(StrategyBacktestRow.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for drawing_id in drawing_ids:
            for strategy in (
                "baseline_brief",
                "top_probability",
                "weighted_coverage",
            ):
                if strategy == omit:
                    continue
                writer.writerow(
                    {
                        "drawing_id": drawing_id,
                        "drawing_number": 1000 + drawing_id,
                        "segment": segment,
                        "strategy": strategy,
                        "best_hits": 10,
                        "hit_13": False,
                        "hit_14": False,
                        "hit_15": False,
                        "package_size": 10,
                        "package_cost": 300,
                        "estimated_coverage": 0.5,
                        "candidate_count": 20,
                        "runtime_seconds": 0.1,
                        "package_hash": f"hash-{drawing_id}-{strategy}",
                    }
                )
    return path
