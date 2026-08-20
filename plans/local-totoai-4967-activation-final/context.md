# Operational context — `local-totoai-4967-activation-final`

## Target identity

- Drawing ID: `12010`
- Visible number: `4967`
- Deadline: `2026-08-06T15:00:00Z` (`18:00 Europe/Moscow`)
- Fingerprint: `68e76b821ab4f5aada592ca90888850e910b4604c4015d1a446d73c265304323`
- Previous detail SHA-256: `4f14980deba6fa54cabb81f54b85947108ef07dc8e9c80122d45903868e38e70`

Previous dispatch was `deferred/drawing_not_playable`: preparation was READY `15/15`, but eligibility was `unknown`, with zero-based baseline-only orders `[1,8,13,14]`.

The ledger additions postdate that state and cover the corresponding visible events:

| Order | Event | Observation | Start UTC |
|---:|---:|---|---|
| 1 | 2 | `uefa-2049126` | `2026-08-06T16:00:00Z` |
| 8 | 9 | `uefa-2049165` | `2026-08-06T18:00:00Z` |
| 13 | 14 | `philadelphia-union-cruz-azul-leagues-cup-20260806` | `2026-08-07T00:00:00Z` |
| 14 | 15 | `austin-fc-club-tijuana-leagues-cup-20260806` | `2026-08-07T01:00:00Z` |

These starts span two Moscow calendar dates and should permit monotonic baseline-to-schedule-evidence enrichment.

## Morning-dispatch command

The snapshot does not disclose the authorized bank, secure env-file path, or the existing state/scheduler roots. They must be taken unchanged from the installed morning wrapper/current 4967 deployment; do not create replacement roots.

```bash
cd /Users/turshevr/toto-ai

python -m toto_ai.cli morning-dispatch \
  --bank "$AUTHORIZED_BANK" \
  --stake 30 \
  --env-file "$PROVISIONED_ENV_FILE" \
  --project-root /Users/turshevr/toto-ai \
  --state-root "$EXISTING_MORNING_STATE_ROOT" \
  --scheduler-root "$EXISTING_SCHEMA_V5_SCHEDULER_ROOT" \
  --schedule-evidence-ledger data/schedule-evidence/ledger.json \
  --expected-drawing-id 12010 \
  --expected-drawing-number 4967 \
  --expected-fingerprint 68e76b821ab4f5aada592ca90888850e910b4604c4015d1a446d73c265304323 \
  --expected-deadline 2026-08-06T15:00:00Z \
  --activate
```

Omit `--reviewed-schedule-catalog`: it is a different schema. `--activate` must occur exactly once.

Dispatch must complete its post-network timing check strictly before T−45:

- T−120: `13:00Z` / `16:00 MSK`
- T−90: `13:30Z` / `16:30 MSK`
- T−60: `14:00Z` / `17:00 MSK`
- **T−45 plan gate: `14:15Z` / `17:15 MSK`**
- T−30: `14:30Z` / `17:30 MSK`
- T−20: `14:40Z` / `17:40 MSK`
- T−16: `14:44Z` / `17:44 MSK`
- T−10 publication boundary: `14:50Z` / `17:50 MSK`

## Expected evidence paths

Known inputs:

- `/Users/turshevr/toto-ai/data/schedule-evidence/ledger.json`
- `/Users/turshevr/toto-ai/data/toto.db`
- `/Users/turshevr/toto-ai/data/raw/`
- `/Users/turshevr/toto-ai/data/totobrief-cache/request-state.json`
- `/Users/turshevr/toto-ai/data/external-cache/api-sports/`

Runtime evidence:

- Existing 4967 dispatch record beneath `$EXISTING_MORNING_STATE_ROOT`
- Generated schema-v5 plan, wrapper, plist, scheduler state, attempts and terminal evidence beneath `$EXISTING_SCHEMA_V5_SCHEDULER_ROOT`
- Installed plist:
  `~/Library/LaunchAgents/com.totoai.production-scheduler.v5.<plan_id>.plist`
- Terminal scheduler marker: exactly one of `.bet-ready`, `.no-bet`, `.failed`
- Actionable publication, when authorized: `package.csv` and `package-archive.json`

Exact generated basenames must come from the dispatch record/CLI output; they are not present in the snapshot.

## Verification checklist

### Before dispatch

- [ ] Current UTC time is strictly before `2026-08-06T14:15:00Z`.
- [ ] Secure env file is current-user-owned, regular, non-symlink, mode no broader than `0600`, with non-empty `API_SPORTS_KEY`.
- [ ] Existing state and scheduler roots match the roots that produced the supplied 4967 state.
- [ ] Ledger and referenced review-document hashes validate.
- [ ] No legacy reviewed-schedule catalog is substituted for the ledger.

### Dispatch result

- [ ] Fresh page-one/detail resolution matches ID `12010`, number `4967`, deadline and fingerprint exactly.
- [ ] Preparation remains READY with `mapped_count=15`.
- [ ] `external_coverage_count` advances `11 → 15`.
- [ ] `baseline_only_event_orders` becomes empty.
- [ ] Eligibility becomes `playable` with a two-day Moscow span.
- [ ] Selected schedule-evidence pins bind one non-null canonical ledger/reviewed hash.
- [ ] State advances from `deferred/not_requested` to generated and activated, with non-null `plan_id`, `plan_path`, label and plist path.
- [ ] Plan is schema v5 and binds publication lead `10` plus offsets `120/90/60/45/30/20/16/10`.
- [ ] Label is exactly `com.totoai.production-scheduler.v5.<plan_id>`.
- [ ] Generated plan, wrapper and plist verify byte-for-byte before activation.
- [ ] Installed plist contains no credentials and uses `/Users/turshevr/toto-ai` as `WorkingDirectory`.
- [ ] `launchctl print gui/501/com.totoai.production-scheduler.v5.<plan_id>` reports the exact job loaded.

### Safety and later scheduler evidence

- [ ] Morning dispatch itself creates no package, coupon or terminal marker.
- [ ] Production `scheduler-execute` uses the generated `--plan` without `--run-id`, `--simulate`, or `--dry-run`.
- [ ] Diagnostic stages cannot authorize PLAY.
- [ ] Final execution requires a fresh TLS-verified TotoBrief detail snapshot.
- [ ] `.bet-ready` appears only after durable package/archive verification and no later than T−10.
- [ ] Any fail-closed outcome is coupon-free and records `.no-bet` or `.failed`.
- [ ] No automatic upload or bet placement occurs.