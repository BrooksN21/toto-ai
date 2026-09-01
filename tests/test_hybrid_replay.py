from types import SimpleNamespace

import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import (
    bound_selection_context,
    quality_v2_config_payload,
    selection_context_sha256,
)
from toto_ai.optimizer.hybrid_replay import (
    _historical_provenance,
    _rebase_sports_probabilities,
    _strategy_payload,
)
from toto_ai.optimizer.quality_replay import _historical_quality_v2_config


def _playable_config() -> EVConfig:
    return EVConfig(
        bank=60,
        stake=30,
        mode="playable",
        effective_budget=60,
        package_safety_enabled=True,
        package_provenance_required=True,
    )


def test_historical_quality_config_round_trips_bound_plan_context():
    config = _playable_config()
    context = bound_selection_context(config)
    payload = {
        "selection_context": context,
        "selection_context_sha256": selection_context_sha256(context),
        "quality_v2": quality_v2_config_payload(config),
    }

    assert _historical_quality_v2_config(payload) == config


def test_sports_rebase_uses_event_fallback_and_blend_weight():
    baseline = ((0.5, 0.3, 0.2),) * 15
    events = tuple(
        SimpleNamespace(
            event_order=order,
            blend_weight=0.2,
            fallback_reason="missing" if order == 0 else None,
            sports_probabilities=(0.2, 0.3, 0.5),
        )
        for order in range(15)
    )

    result = _rebase_sports_probabilities(baseline, events)

    assert result[0] == baseline[0]
    assert result[1] == pytest.approx((0.44, 0.3, 0.26))


def test_historical_provenance_preserves_declared_seed_hashes():
    config = _playable_config()
    research = EVConfig(
        **{
            **config.__dict__,
            "package_provenance_required": False,
        }
    )
    plan = SimpleNamespace(
        schedule_evidence_ledger_sha256="c" * 64,
        schedule_evidence_semantic_hash="d" * 64,
    )

    provenance = _historical_provenance(
        plan=plan,
        config=research,
        probability_snapshot_sha256="a" * 64,
        probability_input_sha256="b" * 64,
        scheduler_plan_sha256="e" * 64,
    )

    assert provenance.schedule_evidence_ledger_sha256 == "c" * 64
    assert provenance.schedule_evidence_semantic_hash == "d" * 64
    assert provenance.selection_context == bound_selection_context(research)


def test_strategy_payload_settles_equal_cost_package():
    probabilities = {"bk": ((0.5, 0.3, 0.2),) * 15}
    payload = _strategy_payload(
        ("1" * 15, "X" * 15),
        models=probabilities,
        actual="X" * 15,
        stake=30,
    )

    assert payload["coupon_count"] == 2
    assert payload["cost"] == 60
    assert payload["settlement"]["best_hits"] == 15
    assert payload["settlement"]["hit15"] == 1
    assert payload["models"][0]["model"] == "bk"
