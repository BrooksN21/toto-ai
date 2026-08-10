import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package import select_ev_package
from toto_ai.ev.ternary import compute_ev_components, materialize_ev_surface
from toto_ai.package.audit import evaluate_package_safety

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "safety_selector"


def _package_sha256(package) -> str:
    coupons = ",".join(row.coupon for row in package.coupons)
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


def _retrospective_hits(package, result: str) -> tuple[int, float]:
    hits = [
        sum(
            actual == selected
            for actual, selected in zip(result, row.coupon, strict=True)
        )
        for row in package.coupons
    ]
    return max(hits), sum(hits) / len(hits)


@pytest.mark.parametrize(
    ("drawing", "expected"),
    [
        (
            4967,
            {
                "old_hash": (
                    "6854f91e18616c34f7267c4c28bbb2be"
                    "5853e249a4e8b8b26ee07276cecf0177"
                ),
                "safe_hash": (
                    "3cf45fdeceee3cbec7f6380dfe5c64376"
                    "6865a181d78c8f289ab1096c44f4a34"
                ),
                "old_expected_payout": 240426.79007832042,
                "safe_expected_payout": 230204.68236597226,
                "gross_ev_delta": -340.7369237449375,
                "candidate_universe": 131072,
                "material_repairs": 17,
                "replacements": 18,
                "old_hits": (5, 2.5602409638554215),
                "safe_hits": (5, 2.3855421686746987),
            },
        ),
        (
            4969,
            {
                "old_hash": (
                    "85edc33d52e29b7dd51689e8a75bef12"
                    "edfd69b73e915a4533972ddd882135ba"
                ),
                "safe_hash": (
                    "f4fde79d9bd1a8bd7f3725439f9b8f5f"
                    "cf8da7dcadbe6e6240e3399743706ae0"
                ),
                "old_expected_payout": 397868.9428957945,
                "safe_expected_payout": 382668.74215943314,
                "gross_ev_delta": -506.67335787871525,
                "candidate_universe": 32768,
                "material_repairs": 11,
                "replacements": 18,
                "old_hits": (8, 5.427710843373494),
                "safe_hits": (9, 5.554216867469879),
            },
        ),
        (
            4970,
            {
                "old_hash": (
                    "86642f00ff08278416156ded973f94a53"
                    "47f5ea681574dafe7b964761b257b06"
                ),
                "safe_hash": (
                    "b0a77d7c72c891e29db31e55f283771"
                    "7ed48c9c89b84f7f5624f0849f5ddbe02"
                ),
                "old_expected_payout": 594028.0740453476,
                "safe_expected_payout": 578167.6969727423,
                "gross_ev_delta": -528.6792357534941,
                "candidate_universe": 32768,
                "material_repairs": 12,
                "replacements": 16,
                "old_hits": (8, 5.102409638554217),
                "safe_hits": (8, 5.186746987951807),
            },
        ),
    ],
)
def test_frozen_pre_cutoff_selector_regression_without_result_leakage(
    drawing,
    expected,
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
    safe_package = select_ev_package(
        surface,
        EVConfig(
            bank=4980,
            stake=30,
            mode="playable",
            min_gross_ev=1.0,
            package_safety_enabled=True,
        ),
        probabilities=ev_input.true_probabilities,
    )

    old_hash = _package_sha256(old_package)
    safe_hash = _package_sha256(safe_package)
    assert old_hash == expected["old_hash"]
    assert safe_hash == expected["safe_hash"]
    assert len(old_package.coupons) == len(safe_package.coupons) == 166
    assert safe_package.cost == 4980
    assert len({row.coupon for row in safe_package.coupons}) == 166
    assert old_package.expected_payout == pytest.approx(expected["old_expected_payout"])
    assert safe_package.expected_payout == pytest.approx(
        expected["safe_expected_payout"]
    )

    old_safety = evaluate_package_safety(
        tuple(row.coupon for row in old_package.coupons),
        ev_input.true_probabilities,
    )
    safe_safety = evaluate_package_safety(
        tuple(row.coupon for row in safe_package.coupons),
        ev_input.true_probabilities,
    )
    assert old_safety.decision == "NO BET"
    assert safe_safety.decision == "PLAY"

    diagnostics = safe_package.selection_diagnostics
    assert diagnostics is not None
    assert diagnostics.constraint_feasible is True
    assert diagnostics.pre_package_sha256 == old_hash
    assert diagnostics.post_package_sha256 == safe_hash
    assert diagnostics.candidate_universe_count == expected["candidate_universe"]
    assert len(diagnostics.material_outcomes_repaired) == expected["material_repairs"]
    assert len(diagnostics.replacements) == expected["replacements"]
    assert diagnostics.gross_ev_delta == pytest.approx(expected["gross_ev_delta"])
    assert all(
        exposure.maximum_share < 0.95
        for exposure in diagnostics.post_exposures
    )

    # Results are deliberately loaded only after both package hashes are fixed.
    finished = json.loads(
        (FIXTURE_DIR / "finished_results.json").read_text(encoding="utf-8")
    )
    result = next(
        row["result"]
        for row in finished["drawings"]
        if row["drawing_number"] == drawing
    )
    assert _retrospective_hits(old_package, result) == pytest.approx(
        expected["old_hits"]
    )
    assert _retrospective_hits(safe_package, result) == pytest.approx(
        expected["safe_hits"]
    )
