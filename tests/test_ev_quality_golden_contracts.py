import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = (
    ROOT
    / "plans"
    / "TOTOAI-AUDIT-4971-PACKAGE-20260810"
    / "frozen-results"
)
CURRENT_OBJECTIVE = [
    "probability_at_least_13",
    "probability_at_least_14",
    "probability_at_least_15",
    "independent_probability_at_least_9",
    "diversity",
    "robust_ev",
]


@pytest.mark.parametrize("drawing", [4967, 4969, 4970])
def test_refreshed_quality_v2_golden_contract_without_surface_recomputation(
    drawing: int,
) -> None:
    payload = json.loads(
        (RESULTS / f"quality-v2-{drawing}.json").read_text(encoding="utf-8")
    )
    quality = payload["packages"]["quality_v2"]
    old = payload["packages"]["old"]
    diagnostics_hash = payload["selector_diagnostics_sha256"]

    assert payload["current_code_status"] == "golden_verified_by_separate_node"
    assert payload["current_code_objective_order"] == CURRENT_OBJECTIVE
    assert payload["release_gate_decision"] == "NO BET"
    assert payload["real_money_actionable"] is False
    assert quality["top_level_decision"] == "NO BET"
    assert quality["structural_status"] == "STRUCTURAL_PASS"
    assert quality["artifact_class"] == "TRAINING/PAPER"
    assert quality["count"] == 166
    assert quality["cost"] == 4_980
    assert min(
        count
        for row in quality["exposure"]["counts"]
        for count in row
    ) > 1
    assert quality["exposure"]["maximum_count"] <= 152
    assert payload["headroom_violation_count"] == 0
    assert quality["hamming"]["close_pair_count"] < old["hamming"][
        "close_pair_count"
    ]
    assert quality["hamming"]["mean_pairwise_hamming"] > old["hamming"][
        "mean_pairwise_hamming"
    ]
    assert quality["hamming"]["effective_pattern_count"] > old["hamming"][
        "effective_pattern_count"
    ]
    assert len(diagnostics_hash) == 64
    assert int(diagnostics_hash, 16) >= 0
    for key in (
        "probability_snapshot_sha256",
        "probability_input_sha256",
        "schedule_evidence_ledger_sha256",
        "schedule_evidence_semantic_hash",
        "scheduler_plan_sha256",
        "quality_v2_config_sha256",
    ):
        value = payload["provenance"][key]
        assert len(value) == 64
        assert int(value, 16) >= 0


def test_4967_golden_records_poor_predictive_result_without_release_claim() -> None:
    payload = json.loads(
        (RESULTS / "quality-v2-4967.json").read_text(encoding="utf-8")
    )
    quality = payload["packages"]["quality_v2"]

    assert quality["observed"]["best_hits"] == 7
    assert quality["observed"]["hit13"] is False
    assert quality["observed"]["hit14"] is False
    assert quality["observed"]["hit15"] is False
    assert payload["release_gate_decision"] == "NO BET"
    assert payload["real_money_actionable"] is False
