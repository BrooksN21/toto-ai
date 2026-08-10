import hashlib
import json
import math
import time
from fractions import Fraction
from pathlib import Path

import pytest

from toto_ai.ev.drawing import build_open_ev_package
from toto_ai.ev.models import EVConfig, PlayTimingEligibility
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    bound_selection_context,
    quality_v2_config_payload,
    selection_context_sha256,
    selection_probability_input_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "safety_selector"
    / "drawing_4971_prospective.json"
)
RUNTIME_BUDGET_SECONDS = 360.0
pytestmark = [pytest.mark.heavy, pytest.mark.research]


def _integer_quote_row(row: tuple[float, ...]) -> tuple[int, ...]:
    fractions = tuple(Fraction(value).limit_denominator(10_000) for value in row)
    denominator = math.lcm(*(value.denominator for value in fractions))
    return tuple(
        value.numerator * (denominator // value.denominator)
        for value in fractions
    )


def _write_scheduler_plan(path: Path, config: EVConfig) -> None:
    semantic = {
        "schema_version": 6,
        "target": {"drawing": 4971, "drawing_id": 0, "ended_at": "frozen-test"},
        "config": {
            "quality_v2": quality_v2_config_payload(config),
            "selection_context": bound_selection_context(config),
            "selection_context_sha256": selection_context_sha256(config),
        },
        "paths": {},
    }
    document = {
        **semantic,
        "plan_id": hashlib.sha256(
            json.dumps(
                semantic,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:16],
        "deadlines": {},
    }
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")


def test_full_bank4980_quality_v2_sensitivity_build_meets_runtime_budget(
    tmp_path: Path,
) -> None:
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    probabilities = tuple(tuple(row) for row in frozen["true_probabilities"])
    crowd_probabilities = tuple(
        tuple(row) for row in frozen["crowd_probabilities"]
    )
    bookmaker_quotes = tuple(_integer_quote_row(row) for row in probabilities)
    payload = {
        "data": {
            "id": frozen["drawing_id"],
            "number": frozen["drawing_number"],
            "pool_sum": frozen["pool_sum"],
            "jackpot": frozen["jackpot"],
            "events": [
                {
                    "order": order,
                    "quotes": {
                        "bk_win_1": bookmaker_quotes[order][0],
                        "bk_draw": bookmaker_quotes[order][1],
                        "bk_win_2": bookmaker_quotes[order][2],
                        "pool_win_1": crowd_probabilities[order][0] * 100,
                        "pool_draw": crowd_probabilities[order][1] * 100,
                        "pool_win_2": crowd_probabilities[order][2] * 100,
                    },
                }
                for order in range(15)
            ],
        }
    }
    config = EVConfig(
        bank=4_980,
        stake=30,
        mode="playable",
        min_gross_ev=1.0,
        package_safety_enabled=True,
        package_provenance_required=True,
    )
    plan_path = tmp_path / "scheduler-plan.json"
    _write_scheduler_plan(plan_path, config)
    provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=FIXTURE,
        probability_input_sha256=selection_probability_input_sha256(probabilities),
        schedule_evidence_ledger_path=(
            PROJECT_ROOT / "data" / "schedule-evidence" / "ledger.json"
        ),
        scheduler_plan_path=plan_path,
        selection_config=config,
    )

    class FrozenClient:
        def drawing_info(self, drawing_id):
            raise AssertionError(f"unexpected network-style fetch for {drawing_id}")

    started = time.perf_counter()
    result = build_open_ev_package(
        client=FrozenClient(),
        drawing_id=int(payload["data"]["id"]),
        config=config,
        payload=payload,
        fetched_at=frozen["fetched_at"],
        selection_provenance=provenance,
        timing_eligibility_resolver=lambda _payload: PlayTimingEligibility(
            status="playable",
            reason="frozen prospective runtime fixture",
            target_fingerprint="a" * 64,
            fingerprint_match=True,
        ),
    )
    elapsed = time.perf_counter() - started
    print(f"quality_v2_bank4980_runtime_seconds={elapsed:.6f}")

    assert config.package_quality_repair_iterations == 12
    assert config.package_quality_candidate_count == 512
    assert config.package_optimization_probability_samples == 2_048
    assert config.package_probability_samples == 8_192
    assert len(result.sensitivity) == 4
    assert result.package.decision == "NO BET"
    assert result.package.structural_status == "STRUCTURAL_PASS"
    assert len(result.package.paper_coupons) == 166
    assert result.package.paper_cost == 4_980
    assert elapsed < RUNTIME_BUDGET_SECONDS
