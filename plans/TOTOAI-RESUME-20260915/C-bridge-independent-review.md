# Independent C dataset bridge review — 2026-09-15T18:17:13+03:00

**Verdict: CHANGES REQUESTED for full native bridge compatibility.** Exact byte/identity/time linkage of12 event chains passes independent review. No source edits, delegation, Git, DB, API, scheduler, consent or5007 mutations.

## Concrete P2 finding
`src/toto_ai/research/sports_v3_dataset_bridge.py:249,274`: prepared projection/history references retain absolute filesystem paths. Native `v3_family_evidence.py:175–181` forbids absolute evidence paths. With legitimate independently reviewed references, all12 actual4999chains fail direct O1 with **UNSAFE_REFERENCE_PATH**; V3 hides that annotation exception as O1_ANNOTATION_UNAVAILABLE. Fix the explicit physical-to-safe-logical-path bridge, preserve source bytes, issue new exact bindings and add end-to-end prepare_bridge/O1 coverage. Do not weaken the path guard. No further O1 guards were bypassed to force a PASS.

## Actual independent linkage / validator result
- Native ReviewedReference is supplied by the independent reviewing caller; no human-only requirement exists in inspected contract. Owner explicitly authorized this independent Codex review. It is not a human/pre-draw review and does not authorize model fit or operator release.
- Verified12projections+24histories=36event-local bindings, exact original source/review/plan hashes and native final-input identity. Native schedule resolution, fixture/home-away IDs, kickoff/capture/as_of, result exclusion and source updatedAt chronology rechecked. No class inference or own-authority boolean in author code.
- Created C-bridge-reviewed-references.json with exact event-local path/hash/scope groups; these are valid only for the stated V3 binding contract and are explicitly NOT O1-compatible yet.
- After legitimate linkage: **12native predictor rows built**, no predictor validation exceptions; event1 has38/53 observed features, other11have42/53. Every row has `scope_verified=false`, `source_rejected=false`, reliability0, evaluation_authorized=false. O1 error exposed directly:12/12UNSAFE_REFERENCE_PATH.
- All240history rows lack each of gender/age_group/squad_type; targets also have empty scope. Training and F4 readiness remain false.12/15currentevent linkages is not fullfold/dataset acceptance.

## Checks and remaining work
Fresh **110pytest PASS in0.49s**, Ruff2PASS. No full suite or training.19bridge tests plus91native family/probability contracts; the existing tests do not cover this actual end-to-end logical-path failure.
Remaining: path compatibility; reviewed class evidence; missing4999events9/14 and unsupported manual format event12; missing5000–5006history; complete15-event sealed folds/label availability.5007early input/capture mismatch is expected and was not reclassified as a live scheduler error. Operations-contract files being edited elsewhere were not reviewed.

An initial reviewer-only assertion confused native snapshot semantic identity with file-byte SHA; native loading then confirmed the actual immutable input. Both hashes are separately recorded; no data-corruption claim.

Detailed receipts: C-bridge-independent-review.json, C-bridge-reviewed-references.json, C-bridge-native-validation.json, C-bridge-independent-checks.json. Only these current-task review files were written; author source hashes remain unchanged. No commit or push.
