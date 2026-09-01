from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from toto_ai.sports_stats.final_hybrid_settlement import (
    settle_final_hybrid_comparison,
)


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_fixture(tmp_path: Path):
    comparison_dir = tmp_path / "output" / "run-1" / "research-comparison"
    comparison_dir.mkdir(parents=True)
    packages = {
        "quality-v2": ("1" * 15, "1" * 14 + "2"),
        "sports-shadow": ("2" * 15, "2" * 14 + "1"),
        "quality-v3": ("X" * 15,),
        "robust": ("1X2" * 5,),
    }
    names = {
        "quality-v2": "baseline-final-research-coupons.txt",
        "sports-shadow": "sports-final-research-coupons.txt",
        "quality-v3": "quality-v3-final-research-coupons.txt",
        "robust": "robust-final-research-coupons.txt",
    }
    candidates = []
    for index, (strategy, coupons) in enumerate(packages.items(), start=1):
        path = comparison_dir / names[strategy]
        path.write_text(
            "RESEARCH ONLY / NOT ACTIVATED / DO NOT WAGER\n"
            "NOT A BALTBet UPLOAD FILE\n"
            f"role={strategy} stake=30 coupons={len(coupons)}\n\n"
            + "\n".join(coupons)
            + "\n",
            encoding="utf-8",
        )
        candidates.append(
            {
                "strategy_id": strategy,
                "package_sha256": hashlib.sha256(
                    ",".join(coupons).encode("ascii")
                ).hexdigest(),
                "coupon_count": len(coupons),
                "cost": len(coupons) * 30,
                "models": [
                    {
                        "model": "bk",
                        "probability_at_least_13": index / 100,
                        "probability_at_least_14": index / 1000,
                        "probability_at_least_15": index / 10000,
                    }
                ],
            }
        )
    comparison = {
        "schema_version": 1,
        "artifact_class": "FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON",
        "plan_id": "plan-1",
        "drawing_id": 12086,
        "drawing_number": 4993,
        "stake": 30,
        "experimental_selection": {"candidates": candidates},
        "automatic_wagering": False,
        "operator_compatible": False,
    }
    comparison["report_sha256"] = hashlib.sha256(_canonical(comparison)).hexdigest()
    report_path = comparison_dir / "comparison.json"
    report_path.write_text(json.dumps(comparison), encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "status": "READY_PARALLEL_PLAY_BEFORE_T10",
        "plan_id": "plan-1",
        "drawing": 4993,
        "drawing_id": 12086,
        "research_report": str(report_path),
        "research_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "automatic_wagering": False,
    }
    sidecar["record_sha256"] = hashlib.sha256(_canonical(sidecar)).hexdigest()
    status_path = tmp_path / "output" / "sidecar-status.json"
    status_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return status_path


def test_settles_exact_quality_and_sports_packages_without_coupon_output(tmp_path):
    status_path = _write_fixture(tmp_path)

    report, paths = settle_final_hybrid_comparison(
        sidecar_status_path=status_path,
        drawing_id=12086,
        drawing_number=4993,
        plan_id="plan-1",
        actual="1" * 15,
        output_dir=tmp_path / "settlement",
    )

    assert report["status"] == "COMPLETE"
    assert report["strategies"]["quality-v2"]["best_hits"] == 15
    assert report["strategies"]["sports-shadow"]["best_hits"] == 1
    assert report["comparison"]["sports_minus_quality_v2_best_hits"] == -14
    assert report["strategies"]["quality-v2"]["category_counts"]["15"] == 1
    assert report["automatic_wagering"] is False
    assert report["operator_compatible"] is False
    for path in paths.values():
        text = path.read_text(encoding="utf-8")
        assert "111111111111111" not in text
        assert "222222222222222" not in text


def test_rejects_tampered_comparison_report(tmp_path):
    status_path = _write_fixture(tmp_path)
    status = json.loads(status_path.read_text())
    Path(status["research_report"]).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="research report SHA-256 mismatch"):
        settle_final_hybrid_comparison(
            sidecar_status_path=status_path,
            drawing_id=12086,
            drawing_number=4993,
            plan_id="plan-1",
            actual="1" * 15,
            output_dir=tmp_path / "settlement",
        )
