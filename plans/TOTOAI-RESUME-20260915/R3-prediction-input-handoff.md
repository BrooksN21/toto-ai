# R3 prediction handoff — frozen model, no refit

Task TOTOAI-RESUME-20260915. Code remains frozen for Huygensreview. This handoff only defines the EXISTING API and its limitations. No predicates changed; no model modification or evaluation-label access.

## Send these exact inputs

1. A features-only JSON array for4999–5006: separately `seal()`-hashed `RETROSPECTIVE_SPORTS_FEATURES_V1` rows; same exact22field schema and53feature names as sibling JSON. Source/BKhash bindings and provider/canonical fixture IDs must remain traceable to original ordered TotoBriefslots. No result/score/label fields anywhere in feature DTO.
2. SHA256 of that file, independent current review path/SHA and exact approved row hashes (positive Sports rows versus explicitly reviewed UNKNOWN/zero-weight rows distinguished). Identity-only mutation, if needed, creates a DERIVED COPY withold→newhash mapping; never rewrite originalC/R1files.
3.120-slot denominator/coverage manifest with draw+zero-basedorder, source-localID↔providerfixtureID, originalR1market source hash and normalized3-wayBK mapping, source timestamps, exclusions/unknownreasons. Real kickoff is mandatory undercurrentfrozenpredictor. No fake timestamps or IDs to fill slots.
4. NO evaluation labels yet. After frozen probabilities are saved, a separate label file can use exact `{drawing_number,event_id,outcome,source_sha256,sha256}` rows (outcome0/1/2, separatelyseal()). Label mapping must use the same verified event/slot binding, not array guesses.

## Prediction-only invocation (paths supplied by Cicero, not assumed existing)

```python
import hashlib,json
from pathlib import Path
from toto_ai.sports_stats.v3_probability import _sealed
from toto_ai.research.sports_v3_retrospective_fit import freeze_predictions
model_path=Path("reports/rehearsal/TOTOAI-RESUME-20260915/R3-fit/real-fit-v1/model.json")
model_bytes=model_path.read_bytes()
assert hashlib.sha256(model_bytes).hexdigest()=="f334b21efd5dfd369c530d7e037b7c9ac8e6ee087d235872ac42453579d37b0e"
model=json.loads(model_bytes);_sealed(model)
assert model["sha256"]=="8381fcf507c77152835e69325c46e446d40e5acb163bf019f03ea1c16d74fdde"
# Load and verify the independently reviewed FEATURES-ONLY file + exacthashes.
# rows and reviewed_feature_hashes come from that handoff, not auto-approval.
prediction=freeze_predictions(model,rows,
    independently_reviewed_hashes=reviewed_feature_hashes)
# Write once with exclusive mode; never overwrite/relabel an earlier forecast.
output=Path("reports/rehearsal/TOTOAI-RESUME-20260915/R3-fit/evaluation-v1/predictions.json")
output.parent.mkdir(parents=True,exist_ok=True)
with output.open("x") as stream:
    json.dump(prediction,stream,indent=2,allow_nan=False)
    stream.write("\n")
# Persist returned contentSHA and fileSHA BEFORE accessing any label file.
```

Then, separately, load the saved prediction, verify bothhashes, obtain hashedlabels and invoke `score_predictions`. Produce overall and per-draw logloss/Brier vs sameBK, numericSportscoverage/BKfallback counts, unchangedmodelhash. Predictions retain domainRETROSPECTIVE, unknownasofSENSITIVITY, previouslyseen/nonblind; no5008operatoractivation or profitabilityclaim.

## Conditional handling — do not guess

- Missing numeric features remainNone; existingtrain-onlymedians/missingindicators apply. NEVER fit preprocessing on evaluation.
- Proven researchidentity with unknown taxonomy is allowed only under explicit researchreview, taxonomy staysnull. Unreviewedidentity remainsUNKNOWN/weight0/BKfallback.
- Currententry still validates realkickoff/canonicalID and15 validrows/group. If those fields genuinely missing, return the slot inunsupportedcoverage rather than fabricate it. The8draw/120denominator remains intact outside thepredictioninput; no false120predictclaim.
- If a prediction-only marketfallback bridge is required, notifyparent/reviewer with exactmissingfields first; specify/test separatepredicates and modelcode-compatibility. Thefrozenmodelpins thismodule'sbytes: editingthemodule then rewritingthemodel'scodehash is NOT acceptable. No patch/bypass was made inthisjob.
