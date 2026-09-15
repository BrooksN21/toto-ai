# Drawing 4999 / DB12106 — timing context (read-only)

Task: TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Source observations on 2026-09-06; current source facts are not historical review authority. No DB/ledger/code/jobs/memory/consent changes. Exact source paths/hashes and constraints are in the JSON companion.

## Concrete result

One fresh TotoBrief request succeeded at 17:49:21 UTC (20:49:21 MSK), with no retries: active drawing 4999 / id12106. Native BaltBet timestamp interpretation confirms **7 September 17:30 MSK = 14:30 UTC**. Raw `ended_at=2026-09-07T17:30:00.000000Z` uses the existing source-specific Moscow wall-clock convention; do NOT parse it as a conventional UTC close or shift closing to20:30MSK. This is TotoBrief revalidation, not direct BaltBet-site verification.

|Position/order|Exact fixture / senior competition context|Source-local date/time|UTC / MSK|Finding|
|---|---|---|---|---|
|9 /8|Floriana FC–Valletta FC, BOV Super Cup|7 September 19:00 Europe/Malta|17:00 UTC / **20:00 MSK**|MFA and club agree; saved Sofascore16:00UTC differs by1h. Conflict must be explicitly reviewed.|
|12 /11|Al Khaleej (Saihat)–Al Riyadh, Roshn Saudi League|7 September18:30 Asia/Riyadh|15:30 UTC / **18:30 MSK**|Saved GOAL+Sofascore and FotMob agree. Exact official kickoff not located; valid existing two-independent-source review route remains possible.|
|14 /13|FK Vozdovac–FK TSC (Backa Topola), Prva Liga Srbije|7 September18:00 Europe/Belgrade|16:00 UTC / **19:00 MSK**|Official FSS current-season fixture found. Local collectors had no match; reviewed target binding still required.|

Timezone conversions use IANA Europe/Malta / Europe/Belgrade (UTC+2 on this date), Asia/Riyadh and Europe/Moscow (UTC+3). European pages print local civil times without an explicit offset; this basis is recorded, not presented as an explicit source UTC field.

## Exact public evidence

- Malta: [MFA announcement](https://www.mfa.com.mt/news/competitions/tickets-out-now-for-40th-bov-super-cup-final/), [official match53208465](https://matchcentre.mfa.com.mt/match/53208465), [Valletta tickets](https://vallettafc.mt/buy-tickets/). Match-centre lineup availability16:00 is not kickoff. [MFA tickets](https://tickets.mfa.com.mt/?club-id=hmr) lists YouthU21/Women separately from this senior Super Cup.
- Saudi: [official senior club identity](https://www.spl.com.sa/en/teams/al-khaleej/index), [Sofascore16629480](https://www.sofascore.com/football/match/al-riyadh-al-khaleej/DUqbsNlrb#id:16629480), [FotMob15:30UTC](https://www.fotmob.com/en-GB/matches/al-khaleej-vs-al-riyadh/86y6czbp). SPL match84371 is an old2025/26 fixture and was rejected as current evidence. Ticket marketplace corroboration is not official authority.
- Serbia: [FSS2026/27 schedule](https://fss.rs/takmicenje/mozzart-bet-prva-liga-srbije-26-27/), [secondary club schedule](https://utakmice.rs/tim/fk-vozdovac). TSC/BackaTopola is a club-identity link, not a fabricated provider fixture ID.

TotoBrief gender/squad/age fields are absent for all3 rows. Official senior competition context and explicitly separated youth/women competitions support disambiguation, but this report does not mint `scope_verified`, reviewed team IDs, or stronger demographic authority than the sources provide. No reserve/youth substitution is authorized.

## Remaining evidence/operational boundary

The existing queue accepts either official+independent or independent+independent HTTPS claims, with exact team/start agreement, fresh captured snapshots/SHA256 and a real reviewer. An official source is therefore not universally mandatory. Public pages located in this context job are NOT yet immutable ledger snapshots or prepared review files. Position9 has a real contradiction; position12 needs qualified two-source review; position14 needs reviewed TSC mapping and second-source acceptance. No record was imported.

Saved preparation is15mapped/12external, timing_unknown3, non-playable, without a scheduler plan. An existing passive retry plan already intends `activate_evening=true`, hard stop7September16:30MSK; do not duplicate it. API-Sports suspended/date-plan errors in saved collection remain an independent real-preflight risk, not cured by knowing kickoffs. No account workaround is proposed.

## Supported next commands — NOT EXECUTED

All future shell cwd must be `/Users/turshevr/toto-ai`. The JSON will carry checked command templates and exact prerequisites; review-file/hash and actual new plan path are intentionally unfilled, not invented. Existing 4998 authorization must not be reused for4999. No experimental-release authorization is requested or created by this job.

### Checked command templates

Placeholders mean genuine missing prerequisites, not executable invented paths. Commands below are future operational instructions only; none were run. Existing retry must be reconciled before any manual dispatch.

**1. Validate each genuine prepared review without ledger mutation**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli schedule-evidence-review --review '<PREPARED_REVIEW_UNDER_LEDGER_DIR>' --review-sha256 '<EXACT_REVIEW_FILE_SHA256>' --ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json
```

Authorized evidence job must preserve two original source snapshots, SHA256, true captured_at and subsequent real reviewer/reviewed_at, exact target fingerprint/event order/teams/start. Prepared review must be under the ledger directory. This context report is not that file. No snapshot/review authority is fabricated.


**2. Import only after successful dry-run and explicit evidence-operation scope; once per prepared review**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli schedule-evidence-review --review '<PREPARED_REVIEW_UNDER_LEDGER_DIR>' --review-sha256 '<EXACT_REVIEW_FILE_SHA256>' --ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json --apply
```

Evidence ledger; NOT executed here


**3. Verify ledger/review/snapshot integrity**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli schedule-evidence-verify --ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json
```


**4. Preferred existing guarded preparation route, without scheduler activation**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli morning-dispatch --bank 4980 --stake 30 --env-file /Users/turshevr/toto-ai/.env --project-root /Users/turshevr/toto-ai --state-root /Users/turshevr/toto-ai/data/scheduler/morning-dispatch --scheduler-root /Users/turshevr/toto-ai/reports/rehearsal --db /Users/turshevr/toto-ai/data/toto.db --aliases /Users/turshevr/toto-ai/data/external-odds/team-aliases.json --schedule-evidence-ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json --expected-drawing-id 12106 --expected-drawing-number 4999 --expected-fingerprint b2596e1df489092abf5281c2f187ef3fa24b531b99136dbea99e7bdcad8a1b1d --expected-deadline 2026-09-07T14:30:00Z --python-executable /Users/turshevr/toto-ai/.venv/bin/python
```

Preparation may perform network/DB/cache/state writes. Future operational owner only. Reconcile existing passive retry before running, do not execute concurrently or copy hidden retry-child flag. Existing retry has GOAL/parallel research options; preserve or explicitly review these with owner, rather than silently changing its config. Bank/stake copied as preparation settings, not new consent.


**5. Same guarded route with scheduler activation after readiness/identity checks**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli morning-dispatch --bank 4980 --stake 30 --env-file /Users/turshevr/toto-ai/.env --project-root /Users/turshevr/toto-ai --state-root /Users/turshevr/toto-ai/data/scheduler/morning-dispatch --scheduler-root /Users/turshevr/toto-ai/reports/rehearsal --db /Users/turshevr/toto-ai/data/toto.db --aliases /Users/turshevr/toto-ai/data/external-odds/team-aliases.json --schedule-evidence-ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json --expected-drawing-id 12106 --expected-drawing-number 4999 --expected-fingerprint b2596e1df489092abf5281c2f187ef3fa24b531b99136dbea99e7bdcad8a1b1d --expected-deadline 2026-09-07T14:30:00Z --python-executable /Users/turshevr/toto-ai/.venv/bin/python --activate
```

Only after evidence and real preparation are valid; existing retry already has activate_evening intent, so avoid duplicate/manual parallel plan. No parallel-release-auto: no authorization may be minted by this job.


**alternative preview. Native scheduler-plan no-write preview only; NOT an additional plan to create alongside morning-dispatch**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli scheduler-plan --drawing 4999 --drawing-id 12106 --ended-at 2026-09-07T14:30:00Z --operational-cutoff 2026-09-07T14:30:00Z --bank 4980 --stake 30 --output-dir '<NEW_4999_PLAN_ROOT>' --project-root /Users/turshevr/toto-ai --schedule-evidence-ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json --env-file /Users/turshevr/toto-ai/.env --python-executable /Users/turshevr/toto-ai/.venv/bin/python --dry-run
```

Without --dry-run this command creates plan/wrapper/plist but does not load it. Inspect native generated slot times; do not copy 4998 slot schedule to4999.


**6. Real exact-target preflight on actual generated plan, not a dry-run**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli scheduler-preflight-only --plan '<ACTUAL_4999_SCHEDULER_PLAN_PATH>'
```

Runs source-backed preflight; no training/packages. May load intended API credential internally and write operational state; future authorized job only. Saved API-Sports suspension/quota capability is a separate blocker; no account workaround.


**7. Read-only plan-bound status**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli scheduler-status --plan '<ACTUAL_4999_SCHEDULER_PLAN_PATH>'
```


**8. Supported plan-bound watcher foreground command; creates its own status outputs, not scheduler authority**

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli scheduler-status-watch --plan '<ACTUAL_4999_SCHEDULER_PLAN_PATH>' --latest '<ACTUAL_4999_PLAN_ROOT>/status-watch/latest.json' --history '<ACTUAL_4999_PLAN_ROOT>/status-watch/history.jsonl' --interval-seconds 30
```

Persistent LaunchAgent setup is not done by this CLI. No watcher creation/activation command was found in the bounded project script/CLI inspection; scheduler activation helper accepts only exact generated scheduler plists and MUST NOT be reused for watcher labels. Future owner must prepare/verify a new4999 plan-bound watcher plist (not edit/reuse4998 label/paths), then explicitly install/start it under the approved operations scope. Existing4998 plist is a structural example only. Local files/stdout cannot wake an idle Codex chat.


### Watcher activation boundary

No actual4999 plan/path/id/plist exists in saved target registry, so an exact installable label/path cannot honestly be filled in yet. Do not claim activation. macOS launchctl bootstrap/kickstart is a later explicit native-OS operation on the verified new plist, not a discovered project watcher installer. The existing watcher plist has RunAtLoad=false; bootstrap alone must not be represented as a running observer. Do not copy its historical4998 dates/plan/label. A new reviewed plan-bound watcher may use the supported foreground command above; persistent installation/start requires a separate explicit operational step.

### Completion

Only this MD and JSON were written. No code/DB/ledger/plan/watcher/shared-memory changes, tests, package generation, consent or publication. One new TotoBrief GET succeeded with zero retries; no further sports API collection. Public evidence observed now is not backdated. Next checkpoint: Operational owner: inspect this three-row evidence result, resolve Malta1h conflict and complete real two-source reviews; then reconcile existing retry and run guarded preparation/real preflight. Context collector stops here.
