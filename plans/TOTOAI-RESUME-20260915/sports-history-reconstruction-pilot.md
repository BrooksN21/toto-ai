# R2 bounded sporting-history pilot —5004/event9

Task TOTOAI-RESUME-20260915. Completed 2026-09-15T17:25:43.929625+00:00. Implementation DONE, independent review pending. No training, publication or live integration.

## Actual result
Two real GOAL histories,20records;2copies of target excluded BEFORE score extraction;18unique prior matches,9perteam. Native `build_sports_v3_feature_table`,rolling10/minimum5:24/28numeric values. Reconstructed Moscow-close T-10 is2026-09-12T12:50Z, not target kickoff14:15Z and not an authenticated operator decision.

Four missing values: home/away venue goalsfor/goalsagainst; native venue counts3and4 below declaredminimum5. No minimum was reduced. Native home rollingPPG1.555556,away1.111111. Target labels never passed to feature builder. Tests also exclude a future-to-decision match that is still before target kickoff, and ensure AET/PEN only use regulation90.

**Classification:** HISTORICAL_RECONSTRUCTION_SENSITIVITY_UNVERIFIED_ASOF. Every historical row retains exactsourcehash,real observed_at/updatedAt; availability and finished_at unknown; gender/age/squad unknown. 0/18 retained rows have at leastone updatedAt after reconstructedcutoff. fit_eligible=false for all rows and artifact. This is successful numeric extraction, NOT an O1/F4datasetPASS, causalbacktest or proof of class/availability. Original captured snapshots untouched; native gates unchanged.

## Verification
RED before implementation(module absent); secondRED beforemanifest runner. Final20focusedpytestPASS0.41s;RuffPASS2changedfiles. Tests: target/future exclusion before scores, target-label perturbation invariance, exact IDs/kickoff/alias collision, sourcebyte tamper, wrong team, missing target, conflict revisions, nonterminal/FT90, realdates/no falsefit, manifest end-to-end, path traversal/symlinkescape, codehash mismatch, explicitMoscowwall. No syntheticfit.

## Resume actual extraction (choose a NEW output basename)
```sh
.venv/bin/python -m toto_ai.research.sports_history_reconstruction \
  --manifest reports/rehearsal/TOTOAI-RESUME-20260915/sports-history-reconstruction/5004-pilot-run-manifest.json \
  --output reports/rehearsal/TOTOAI-RESUME-20260915/sports-history-reconstruction/5004-pilot-rerun.json
```
Run from /Users/turshevr/toto-ai. NoAPI/DB. Existing output refuses overwrite; adapterhash inmanifest detects code drift. Preserve current result rather than rerunning unnecessarily. Final source/output hashes in companionJSON. Core inputsha binds exacttargetconfig+sourcehashes; runreceipt also bindsmanifest andadaptercode. Source hashes were frozen from extant bytes for research, not an independentreview authority.

## Collector next step
`resumable-collector-plan.json` in pilotdir: cache-first exactfixture/ID joins for120targets; other cached candidates remain unreviewed. ExistingGOAL datepages5000 and coverage refs are startingpoints. Actual newcalls thisimplementation0(priorcontext1). Exactmissingrequestlist currentlyEMPTY/INCOMPLETE; no newcalls authorized. Aftermapping/review, request one missingunique verifiedteam history atatime, suggested firstfillcap10,retries0,timeout10. Totalcost unknown until IDs/oldwindows checked. Currentadapterlast10only; no invented historicalpagination.

## Handoff / scope
Priorhandoff saved sports-history-reconstruction-context.md. Parent checkpoint interrupted priorcommand, nothumanowner. Scopedcheckfound no matching stdinPythonprocess or plannedpartialoutputs; noglobalprocessaudit. Only newinactiveadapter/tests and ownreports changed. DB/jobs/5008/consent/ACTIVE_PLAN/nativeSportsV3/Bmarket/Git untouched.

**Next:** independent review of this boundedpatch, then separatecachejoin/collectionstage. Native causalfitblocked by availability/classes/missingfeatures and unapproveddatasetdomain, not by absenceoforiginalpredrawsnapshot alone.
