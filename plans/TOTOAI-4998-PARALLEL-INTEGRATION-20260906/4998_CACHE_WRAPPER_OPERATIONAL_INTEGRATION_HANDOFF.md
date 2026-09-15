#4998 operational integration — ENABLED16:35, after baseline preflight

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Existing plan
c1d243f5b6ca48f3, drawing4998/db12102, bank4980/stake30 unchanged.

## Timing and actual state

At16:26 deliberately deferred multi-file update rather than risk16:30 startup.
Primary16:30 TLS preflight completed16:30:16, launchd exit0; warmup/final calculation
NOT claimed. Code writes began only after primary stopped. Integration and
atomic saved-wrapper binding completed **16:35:21MSK**, not retroactively16:30.
All three jobs remain loaded on their existing calendars. Primary/parallel idle;
watcher running. Next primary checkpoint17:00; parallel/final18:00; expiry18:20;
closure18:30MSK. No schedule, LaunchAgent, plan or consent rewrite/reinstallation.

## Exact source and tests

Cachee914a097… + accepted wrapper-parser014ef057… applied to6 paths with exact
before/after hashes. CLI only cache2hunks composed over published G1/backfill;
combined SHA256fc7f04615930e8f2083b411ecb04a42e0f9504027f13cf817b6a789978e5b5dc.
GOAL quarantine/90min parser unchanged. No full isolated CLI/sidecar replacement.
64 targeted current-main tests PASS1.44s; Ruff5files PASS; native actual CLI help
PASS and advertises --g1-refinement. Wrapper reuse tests operated only on synthetic
copies; actual staging/saved-wrapper parser read-only validation PASS.

## Binding / preserved bytes

New seed: /Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/sports-seed/sports_probability_shadow_4998_ac04ea9b30359094.json
File SHA2562d5003c79378fb0b5f425ddf8cfdc0902327e727c0c0f3bb43843b43f2139e78;
artifactac04ea9b303590945dbdc3c12a451840d300350b641593f5cf07b74054d5f32e.
Native load PASS; reviewed corrected Sports-v2,14/15+1fallback, not trained Sports-v3.
Original capture/as_of unchanged; no provider refetch or probability recomputation.
New wrapper SHA25655488ab682ca35d5fcc145555471707c595bb2077c4266547cb5f98d137a2389.
Backup: /Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/4998-sidecar-wrapper-before-12727d8a0cb15fb0.sh
Old wrapper SHA25612727d8a0cb15fb019856cf4b0dc1b25fa66efec76b2f19b53cda7e35e24bd6a; old seed remains unchanged.
Atomic rename/fsync, existing mode retained; parser validates exact plan/root/seed
and G1=true. Native parallel authority validator PASS; both authority files and
all16 protected non-wrapper source/plan/job/seed/ledger paths unchanged.

Actual automatic retry launches [str(wrapper)], not a reconstructed default-off
command; it therefore retains this saved opt-in on an eligible later retry.
No real retry/sidecar/primary run performed. G1 still waits for primary delivery,
valid authority, same-input safety/non-degradation and runtime/deadline gates;
enabled does NOT mean attempted/improved/selected or operator PLAY.

## Production source-budget sanity

Automatic CLI callsite omits request_budget; ensure/default client budget120,
rolling retry allowance120. Config accepts120 and rejects121 without any request.
No mismatch/default>120 and no change to financial4980/30. The same client performs
schedule plus team-history queries(limit10); history does not create a fresh client
or reset its budget. Failed source caches are not reusable. Completed source/paper
cache is NOT a validated sports forecast: histories still need chronology/score/
eligibility checks; zero/partial validity remains fallback. This activation uses
the separately reviewed real14/15 seed, not cache readiness as probability evidence.

Receipt:4998_CACHE_WRAPPER_OPERATIONAL_INTEGRATION_RECEIPT.json includes exact
commands/source hashes, protected snapshots, authority hashes, loaded-job calendars,
CLI output, test import attestation and backup/binding times. No automatic wager,
research-packet publication, DB write by this integration or source collection.

DONE: integration + persisted future parallel opt-in. NEXT: parent17:00 checkpoint;
separate nonoperator comparison only from genuine supported frozen/BK input.
No final snapshot invented; no comparison run or PLAY claimed here. No owned process.
