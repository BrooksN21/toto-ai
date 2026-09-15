from copy import deepcopy
from dataclasses import asdict
import pytest
import test_sports_v3_probability as base
import test_sports_v3_generation as gen
from toto_ai.sports_stats import v3_probability as v3, v3_parallel as parallel, v3_generation as generation
from toto_ai.sports_stats.v3_feature_disposition import feature_disposition

@pytest.mark.parametrize("variant", ["A3", "A4"])
def test_independent_future_label_semantic_rejection_even_after_both_hashes(variant):
    model = base.fit(variant=variant)
    model["training_rows"][0]["label_available_at"] = "2099-01-01T00:00:00+00:00"
    model["training_manifest_sha256"] = v3.digest(model["training_rows"])
    model = v3.seal(model)
    with pytest.raises(ValueError, match="label|chronology|availability"):
        v3.load_model(v3.canonical_json(model))
    prediction = v3.infer_v3(model, base.feature(10))
    assert prediction["status"] == "BK_FALLBACK"
    assert prediction["probabilities"] == base.feature(10)["bk_probabilities"]

def test_independent_changed_bk_rejected_before_generator(monkeypatch):
    request, context = gen.fixtures.request(), gen.fixtures.context()
    original = asdict(gen.frozen())
    context["frozen_input"] = original
    inference = parallel.infer_final_bk(request, context)
    changed = deepcopy(original)
    changed["events"][0]["bk_probabilities"] = [0.8, 0.1, 0.1]
    with pytest.raises(ValueError, match="frozen payload binding"):
        generation.generate_v3_candidate(request=request, inference=inference,
          frozen_payload=changed, control_coupons=(), gate={"status":"SYNTHETIC_TEST_ONLY"})

@pytest.mark.parametrize("proof", [True, False])
def test_independent_core_optional_missingness_never_grants_authority(proof):
    row = base.feature(10)
    row["scope_verified"] = proof
    for key in set(v3.FEATURE_NAMES) - set(v3.CORE_NAMES):
        row["features"][key] = None
    result = feature_disposition(row)
    assert result["core_source_computable"] is True
    assert result["A2_A3"]["input_contract_satisfied"] is proof
    assert result["A4_A5"]["input_contract_satisfied"] is proof
    assert all(result[k] is False for k in ("training_authorized", "evaluation_authorized", "activation_allowed"))
    row["features"][v3.CORE_NAMES[0]] = None
    partial = feature_disposition(row)
    assert not partial["A2_A3"]["input_contract_satisfied"]
    assert partial["A4_A5"]["input_contract_satisfied"] is proof

@pytest.mark.parametrize("variant, partial", [("A2",False),("A3",False),("A4",True),("A5",True)])
def test_independent_actual_inference_core_optional_policy(variant, partial):
    model = base.fit(variant=variant)
    row = base.feature(10)
    for key in set(v3.FEATURE_NAMES) - set(v3.CORE_NAMES):
        row["features"][key] = None
    if partial:
        row["features"][v3.CORE_NAMES[0]] = None
    row = v3.seal(row)
    assert v3.infer_v3(model,row)["status"] == "PREDICTED_EXPERIMENTAL"
    unverified = v3.seal({**row,"scope_verified":False})
    result = v3.infer_v3(model,unverified)
    assert result["status"] == "BK_FALLBACK"
    assert result["probabilities"] == row["bk_probabilities"]
