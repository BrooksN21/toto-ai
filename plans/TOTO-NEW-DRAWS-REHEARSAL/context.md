# TOTO-NEW-DRAWS-REHEARSAL context

Collected 2026-07-27 from the standalone `/Users/turshevr/toto-ai` workspace only. No package generation, staging, commit, external memory, or Yandex systems were used; the bounded TotoBrief requests are recorded below.

## Scope and bounded network attempts

- Read `AGENTS.md`, all files in `memory-bank/`, and `plans/TOTO-DRYRUN-NEXT/context.md`.
- One bounded TotoBrief page-one request was attempted: `drawings --name baltbet-main --page 1`, with a 30-second subprocess bound. It failed after four attempts with `ConnectionError`.
- Three bounded exact detail requests were attempted for locally missing detail IDs `11975`, `11977`, and `11981`, each with a 20-second subprocess bound. All failed with the same TotoBrief `ConnectionError`. No further requests were made.
- No package-generation command was run.

## Exact local drawing inventory

SQLite: `/Users/turshevr/toto-ai/data/toto.db`. Result completeness means non-empty `events.result`; result snapshots are counted separately.

| visible | internal ID | status | ended_at | events | complete results | result snapshots | preparation row |
|---:|---:|---|---|---:|---:|---:|---|
| 4953 | 11972 | finished | `2026-07-23T15:30:00.000000Z` | 15 | 0/15 | 0 | `api-sports`, `unresolved`, mapped `0`, unresolved orders `0..14`, eligibility `unknown`, updated `2026-07-23T12:36:14.525862+00:00` |
| 4954 | 11975 | finished | `2026-07-24T15:30:00.000000Z` | 0 | 0 | 0 | none |
| 4955 | 11977 | finished | `2026-07-25T15:30:00.000000Z` | 0 | 0 | 0 | none |
| 4956 | 11981 | finished | `2026-07-26T14:30:00.000000Z` | 0 | 0 | 0 | none |
| 4957 | 11983 | active | `2026-07-27T15:00:00.000000Z` | 0 | 0 | 0 | none; not completed |

Additional counts for 4953+: drawing-event pins `0` for every drawing; external collection runs and dispositions `0`; archived package rows `0`; settlement rows `0`.

## Honest rehearsal availability

### 4953 / 11972 — limited pre-result rehearsal only

Stored pre-deadline inputs exist:

- `/Users/turshevr/toto-ai/data/raw/drawing_11972.json` and its metadata sidecar; `fetched_at=2026-07-23T12:35:24.704972+00:00`, before the `15:30Z` deadline. It contains all 15 TotoBrief events and no results.
- SQLite has 15 quote rows for 11972 (pool and BK probability triples); event rows have empty `result`/`score`.
- The failed preparation attempt left a pending review for event order 6 (`Флора — ТНС`, target event `178689`) and no authoritative pins. The best cached provider candidate was fixture `1589427`, `Flora Tallinn — The New Saints`, but it was not accepted.
- Some API-Sports cache files were fetched before the deadline, but there is no `external_collection_runs` row or complete 15-event frozen external-probability snapshot for 4953.

Therefore 4953 can honestly support only an input/preparation-boundary rehearsal from stored pre-deadline TotoBrief/pool/BK data (and inspection of cached provider evidence). It cannot support a full runner/package retrospective: no READY 15/15 preparation, no external collection manifest, no runner manifest, no package, and no result snapshot. Do not use final `drawings` summary values as if they were pre-deadline snapshots.

### 4954–4956 — blocked

No raw TotoBrief detail, event rows, quote rows, preparation, pins, external collection, runner manifest, package, or result snapshot is stored for any of these drawings. The current SQLite summary rows are insufficient to reconstruct an as-of-deadline input. Fetching current details now would be post-result and must not be used as an honest retrospective rehearsal input. These drawings are blocked until pre-deadline snapshots/cache are supplied or a new explicitly post-result investigation is authorized.

### Existing controls, not newly completed

The workspace has generated rehearsal/package artifacts for older drawings only:

- 4950: `/Users/turshevr/toto-ai/reports/drawing_run_4950_20260720T143000Z_e387daf42ce6.{json,md}` and `/Users/turshevr/toto-ai/reports/ev_package_4950_research_bank_4980.{csv,md}`.
- 4951: `reports/rehearsal/4951-early-run/` and `reports/rehearsal/4951-expanded-run/` contain runner manifests and EV packages.
- 4952: `reports/rehearsal/current-systematic-research-4952-20260722T105232Z/` and `reports/rehearsal/evening-4952/` contain runner manifests/packages; related raw/provider cache evidence is under `data/raw/drawing_11970*` and `data/external-cache/api-sports/runs/4952-*`.
- Package-audit artifacts exist under `reports/final-acceptance-4952/`, `reports/final-p2-acceptance-4952/`, and `reports/review*4952/`.
- The SQLite `archived_packages` and `package_settlements` tables are empty despite these report files; they are not newly completed-drawing archives.

No 4953–4956 runner manifest or generated package exists. No probability input for 4954–4956 exists locally.

## Interrupted TNS alias work / Git state

- `git diff` and `git diff --cached` are empty; no tracked source/config changes remain.
- Before this context file was created, `git status --short` showed only the pre-existing untracked `plans/` and `reports/` trees; no alias patch was staged or committed. The only new file from this task is this context file.
- Tracked `/Users/turshevr/toto-ai/data/external-odds/team-aliases.json` contains no Flora/TNS alias.
- SQLite has no Flora/TNS alias rows. `team_registry_reviews` row `id=4` for drawing 11972/order 6 remains `pending`; no resolution IDs/provenance are stored.
- Conclusion: the interrupted TNS alias work left no detectable working-tree alias patch. The blocker remains the pending reviewed identity plus missing authoritative 15/15 preparation.

## Bottom line

Among newly completed drawings, **4953 is the sole limited candidate**, suitable only for an honest pre-result input/preparation rehearsal, not a full retrospective package evaluation. **4954, 4955, and 4956 have no usable pre-deadline local evidence and are blocked**; using newly fetched details or current result data would leak post-result information. 4957 is still active and out of scope.
