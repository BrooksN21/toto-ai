# TOTO-CATCHUP-20260824 bounded context

Collected locally on 2026-08-24 using read-only SQLite queries and bounded
listings. No network, external service, test, source edit, commit, subagent, or
fresh `launchctl` query was used.

## Git

- HEAD: `1d8e6f707848e39093f4c26de5636f50fccd0abb`
- Status: `main...origin/main [ahead 1]`
- Untracked at observation time: `plans/TOTO-CATCHUP-20260824/` and
  `plans/TOTO-MORNING-TRAINING-20260820/`.

## SQLite drawings after 4981

The deadline below is the local `drawings.ended_at` value.

| Drawing | DB ID | DB status | Deadline UTC (MSK) | Events | Event results | Complete snapshot | Actual |
|---:|---:|---|---|---:|---:|---|---|
| 4982 | 12054 | finished | 2026-08-21 19:00 (22:00) | 15 | 15/15 | yes | `X211112211X2X21` |
| 4983 | 12057 | finished | 2026-08-22 17:00 (20:00) | 15 | 15/15 | yes | `2111XX21XX2XX22` |
| 4984 | 12060 | finished | 2026-08-23 16:00 (19:00) | 15 | 2/15 | no | `1......X.......` |
| 4985 | 12062 | active | 2026-08-24 19:30 (22:30) | 15 | 0/15 | no | `...............` |

Newest open drawing in SQLite: **4985**, DB ID `12062`, status `active`,
deadline `2026-08-24T19:30:00Z`. No drawing above 4985 was present.

`archived_packages` and `package_settlements` both contain zero rows for each
of drawings 4982-4985.

## Scheduler directories and artifacts

| Drawing | Scheduler directory | Plan/state | Operator result | Package | Post-draw |
|---:|---|---|---|---|---|
| 4982 | `reports/rehearsal/evening-4982-20260821T160000Z/` | plan `453829753fa55b5f`; terminal `failed` | absent; no markers | absent (lock only) | absent |
| 4982 | `reports/rehearsal/evening-4982-20260821T190000Z/` | plan `7dddf0c68bf09df1`; terminal `failed` | absent; no markers | training-only: `TRAINING_PAPER`, 166 coupons, 4,980 RUB, `STRUCTURAL_PASS`, non-actionable | absent |
| 4983 | none found | absent | absent | absent | absent |
| 4984 | none found | absent | absent | absent | absent |
| 4985 | none found | absent | absent | absent | absent |

Top-level `reports/package_4982.csv` and `reports/brief_4982.csv` exist outside
the scheduler directories and are not scheduler archives.

## LaunchAgent artifacts / last recorded status

No fresh system status query was made. Paths and labels come from project plist
artifacts. Runtime status is copied from the pre-existing partial context and
is therefore **not freshly verified**.

| Label | Project plist / program path | Last recorded status |
|---|---|---|
| `com.totoai.morning-dispatcher.v1` | `reports/rehearsal/morning-dispatcher-v2/totoai-morning-preanalysis.plist`; program `/Users/turshevr/toto-ai/reports/rehearsal/morning-dispatcher-v2/run-morning-preanalysis.sh` | loaded/enabled, not running, 54 runs, last exit 2 |
| same label, v3 candidate | `reports/rehearsal/morning-dispatcher-v3/totoai-morning-preanalysis.plist`; program `/Users/turshevr/toto-ai/reports/rehearsal/morning-dispatcher-v3/run-morning-preanalysis.sh`; `StartInterval=3600` | recorded as not installed |
| `com.totoai.production-scheduler.v6.453829753fa55b5f` | `reports/rehearsal/evening-4982-20260821T160000Z/totoai-scheduler.plist` | loaded, not running, 8 runs, last exit 0; scheduler state `failed` |
| `com.totoai.production-scheduler.v6.7dddf0c68bf09df1` | `reports/rehearsal/evening-4982-20260821T190000Z/totoai-scheduler.plist` | loaded, not running, 2 runs, last exit 2; scheduler state `failed` |
| `com.totoai.nightly-reconciliation.v1` | `reports/nightly-reconciliation/totoai-nightly-reconciliation.plist`; program `/Users/turshevr/toto-ai/reports/nightly-reconciliation/run-nightly-reconciliation.sh` | loaded, not running, 22 runs, last exit 2 |

No scheduler directory or LaunchAgent artifact for drawings 4983-4985 was
found in the bounded listings. No post-draw LaunchAgent for drawing 4982 was
recorded as loaded in the prior context.
