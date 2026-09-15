#17:30 release gate context — 2026-09-06T17:36:32.135461+03:00
Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. READ ONLY; no runtime/source/consent changes.

## Verdict
The17:30 NO BET is expected PRE_FINAL_CHECKPOINT behavior, not failed consent.
`quality_v2_real_money_release_gate_closed` is the default quality-v2 TRAINING/PAPER
result after a structurally valid candidate. Pre-final scheduler phases save usable
candidate bytes as LAST_KNOWN_GOOD_DEGRADED but explicitly actionable=false/NO BET.
The experimental manual override is consumed ONLY at scheduler_phase==final.
Therefore this reason ALONE does not block18:00 experimental PLAY. It does not
prove18:00success: neither exit0 nor saved LKG is an actionable release.

## Exact evidence / code paths
- Operator `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/operator-result.json`: decision NO BET, actionable=false,
  provenance PRE_FINAL_CHECKPOINT, LAST_KNOWN_GOOD_DEGRADED,166/4980. Reason
  `validated freshness_preflight package available before final refresh`.
- Scheduler state revision6: freshness_preflight complete17:31:56.715089MSK;
  error/failure_details absent; final/publish pending. Phase reason
  `quality_v2_real_money_release_gate_closed` is a release-gate outcome, not a process crash.
- Attempt `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/attempts/freshness_preflight-01-20260906T143003831993Z-79cb1142/fallback/reports/drawing_run_4998_20260906T153000Z_ac918f2f43e7.json`: decision NO BET, same terminal_reason, eligibility playable,
  exact selection_context `d7ebfba926adc119eb5e9db5ab2cdd28a1a8b999443c528d989a8d59b73e4de8`.
- `/Users/turshevr/toto-ai/src/toto_ai/ev/package.py:585-600`: valid paper candidate is deliberately
  returned with NO BET / gate-closed / STRUCTURAL_PASS / TRAINING/PAPER.
- `/Users/turshevr/toto-ai/src/toto_ai/runner/scheduler.py:2459-2495`: phase!=final persists LKG and
  writes PRE_FINAL_CHECKPOINT. Lines3551-3596: writer forces actionable=false/NO BET.
- Same scheduler lines6555-6628: paper candidate requires structural pass, pinned
  fresh revalidation, matching preflight/final fingerprints, playable effective
  eligibility, recomputed safety PLAY, validated rows/probabilities/bank. Only
  lines6591-6619 with scheduler_phase==final AND valid authorization return PLAY.
- Same scheduler lines3765-3807/3818-3839: native authorization validator and status.
  Read-only native `experimental_manual_release_status(load_scheduler_plan(...))`
  returned experimental_manual_authorized; checks recordSHA, exact plan/drawing/db,
  bank/stake, quality-v2 configSHA, selection contextSHA, expiry and pre-T-10 timestamp.

## Consent / boundaries
Consentfile SHA `788b4bd358171a98909e7bd426228ed4e68fc8268db45c7a1984500a369900b1`,
recordSHA `b9722aa6d382bdb03276a494575e8849bd3658cf227c00bc8cc59882f70013e1`; original authorized_at09:57:14.587305Z unchanged.
Plan c1d243f5b6ca48f3 /4998/db12102 /4980/30, expires18:20MSK.
Quality-v2 configSHA `12745b890f293f26eb856afe9ec5c93d57a856971976b7e69dc207892402c2b1`;
selection contextSHA `d7ebfba926adc119eb5e9db5ab2cdd28a1a8b999443c528d989a8d59b73e4de8`.
All8 protected hashes match saved G1 adoption baseline, including primary/parallel
consents, wrapper, plan, primary script/plists,seed. No consent rewrite needed/performed.

## Remaining actual conditions for possible final PLAY
1. Final phase really executes on fresh hash-bound4998 input, complete matched15/15,
   unchanged fixture fingerprint and valid schedule/eligibility/chronology.
2. Recomputed probability-bound selector/package safety must pass, candidate rows,
   provenance, structural checks and4980/30budget must validate. Consent does NOT
   override these checks or guarantee a profitable package.
3. Immutable exact authorization must remain valid. Final calculation/publication
   must finish inside scheduler deadlines including45s publication reserve before
  18:20MSK; closure18:30. Final phase targets18:00. Later data/runtime failure still
   fails closed; pre-final LKG alone must never become an upload recommendation.
4. Parallel companion additionally needs actionable scheduler control and its own
   same-final-input/consent/eligibility/nondegradation gates; not established by this read.

No final forecast/PLAY or all-healthy claim.17:40observation continues separately,
bounded to17:45; source/API/DB/retries/jobs/authority untouched. A harmless initial
inspection import used a nonexistent module path and failed before validation;
correct native scheduler import then passed authorization validation. No policy/code fix.

## File evidence SHA256 at context read
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json`: `946fc198cc232224d84bf79c9443079789f6c8a9897ba5a4fed8869c130614f9`
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/operator-result.json`: `3e8d1a95c22700dd9febaa0fa466535ffb73f4ea587c52a2c1d5e97dbe008a43`
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-state.json`: `1e3a5e5d4925937022f6b7f1115ae860dd801d7f6f424b213f3ec746279eead9`
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/experimental-manual-release-authorization.json`: `788b4bd358171a98909e7bd426228ed4e68fc8268db45c7a1984500a369900b1`
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/attempts/freshness_preflight-01-20260906T143003831993Z-79cb1142/fallback/reports/drawing_run_4998_20260906T153000Z_ac918f2f43e7.json`: `f4281dfd129a43661401dd0a4dd1a6efc1997d543434ecc1b4d6c64e1bb4eba0`
- `/Users/turshevr/toto-ai/src/toto_ai/runner/scheduler.py`: `07e23f28ebff084bc4e3fe13a3b185d201050ac983c64ce1be5ea0dc014848c4`
- `/Users/turshevr/toto-ai/src/toto_ai/ev/package.py`: `7f360752587e370e2b2e46592adfa650e0cebafc840aeff82cf503504a6357a9`
