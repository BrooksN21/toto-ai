"""Research safety is independently computed and cannot grant wager authority."""

from dataclasses import asdict

import pytest

from toto_ai.ev.models import EVConfig


def test_concentrated_candidate_is_rejected_without_changing_control():
    from toto_ai.sports_stats.v3_research_safety import audit_research_candidate

    control = ("1" * 15, "X" * 15, "2" * 15)
    candidate = ("1" * 15, "1" * 14 + "X", "1" * 14 + "2")
    result = audit_research_candidate(
        candidate,
        controls={"quality-v2": control, "robust": control},
        probabilities={"BK": [[1 / 3] * 3] * 15},
        config=EVConfig(bank=90, stake=30),
    )
    assert result["research_checks_passed"] is False
    assert result["concentration"]["zero_exposure_count"] == 28
    assert result["control_preserved"] is True
    assert result["operator_compatible"] is False
    assert "uploadable_coupons" not in str(result)


def test_equal_balanced_candidate_is_not_promoted_to_operator():
    from toto_ai.sports_stats.v3_research_safety import audit_research_candidate

    coupons = ("1" * 15, "X" * 15, "2" * 15)
    kwargs = dict(
        controls={"quality-v2": coupons, "robust": coupons},
        probabilities={"BK": [[1 / 3] * 3] * 15},
        config=EVConfig(bank=90, stake=30),
    )
    first = audit_research_candidate(coupons, **kwargs)
    assert first == audit_research_candidate(coupons, **kwargs)
    assert first["research_checks_passed"]
    assert first["activation_allowed"] is False
    assert first["concentration"]["max_hhi"] == pytest.approx(1 / 3)
    assert first["package_overlaps"]["quality-v2"]["jaccard"] == 1


def test_quality_v2_provenance_requires_exact_config_and_artifacts():
    from toto_ai.sports_stats.v3_research_safety import validate_research_provenance

    config = asdict(EVConfig(bank=90, stake=30))
    with pytest.raises(ValueError, match="provenance"):
        validate_research_provenance(
            None,
            probabilities=[[1 / 3] * 3] * 15,
            config=config,
            expected_config_sha256="0" * 64,
            expected_plan_sha256="e" * 64,
            expected_probability_snapshot_sha256="f" * 64,
        )


def test_native_provenance_validates_real_bytes_config_and_v3_array(tmp_path):
    import hashlib
    import importlib.util
    import json
    from dataclasses import replace
    from pathlib import Path

    from toto_ai.ev.package_quality import PackageSelectionProvenance
    from toto_ai.sports_stats.v3_probability import canonical_json, digest, seal
    from toto_ai.sports_stats.v3_research_safety import validate_research_provenance

    spec = importlib.util.spec_from_file_location(
        "f4_native_provenance_fixtures",
        Path(__file__).with_name("test_ev_package_quality.py"),
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    config = EVConfig(
        bank=90, stake=30, package_safety_enabled=True, package_provenance_required=True
    )
    rows = [[1 / 3] * 3] * 15
    snapshot = seal(
        {
            "kind": "SPORTS_V3_RESEARCH_PROBABILITY_INPUT",
            "model_sha256": "a" * 64,
            "final_input_sha256": "d" * 64,
            "probabilities": rows,
            "probability_input_sha256": digest(rows),
            "operator_compatible": False,
            "automatic_wagering": False,
        }
    )
    probability_path, ledger_path, plan_path = (
        tmp_path / n for n in ("v3.json", "ledger.json", "plan.json")
    )
    probability_path.write_text(canonical_json(snapshot))
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2025-01-01T00:00:00Z",
                "observations": [],
            }
        )
    )
    fixture._write_test_scheduler_plan(plan_path, config=config)
    provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=probability_path,
        probability_input_sha256=digest(rows),
        schedule_evidence_ledger_path=ledger_path,
        scheduler_plan_path=plan_path,
        selection_config=config,
    )
    kwargs = dict(
        probabilities=rows,
        config=asdict(config),
        expected_config_sha256=digest(asdict(config)),
        expected_plan_sha256=provenance.scheduler_plan_sha256,
        expected_probability_snapshot_sha256=provenance.probability_snapshot_sha256,
        expected_model_sha256="a" * 64,
        expected_final_input_sha256="d" * 64,
    )
    assert validate_research_provenance(asdict(provenance), **kwargs) == provenance
    with pytest.raises(ValueError, match="EV config"):
        validate_research_provenance(
            asdict(provenance),
            **{**kwargs, "config": asdict(replace(config, min_gross_ev=2))},
        )
    snapshot = seal({**snapshot, "probabilities": [[0.2, 0.3, 0.5]] * 15})
    probability_path.write_text(canonical_json(snapshot))
    new_hash = hashlib.sha256(probability_path.read_bytes()).hexdigest()
    provenance = replace(provenance, probability_snapshot_sha256=new_hash)
    with pytest.raises(ValueError, match="actual V3"):
        validate_research_provenance(
            asdict(provenance),
            **{**kwargs, "expected_probability_snapshot_sha256": new_hash},
        )
