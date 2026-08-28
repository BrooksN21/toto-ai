import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package import select_ev_package
from toto_ai.ev.package_quality import (
    SUPPORTED_SCHEDULER_SCHEMA_VERSION,
    PackageSelectionProvenance,
    bound_selection_context,
    quality_v2_config_payload,
    selection_context_sha256,
)
from toto_ai.ev.ternary import compute_ev_components, materialize_ev_surface
from toto_ai.external_odds.schedule_evidence import load_schedule_evidence_ledger
from toto_ai.package.audit import (
    canonical_probability_input_sha256,
    evaluate_package_safety,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "safety_selector"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _package_sha256(package) -> str:
    selected = (
        package.paper_coupons
        if package.structural_status == "STRUCTURAL_PASS"
        else package.coupons
    )
    coupons = ",".join(row.coupon for row in selected)
    return hashlib.sha256(coupons.encode("utf-8")).hexdigest()


def _forbidden_selection_keys(value) -> set[str]:
    forbidden = {"result", "results", "score", "scores", "result_status"}
    if isinstance(value, dict):
        found = forbidden.intersection(value)
        return found.union(
            *(_forbidden_selection_keys(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_forbidden_selection_keys(item) for item in value))
    return set()


def _retrospective_hits(coupons, result: str) -> tuple[int, float]:
    hits = [
        sum(actual == selected for actual, selected in zip(result, coupon, strict=True))
        for coupon in coupons
    ]
    return max(hits), sum(hits) / len(hits)


def _write_frozen_scheduler_plan(path: Path, config: EVConfig) -> None:
    semantic = {
        "schema_version": SUPPORTED_SCHEDULER_SCHEMA_VERSION,
        "target": {
            "drawing": 4971,
            "drawing_id": 0,
            "ended_at": "frozen-test",
            "operational_cutoff": "frozen-test",
        },
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


@pytest.mark.heavy
@pytest.mark.research
@pytest.mark.parametrize(
    ("drawing", "expected"),
    [
        (
            4967,
            {
                "old_hash": (
                    "6854f91e18616c34f7267c4c28bbb2be5853e249a4e8b8b26ee07276cecf0177"
                ),
                "safe_hash": (
                    "3cf45fdeceee3cbec7f6380dfe5c643766865a181d78c8f289ab1096c44f4a34"
                ),
                "old_expected_payout": 240426.79007832042,
                "safe_expected_payout": 230204.68236597226,
                "old_hits": (5, 2.5602409638554215),
                "safe_hits": (5, 2.3855421686746987),
                    "quality_hash": (
                        "4466edbdba26cfd834528ea84ccb66ffe399558eb683eafe48ec959027cefe0e"
                    ),
                    "quality_pre_hash": (
                        "1d3e8bb1fd3e9bc5269ac1fa94eb3bd3f2e4e689db4a48a13be969e4b213ba90"
                    ),
                    "quality_expected_payout": 24220.904748135024,
                    "quality_hits": (12, 6.825301204819277),
                    "quality_probabilities": (
                        0.9613037109375,
                        0.014681710023644944,
                        0.001577812710087321,
                        7.40491769318058e-05,
                ),
            },
        ),
        (
            4969,
            {
                "old_hash": (
                    "85edc33d52e29b7dd51689e8a75bef12edfd69b73e915a4533972ddd882135ba"
                ),
                "safe_hash": (
                    "f4fde79d9bd1a8bd7f3725439f9b8f5fcf8da7dcadbe6e6240e3399743706ae0"
                ),
                "old_expected_payout": 397868.9428957945,
                "safe_expected_payout": 382668.74215943314,
                "old_hits": (8, 5.427710843373494),
                "safe_hits": (9, 5.554216867469879),
                    "quality_hash": (
                        "8395ab6be9f53ec11f3cf9ab2ec4779a57bbf0f933f7b632ae0319147361e38a"
                    ),
                    "quality_pre_hash": (
                        "8395ab6be9f53ec11f3cf9ab2ec4779a57bbf0f933f7b632ae0319147361e38a"
                    ),
                    "quality_expected_payout": 25054.79602582583,
                    "quality_hits": (9, 5.030120481927711),
                    "quality_probabilities": (
                        0.963623046875,
                        0.012337053994490883,
                        0.0012890197702330342,
                        5.937416371423911e-05,
                ),
            },
        ),
        (
            4970,
            {
                "old_hash": (
                    "86642f00ff08278416156ded973f94a5347f5ea681574dafe7b964761b257b06"
                ),
                "safe_hash": (
                    "b0a77d7c72c891e29db31e55f2837717ed48c9c89b84f7f5624f0849f5ddbe02"
                ),
                "old_expected_payout": 594028.0740453476,
                "safe_expected_payout": 578167.6969727423,
                "old_hits": (8, 5.102409638554217),
                "safe_hits": (8, 5.186746987951807),
                    "quality_hash": (
                        "2c5726c50ddfb8af733e99518c11a8f5818aba03271acc86fee1defab23d78af"
                    ),
                    "quality_pre_hash": (
                        "ae56a6ff1960cc524fa9a5ebb5a0870d21ad7eda3680f34c3236b9317603cd14"
                    ),
                    "quality_expected_payout": 33460.92459452146,
                    "quality_hits": (10, 5.63855421686747),
                    "quality_probabilities": (
                        0.961669921875,
                        0.010738058474865898,
                        0.0010744290112708929,
                        4.766600224159623e-05,
                ),
            },
        ),
    ],
)
def test_frozen_pre_cutoff_selector_regression_without_result_leakage(
    drawing,
    expected,
    tmp_path,
):
    frozen_path = FIXTURE_DIR / f"drawing_{drawing}_pre_cutoff.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    assert _forbidden_selection_keys(frozen) == set()
    assert datetime.fromisoformat(frozen["captured_at"].replace("Z", "+00:00")) < (
        datetime.fromisoformat(frozen["selection_cutoff_at"].replace("Z", "+00:00"))
    )

    ev_input = ev_input_from_payload(
        frozen["payload"],
        fetched_at=frozen["captured_at"],
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    components = compute_ev_components(ev_input)
    surface = materialize_ev_surface(
        components,
        ev_input.possible_winnings,
        ev_input.jackpot,
    )
    old_config = EVConfig(
        bank=4980,
        stake=30,
        mode="playable",
        min_gross_ev=1.0,
    )
    old_package = select_ev_package(surface, old_config)
    safety_v1_fixture = json.loads(
        (FIXTURE_DIR / "safety_v1_packages.json").read_text(encoding="utf-8")
    )["drawings"][str(drawing)]
    safety_v1_coupons = tuple(safety_v1_fixture["coupons"])
    ledger_path = PROJECT_ROOT / "data" / "schedule-evidence" / "ledger.json"
    ledger = load_schedule_evidence_ledger(ledger_path)
    plan_path = tmp_path / "scheduler-plan.json"
    selection_config = EVConfig(
        bank=4980,
        stake=30,
        mode="playable",
        min_gross_ev=1.0,
        package_safety_enabled=True,
        package_provenance_required=True,
    )
    _write_frozen_scheduler_plan(plan_path, selection_config)
    quality_package = select_ev_package(
        surface,
        selection_config,
        probabilities=ev_input.true_probabilities,
        provenance=PackageSelectionProvenance(
            probability_snapshot_sha256=hashlib.sha256(
                frozen_path.read_bytes()
            ).hexdigest(),
            probability_input_sha256=canonical_probability_input_sha256(
                ev_input.true_probabilities
            ),
            schedule_evidence_ledger_sha256=hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest(),
            schedule_evidence_semantic_hash=ledger.semantic_hash,
            probability_snapshot_path=str(frozen_path),
            schedule_evidence_ledger_path=str(ledger_path),
            scheduler_plan_path=str(plan_path),
            scheduler_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            selection_context=bound_selection_context(selection_config),
            selection_context_sha256=selection_context_sha256(selection_config),
        ),
    )

    old_hash = _package_sha256(old_package)
    safety_v1_hash = hashlib.sha256(
        ",".join(safety_v1_coupons).encode("utf-8")
    ).hexdigest()
    quality_hash = _package_sha256(quality_package)
    assert old_hash == expected["old_hash"]
    assert safety_v1_hash == expected["safe_hash"]
    assert quality_hash == expected["quality_hash"]
    assert len(old_package.coupons) == len(safety_v1_coupons) == 166
    assert quality_package.decision == "NO BET"
    assert quality_package.structural_status == "STRUCTURAL_PASS"
    assert len(quality_package.paper_coupons) == 166
    assert quality_package.paper_cost == 4980
    assert len(set(safety_v1_coupons)) == 166
    assert len({row.coupon for row in quality_package.paper_coupons}) == 166
    assert old_package.expected_payout == pytest.approx(expected["old_expected_payout"])
    assert safety_v1_fixture["expected_payout"] == pytest.approx(
        expected["safe_expected_payout"]
    )
    assert quality_package.paper_expected_payout == pytest.approx(
        expected["quality_expected_payout"]
    )

    old_safety = evaluate_package_safety(
        tuple(row.coupon for row in old_package.coupons),
        ev_input.true_probabilities,
    )
    safety_v1_safety = evaluate_package_safety(
        safety_v1_coupons,
        ev_input.true_probabilities,
    )
    quality_safety = evaluate_package_safety(
        tuple(row.coupon for row in quality_package.paper_coupons),
        ev_input.true_probabilities,
    )
    assert old_safety.decision == "NO BET"
    assert safety_v1_safety.decision == "PLAY"
    assert quality_safety.decision == "PLAY"

    diagnostics = quality_package.selection_diagnostics
    assert diagnostics is not None
    assert diagnostics.constraint_feasible is True
    assert diagnostics.provenance_complete is True
    assert diagnostics.pre_package_sha256 == expected["quality_pre_hash"]
    assert diagnostics.post_package_sha256 == quality_hash
    assert diagnostics.headroom_violation_count == 0
    category = diagnostics.post_category_probabilities
    assert category is not None
    assert (
        category.probability_at_least_9,
        category.probability_at_least_13,
        category.probability_at_least_14,
        category.probability_at_least_15,
    ) == pytest.approx(expected["quality_probabilities"])
    assert all(exposure.maximum_share < 0.95 for exposure in diagnostics.post_exposures)

    # Results are deliberately loaded only after both package hashes are fixed.
    finished = json.loads(
        (FIXTURE_DIR / "finished_results.json").read_text(encoding="utf-8")
    )
    result = next(
        row["result"]
        for row in finished["drawings"]
        if row["drawing_number"] == drawing
    )
    assert _retrospective_hits(
        tuple(row.coupon for row in old_package.coupons), result
    ) == pytest.approx(expected["old_hits"])
    assert _retrospective_hits(safety_v1_coupons, result) == pytest.approx(
        expected["safe_hits"]
    )
    observed_quality_hits = _retrospective_hits(
        tuple(row.coupon for row in quality_package.paper_coupons), result
    )
    assert observed_quality_hits == pytest.approx(expected["quality_hits"])
