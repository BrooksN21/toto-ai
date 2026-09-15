# Context handoff — TOTOAI-4998-PARALLEL-INTEGRATION-20260906

Collected 2026-09-06T11:21:23.512545+00:00; cwd `/Users/turshevr/toto-ai`. **Context only**, no code/jobs/authority/main-memory/VCS mutation, no model/test/forecast/replay/network/DB execution. Only this handoff is written. Current instruction authorizes a downstream integration/publication task; neither is performed by this context worker. Prior acceptance is reused, not re-reviewed. No live launchd/process claim: only saved job artifacts inspected.

## Current binding and operational priority
Plan `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json`: c1d243f5b6ca48f3, drawing4998/db12102, requested bank4980/stake30/capacity166. Identity fingerprint b3f20304ff03e14a5b252512c5e5b2f6b58e1b94e3d7b2b39f62c0589473cbb7. Primary quality-v2 is immutable for this integration. First16:30;17:00/17:30/17:40/17:50; final18:00;18:12;expiry18:20MSK, closure18:30MSK (UTC+3). Parallel18:00; canonical local watcher16:30,30s from saved memory, no idle-chat wakeup/heartbeat.
Latest ACTIVE_PLAN records O1/G1 local integration complete and NOT activated;183 O1 cases=167+16 separate runs; G1 119pass/3 declared benchmark deselections. New retrospective4997 result is explicitly research, not an archived forecast or live profitability proof. Do not reopen that experiment.

## Existing entry points and minimal technical seam (not an implementation plan)
- `/Users/turshevr/toto-ai/src/toto_ai/cli.py`: imports sidecar functions at~365; `run-final-goal-hybrid-sidecar` is the installed wrapper command. No need to run prepare/activate/preflight again.
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_sidecar.py`: `run_final_hybrid_sidecar`348–475 waits for plan-bound actionable primary PLAY; `_execute`589–693 exports exact primary, loads final-input next to source package, invokes comparison, and rejects recomputed BK coupons differing from exported primary. `_publish_parallel_selection`768–877 is the only companion promotion seam; validator923–970.
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_comparison.py`: `execute_final_hybrid_comparison`70–447 loads expected-plan final snapshot, same bank/stake/effective budget/provenance, unmodified quality-v2 baseline, sports-v2 rebased/fallback, uncertainty quality-v3 and robust. Lines188–219 already hold `candidate_union`, `combined_models`, `exposure_constraints`, `robust` plus frozen snapshot. **Smallest G1 data seam: after existing robust selection and before `_parallel_candidate`243–279/exact comparison/report generation**. All necessary model matrices/control-relative integer bounds and candidate coupons already exist here; avoid scheduler engine changes.
- G1 `/Users/turshevr/toto-ai/src/toto_ai/optimizer/exact_maximin_refinement.py`: `refine_maximin_package`386; `RefinementBinding`35 fields input/initial/universe/models/bounds SHA256, requested bank,stake,capacity,effective_budget; `RefinementLimits`50 defaults64swap evaluations/2accepted/5seconds. Initial must be within fixed candidate universe and exactly fill resolved capacity. `_validate`138–273 defines canonical sorting/hashes—use those exact contracts, not generic file SHA substitutions. Results preserve research/nonoperator flags; pass selected coupons through existing sidecar safety/selection/publication rather than editing those flags.
- A refinement of an existing challenger is technically smaller than adding a fifth strategy; **do not silently label a new algorithm as old robust**. Report G1 lineage/bindings/status/rollback separately and obtain downstream authorization compatibility disposition. A distinct G1 strategy needs candidate/report/path/ranking/release support and cannot currently be released under existing four-strategy authorization.
- Preserve G1 whole-run rollback and all-category/all-scenario non-degradation; catch integration/timeout failures locally and retain existing challenger/control. G1 uses cooperative checks around exact primitives, **not hard interruption**. An outer bounded worker/deadline and publication reserve are required for any promised hard deadline; defaults do not establish runtime safety for166coupons. No real runtime run here.

## Existing selector and authority interaction — concrete constraint
`/Users/turshevr/toto-ai/src/toto_ai/optimizer/parallel_challenger.py`146–240 requires exactly one eligible quality-v2 control and identical ordered model sets. Challengers must pass safety, BK P13/P14/P15 >=control (tolerance1e-12), max concentration <=control, strict worst-model P13 improvement. Tie order: worstP13,meanP13,worstP14,worstP15,packageSHA. No winner =>control. `_parallel_candidate`521–559 in comparison adds package safety/exact metrics; do not replace this with G1 self-claims.
Existing immutable parallel authorization explicitly lists **quality-v2,sports-shadow,quality-v3,robust**, policy `parallel-challenger-nondegradation-v1`. `_validate_parallel_authorization` requires that exact list and recordSHA; publisher path map only accepts those four. New `g1` ID is unsupported today. New owner wiring/push intent is not a license to rewrite/backdate this historical authorization or fake a matching hash; a supported explicit versioned authority route is a downstream decision if candidate identity/policy changes. No code hash is directly bound in current auth, but that does not permit hiding a material strategy change.
Primary auth binds plan/drawing/bank/stake, quality-v2 configSHA `12745b890f293f26eb856afe9ec5c93d57a856971976b7e69dc207892402c2b1`, selection-contextSHA `d7ebfba926adc119eb5e9db5ab2cdd28a1a8b999443c528d989a8d59b73e4de8`. Do not change plan/config to add parallel configuration. Parallel comparison/retry also binds full plan file SHA, final snapshot/probability identity, selected package bytes; any serialized plan change can invalidate current artifacts even if a plan_id string is retained.

## O1 honest readiness use
`/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_family_evidence.py:600` `assess_family_evidence(event:EvidenceBytes, verified_event_local_histories, reviewed_refs, cutoff_evidence, legacy_strict_scoped_eligible)` is **descriptive evidence annotation only**. Typed independently reviewed references and exact target/history bytes are required; self-consistent hash is not trust. Missing/rejected sources remain explicit, legacy eligibility is passed through. Never route readiness into F4/gates/probabilities/training or claim a trained Sports-v3 predictor. Minimal permitted use is a separate optional sidecar readiness/provenance report that cannot modify baseline, sports probabilities or eligibility and cannot delay primary. A correct current4998 O1 input adapter/reviewed-reference contract has not been established in this discovery; do not fabricate it from schedule review alone.
Installed sports artifact is still **Sports Analytics v2**, NOT_ACTIVATED/INSUFFICIENT_EVIDENCE, coverage0/15, fallback15/15. Existing comparison uses baseline when coverage=0. O1 adoption does not cure this or create a sports-v3 model.

## Primary-first publication and best-coupon ordering
`/Users/turshevr/toto-ai/src/toto_ai/runner/scheduler.py:3959–3969` atomically persists scheduler-owned operator-result BEFORE best-effort detached sidecar retry and `_write_ready_operator_delivery`. Retry exceptions are swallowed to preserve already durable primary. **Do not insert G1/O1/best-coupon scanning before primary atomic publication or make delivery await sidecar.** Primary ready file must be delivered first; later companion/best analysis is separately labelled.
Comparison349–372 and `_best_single_coupon_payload`636 compute `best_coupon_by_p13`, not first row. Sidecar `_selected_coupon_ranking`880–920 validates selected package position/coupon before publication. Status reader `/Users/turshevr/toto-ai/src/toto_ai/operations/scheduler_status.py:315–332` consumes bound `highest_p13_single_coupon`/selected strategy only. Ranking output must identify objective,probability/reference model,computed value,one-based position and package/input hashes. Do not present research coupons as upload; NO BET has no invented wagering file. Expired18:20 records never actionable.

## Frozen4998 data available for future offline/dry validation
- Installed seed `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/sports-seed/sports_probability_shadow_4998_08da2cb616e108b8.json`; fileSHA `9c2489b5cf65289227f6df794182fe71aa37f3b4ffb840c6111e8a1de1426fbd`, artifactSHA `08da2cb616e108b87b620ef5e4d2091c326174172b53524c975d4c23a05e632f`, original snapshot run `7e7bbdd815376fc6f9482032be34f3108b8122caff412ef7b34bf7ef34cfc71e`, as_of `2026-09-06T09:34:19.081148+00:00`. Other later seeds exist but wrapper remains pinned to08da2c; do not substitute a newer seed silently.
- Plan-bound copied reviewed ledger under `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/bindings/schedule-evidence-67ca1b2e8091005a/ledger.json`; schema/content validation remains existing project responsibility, not a new provider check.
- Preflight source files (existence only, not promoted to final input):
- `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/preflight/drawing-12102-20260906T153000Z-b3f20304ff03e14a/source-collector/conservative-cutoff.json`
- `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/preflight/drawing-12102-20260906T153000Z-b3f20304ff03e14a/source-collector/schedule-source-candidates.json`
- `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/preflight/drawing-12102-20260906T153000Z-b3f20304ff03e14a/source-consensus/schedule-consensus-promotion.json`
- `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/preflight/drawing-12102-20260906T153000Z-b3f20304ff03e14a/source-independent-consensus/independent-schedule-consensus.json`
- Current scheduler final-input matches: `[]`. `operator-result.json` present: False; sidecar-status present: False. Thus **no current scheduler-final frozen input for end-to-end sidecar replay is available at observation**. Use existing synthetic fixture builders for offline integration tests; any newly derived4998 research input must be explicitly labelled/nonoperator and validated against expected-plan contract, not masquerade as final input. No snapshot or package created here.

## Runtime/fallback controls (read code, no launches)
Existing wrapper: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/run-parallel-sidecar.sh`: waits900s,poll default5s, minimum-runtime240s. From18:00, stop waiting min18:15 / latest start18:16. Comparison deadline leaves5seconds before18:20. Pre-final warmup/refresh is nonterminal; late PLAY skips; NO BET may only research if valid final snapshot/time, never release. Retry478–577 validates exact plan/operator/status record and uses exclusive `parallel-sidecar-retry.json` marker, detached Popen; at most one claim for a bound ready record. Existing run output export collision also fails rather than overwrites. No evidence of a universal worker/process lock from this narrow read: do not assert stronger duplicate protection than these actual guards.
Saved project job artifacts (calendar evidence only, **not freshly verified loaded runtime**):
```json
[
  {
    "path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/totoai-scheduler.plist",
    "sha256": "5a4c791051f06bd8435b2a4cdd054173f5ff21a0e76adca94cbdbd3141391987",
    "Label": "com.totoai.production-scheduler.v9.c1d243f5b6ca48f3",
    "StartCalendarInterval": [
      {
        "Day": 6,
        "Hour": 16,
        "Minute": 30,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 17,
        "Minute": 0,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 17,
        "Minute": 30,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 17,
        "Minute": 40,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 17,
        "Minute": 50,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 18,
        "Minute": 0,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 18,
        "Minute": 12,
        "Month": 9,
        "Year": 2026
      },
      {
        "Day": 6,
        "Hour": 18,
        "Minute": 20,
        "Month": 9,
        "Year": 2026
      }
    ],
    "StandardOutPath": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/logs/scheduler.stdout.log",
    "StandardErrorPath": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/logs/scheduler.stderr.log"
  },
  {
    "path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/totoai-parallel-sidecar.plist",
    "sha256": "88be0e505f7a4ae3cfb604086593229780f1f619e85f0f6831023519f3441181",
    "Label": "com.totoai.parallel-sidecar.v1.c1d243f5b6ca48f3",
    "StartCalendarInterval": {
      "Day": 6,
      "Hour": 18,
      "Minute": 0,
      "Month": 9,
      "Year": 2026
    },
    "StandardOutPath": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/parallel-sidecar.stdout.log",
    "StandardErrorPath": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/parallel-sidecar.stderr.log"
  }
]
```
Existing primary/parallel/watcher should not be recreated. Main operations owns due16:30 check. No heartbeat or automatic wagering.

## Exact testing surface and accepted receipts
Existing pertinent tests: `/Users/turshevr/toto-ai/tests/test_exact_maximin_refinement.py`, `test_parallel_challenger.py`, `test_final_hybrid_sidecar.py`, `test_parallel_sidecar_retry.py`, `test_final_hybrid_settlement.py`, `test_scheduler_status.py`, `test_sports_v3_family_evidence.py` (all under same tests dir). Preserve immutable reviewer probes; use byte-identical temporary/local context. Main-only guarded synthetic pytest approach is saved in O1/G1 receipts; deny network/DB/out-of-temp writes. Future tests must cover primary-before-companion/ranking, unchanged baseline bytes, G1 timeout/rollback/malformed-binding fallback, four-strategy authorization rejection vs explicit extension, same-input budgets, exact selected hashes, nondegradation, no O1 eligibility promotion, T-10 and retry races. Run scoped current-main Ruff, no disables or config weakening. No tests rerun in context-only task.
```json
[
  {
    "path": "/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/G1_MAIN_INTEGRATION_RECEIPT_20260906.json",
    "sha256": "bbc7eee1ecbd59f8417a98dd2003623526a5fd3e62967397e435a2ede7c8c700",
    "phase": "APPLIED_VERIFIED_UNUSED_NO_ACTIVATION",
    "verification_summary": {
      "G1": "119 passed, 3 existing synthetic-size benchmarks deselected in 0.81s",
      "G1_Ruff": "3 files PASS under current-main full Ruff config: two exact new files and byte-identical temporary reviewer probe",
      "F3": "Only omitted 16 probes:16 passed in 0.43s",
      "O1_reconciliation": "167 earlier +16 now =183 covered; not claimed as a new single183 run",
      "safety": "Main-only project imports; no blocked actions; temporary harness removed; original probes unchanged."
    }
  },
  {
    "path": "/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/O1_IMPORT_ORDER_CLEANUP_RECEIPT_20260906.json",
    "sha256": "8a0227b5c25253d8a38e0c5321da607f37b00fd771778cdbcf9c0e344f5ab5d1",
    "phase": "COMPLETE_IMPORT_ONLY_VERIFIED"
  },
  {
    "path": "/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/LOCAL_ADOPTION_FINALIZATION_RECEIPT_20260906.md",
    "sha256": "f88916ea16c6af8bd23b6008cf5e274535945aff754a49a7167df74059e96159"
  },
  {
    "path": "/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/GOAL_PAGINATION_ADOPTION_RECEIPT_20260906.json",
    "sha256": "5ab4640d141ce2c8e1d5f39ce79c60aa14038cae2401529e428bb2878005c94f",
    "status": "APPLIED_VERIFIED_UNCOMMITTED"
  }
]
```

## Observed hashes for downstream handoff (not a publication manifest)
```json
{
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json": "946fc198cc232224d84bf79c9443079789f6c8a9897ba5a4fed8869c130614f9",
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/experimental-manual-release-authorization.json": "788b4bd358171a98909e7bd426228ed4e68fc8268db45c7a1984500a369900b1",
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/parallel-release-authorization.json": "470d9f82523b52dd98354d309990e9b4510481efd4f458f20f3f538158ec499e",
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/run-scheduler.sh": "38958adce9e5672328be98fe8209d3bd64021098be4ba70d74018c3a71a6c5db",
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/run-parallel-sidecar.sh": "12727d8a0cb15fb019856cf4b0dc1b25fa66efec76b2f19b53cda7e35e24bd6a",
  "/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/sports-seed/sports_probability_shadow_4998_08da2cb616e108b8.json": "9c2489b5cf65289227f6df794182fe71aa37f3b4ffb840c6111e8a1de1426fbd",
  "/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_comparison.py": "14d185004bca5844a6832d22c1208de8bca51deedbe3de5c537054a660488265",
  "/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_sidecar.py": "5a3113275282527cd248bab8a4267282ae88a90a9ca23053c0e5aad1873d787e",
  "/Users/turshevr/toto-ai/src/toto_ai/optimizer/parallel_challenger.py": "5b3cdea811c9d2a3acab09e54917c58bac63ae0c5f53ad3b4c5e8ee611bd6d5b",
  "/Users/turshevr/toto-ai/src/toto_ai/optimizer/exact_maximin_refinement.py": "b249971911e80d353ff719f0bd58e088c1ac4a183c4764ce32ed838147df62ee",
  "/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_family_evidence.py": "046c8543007429b7f26d0de4056b8f7fce7faa7a35b3f8f207e831cdb295d22b",
  "/Users/turshevr/toto-ai/src/toto_ai/operations/scheduler_status.py": "5c3bfb00238b00772febe36f055d28414e44c1ec08295f09dfc83668474f2956"
}
```

**Done:** bounded source/binding discovery; saved this context. **Remaining:** downstream scoped implementation/review + explicit authority-compatible release design + separate publication. **Concrete limits:** no final-input yet; new G1 strategy not in immutable authorization/path map; O1 is not predictor and no ready event-local reviewed input adapter established. **Next exact checkpoint:** parent consumes this file; do not refetch providers or repeat adoption/history. No background process owned.
