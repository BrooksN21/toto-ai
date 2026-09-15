# Sports Analytics v3 — bounded model-readiness checkpoint

Observed at: `2026-09-04T23:35:25+03:00` (MSK).

Status: `RESEARCH ONLY — BASELINE HANDOFF REQUIRED — NO MODEL RUN`.

This checkpoint is limited to the already approved Sports Analytics v3/F3–F7
plan and its fair same-input replay contract. It does not start a new backlog,
does not review the separate operational/persistence change set, and does not
change production data, SQLite, scheduler, operator, drawing 4997, or any
wagering artifact.

## Exact next incomplete MODEL step

The next step is **F3 / plan P1: read-only Sports v3 coverage auditor**:

1. consume the explicit, validate-only frozen raw-history manifest for
   drawings 4990–4995;
2. convert its exact provider fixture/team identities and strictly pre-kickoff
   completed matches into the input contract of
   `build_sports_v3_feature_table`;
3. emit one deterministic 90-row source/feature coverage audit;
4. add explicit regressions for 4990 `SOURCE_REJECTED`/BK fallback and 4991
   all-missing/BK identity;
5. perform no fitting, probability blending, package generation, SQLite write,
   operational import, or network request.

This is not package optimizer `quality-v3`. F4/P2 (A0–A5 chronological
probability validation) follows only after P1. F5 and any new package research
follow only after the probability gate. F6 requires at least 30 prospective
drawings / 450 events. F7 requires authoritative payout evidence. The existing
four-package comparison (`quality-v2`, `sports-shadow`, `quality-v3`, `robust`)
is a separate same-input package replay and is not evidence that Sports
Analytics v3 exists or is profitable.

## Frozen instruction/evidence baseline

| Evidence | File SHA-256 |
|---|---|
| production `memory-bank/ACTIVE_PLAN.md` (updated `2026-09-04T23:20:24+03:00`) | `893d73de4c70179e7742bbb26c338365cd5dd2212736529ab56bd780f0750b1c` |
| archived F3–F7 checkpoint | `20116a609f62429441be5eb51d9818c11da06583cd92db95fcca100571aae24f` |
| recovery model plan | `5173cb909fef7e872d76e0c94d04fa9798abc682ff32d7977a147a1a2339ab5e` |
| recovery research baseline | `7f53aa052e16923a5dc91f6dd8ea52ef67599a693de74e0105589034746e5d0f` |
| recovery implementation report | `794bd85e92c070157a411c6b572e0bc18ea6c373fc076002b65b52dbb9f38d98` |

The saved evidence resolves the old 4990 choice: keep the fold in the
scoreboard with exact BK fallback and explicit `SOURCE_REJECTED`; do not repair
the deadline or synthesize history.

## Code baseline and readiness blocker

Production and this linked worktree both point at commit
`a17e0771e5ad1d3dc4990ce917b6135c8f7168f2`, but that commit is not the full
current production sports-history baseline.

| Path | production current SHA-256 | worktree SHA-256/state | Baseline status |
|---|---|---|---|
| `src/toto_ai/sports_stats/v3_features.py` | `90e6172afb5a0c982dd98be5015abac5f4f54a588eb8943798b75dc99bd96970` | same | committed/shared |
| `tests/test_sports_v3_feature_table.py` | `cab7af30ee8710d9346d48d0b7104b93269d9859a8417235e81e55ab16211d0f` | same | committed/shared |
| `src/toto_ai/sports_stats/storage.py` | `3342b6ab721180c5e3a96bc932f5e8c062a7ce0ccf53369e1a09df78a3a85478` | same | committed/shared |
| `src/toto_ai/sports_stats/domain.py` | `cdebd1a59f67240b3a3973fa5ba8d22b9ee48224515976e5808f9c1dc9bc07b8` | `98d9c5cd3161461ecbb889c0b9506127add16fc1a1484fabd671309fc7f365ea` | production tracked modification adds semantic persistence identity |
| `src/toto_ai/cli.py` | `5b11f3c9cc2ac9feaddc6f935150fcbc55eeffba3aefae48640f0b8f4e29f88c` | `64a128eca59cfbceea3b95ff0640d34b0056c22c16b82429bb3648ae3c261ab0` | production tracked modification wires the backfill CLI |
| `src/toto_ai/sports_stats/history_backfill.py` | `4117fff236aa9024471826b49ca7c8b929d4772a8bf96bc86e60f37c278aafd5` | missing | production untracked |
| `tests/test_sports_history_backfill.py` | `0d8ccb2b866307f4229ed86d20c860fe5eca6099f19e77da4f12a3047b504961` | missing | production untracked |
| exact 4990–4995 backfill manifest | see data baseline below | missing | production untracked |

The worktree copy of `scripts/project-git` resolves to the worktree root but
requires `.git` to be a normal directory, so it cannot attest this linked
worktree. It was not used to bypass the repository guard.

**Blocker:** the coverage auditor must not be implemented or evaluated against
the knowingly incomplete worktree baseline, and the dirty production files
must not be copied ad hoc. The review/integration owner must provide a
self-contained reviewed baseline containing the approved persistence contract
(or an explicitly approved replacement) before implementation starts. This
checkpoint does not duplicate that review.

## Hash-bound data baseline

- Manifest path (production read-only):
  `plans/TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904/backfill-4990-4995-manifest.json`.
- Manifest file SHA-256:
  `07463e8831c8e1cbcd146b9243555c2efce72a160b4c527c3243573ade270e49`.
- Manifest semantic SHA-256:
  `dd6151f61f4d3ab89a28eeea778fa0d02f7e96deb956ecb6c9742c076758ca77`.
- Validate-only audit JSON file SHA-256:
  `15cb3aa28683f5b9e7d01851efea036975ef393e3e22208f5a7f371a8643fee7`.
- Validate-only audit semantic SHA-256:
  `737db286938d5a46c4d683c29368ed398a49fb6f632816fae08a2ebbb6bc6ab1`.
- 90-event attribution aggregate semantic SHA-256:
  `94ab5d0641f23ba4a25f16830b4536cac4c4bdf8e916a83cc519ccf2e25a1189`.
- Aggregate file SHA-256 values: JSON
  `5fe2613249d2a911c8e1bbac0a0485669b993fcff1343a678d9723e5e7eec797`,
  CSV `9fdd79dc4984925e24421129510c172d14d8c714536f4393066d094d5626ccec`,
  Markdown
  `8998aa984e8f12bba059930c99984b3cdfa73a35360f6f67f3e56ca9f4d4a1c9`.

The manifest individually binds every raw GOAL response file. No raw bytes are
copied into this worktree by this checkpoint.

| Drawing | Final input SHA-256 | Schedule binding SHA-256 | Validated source disposition |
|---:|---|---|---|
| 4990 | `3b3421619963e653830167cce1f885230fcd0bf6927566db2152ebe08be00b52` | `846d2a0f9f5b7dc81f9ecba81a40fe519b13cb16953fe0970690c3e81748f7a5` | rejected: final-input deadline mismatch; 0 complete / 0 missing counted |
| 4991 | `1e5e7f87fa57890a52c25b73dbf67b157e3b4270c0321e374aaaf8b1e4358ab9` | `618dad25bb94e0c9a3da0b6d2465b0026fd62ce269e5d6c06c8e4755fb24478f` | validated: 0 complete / 15 missing; sources 0 available / 30 unavailable |
| 4992 | `0e6bbba33ee32e3c0c462cc324d361da9b192a865c9cae5c1075defbd63a1e8d` | `8ba35a53cfe6fa60977196fcf31070600adc0131d020f51c346c0104c2045ae8` | validated: 15 complete / 0 missing; sources 30 / 0 |
| 4993 | `81c892362d9bee025200b2b4d9b3145c24b4d26adf7d9ddaa2ac7ac06468274d` | `db554ad5ca0d6eefca1cbf728ac4c5d1bb996045528edce45169fca99b84d938` | validated: 11 complete / 4 missing; sources 22 / 8 |
| 4994 | `3a721619aaf69daab6e2e6f5b8e078f79bd7216aedc24b284449b619345ff119` | `f5114584165cfdaeb62e3c48f94f1e1c4bb3a0c8cd051a45508694b01e5b9670` | validated: 13 complete / 2 missing; sources 26 / 4 |
| 4995 | `4728899b757f5e75affdc0e2ed5b4bf26fbe1b9db88cc37dd34fe31cc801c1ff` | `f7d8d99a990a91c1b044ae52542b88c45e3e1d36d4d4e77ad8002d68908b18ed` | validated: 13 complete / 2 missing; sources 26 / 4 |

The aggregate baseline is descriptive only: Sports v2 versus BK over 90 events
has Brier delta `-0.001184388`, log-loss delta `-0.001702241`, ECE delta
`+0.026938554`, and top-correct `37/90` versus `38/90`. These values are not a
Sports v3 result and do not establish profitability.

## Exact P1 experiment contract after baseline handoff

Required inputs:

1. the reviewed code baseline and exact hashes above (or owner-approved
   replacement hashes recorded before execution);
2. the exact manifest and every path/hash it binds; no discovery, fuzzy team
   matching, reconstructed history, or database read;
3. `v3_features.py` with its predictor allowlist and semantic hash contract;
4. explicit audit parameters recorded before execution. The frozen history
   request size supports `rolling_window=10`; however,
   `minimum_prior_matches` has no saved production value in the plan. It must
   be fixed by the reviewed experiment specification rather than inferred from
   unit-test examples or selected after seeing coverage;
5. output only under a new worktree-local `reports/research/<run-id>/`, with
   `operator_compatible=false`, `automatic_wagering=false`, and
   `profitability_proven=false`.

The adapter must validate capture timestamps and `as_of` before handing flat
matches to `build_sports_v3_feature_table`, deduplicate identical fixture IDs
deterministically, reject conflicting duplicate fixture content, and preserve
per-event source disposition separately from feature non-null coverage. Target
and historical team identities must use the exact provider IDs. Actual target
results, scores, actual rank/draw, post-kickoff data, and post-result package
metrics are forbidden inputs.

Acceptance criteria are exactly the saved plan P1 gate:

- 90 rows for 4990–4995 and exactly 15 unique event orders per drawing;
- 4990 explicit `SOURCE_REJECTED` with exact BK fallback in later probability
  work; 4991 explicit all-missing negative control;
- source complete counts for 4991–4995 `0,15,11,13,13` and missing counts
  `15,0,4,2,2`;
- per-predictor non-null count/rate, prior/venue match-count distribution, and
  missing-reason counts, kept distinct from raw source availability;
- `leakage_violation_count=0`, `post_as_of_source_count=0`,
  `same_or_future_kickoff_history_count=0`, duplicate identity count `0`;
- identical semantic/output hashes on an identical rerun; a changed source byte
  or timestamp must change the bound hash or fail closed;
- no fitting and no activation review if full-feature coverage is below 70%.

The 4996 15-row extension remains separate and cannot be used to tune the P1
contract after its result is known. No automatic 500/1000 replay is authorized.

## Next concrete checkpoint

Wait for the review/integration owner to provide the self-contained reviewed
baseline and the predeclared `minimum_prior_matches` value. Then re-hash only
the handed-off files and implement the P1 coverage auditor with failing-first
4990/4991/determinism tests. Do not begin F4 probability fitting or any F5
package replay before P1 passes.
