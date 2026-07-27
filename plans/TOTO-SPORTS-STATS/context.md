# TotoAI sports-statistics handoff

Collected on 2026-07-27 from the standalone repository
`/Users/turshevr/toto-ai` only. Root `AGENTS.md` and every file in
`memory-bank/` were read. No Arcadia/Yandex/Gena/Startrek skills or external
project memory were used.

## Repository state

- Branch: `feature/initial-toto-ai`
- HEAD: `7ea5b22 Recover drawing lifecycle and fail-closed betting safety`
- The worktree is not clean.

Tracked modifications:

- `data/external-odds/team-aliases.json`
- `memory-bank/CURRENT_STATE.md`
- `memory-bank/DECISIONS.md`
- `src/toto_ai/cli.py`
- `src/toto_ai/db/models.py`
- `src/toto_ai/external_odds/preparation.py`
- `src/toto_ai/external_odds/team_registry.py`
- `src/toto_ai/operations/finished_draw.py`
- `tests/test_finished_lifecycle.py`
- `tests/test_team_resolution.py`

Relevant untracked source/test file:

- `tests/test_team_resolution_tns.py`

Other untracked material includes existing `plans/` handoffs and a large
`reports/` tree. These operational reports must not be accidentally included
in a source commit.

## Unfinished lifecycle work

### Cancelled/void event support

The uncommitted implementation adds explicit reviewed VOID handling to the
finished-drawing lifecycle:

- CLI `sync-finished-results` accepts repeatable `--void-event` values and one
  mandatory HTTP(S) `--void-source`.
- Current result snapshot schema changes from v2 to v3.
- A reviewed void event is stored as result `*`, `result_status = "void"`,
  empty score, and evidence URL.
- An empty API result without a reviewed override fails closed.
- A void override is rejected if the event already has a result or score.
- Settlement counts every coupon outcome at a void position as correct and
  excludes that position from fixed/zero-exposure miss diagnostics.
- Empty `void_event_orders` is removed from settlement hash input to preserve
  old non-void settlement hashes.
- Snapshot validation has separate legacy v1/v2 and current v3 rules.

Existing tests cover reviewed VOID sync, immutable stored evidence, settlement
as a hit, missing evidence rejection, and contradiction rejection. They do not
yet provide a direct CLI success/pass-through test for the new options, and
there is no explicit regression fixture proving that a pre-existing schema-v2
snapshot still verifies after the v3 change.

Current verification:

- Focused lifecycle/team-resolution suite: `63 passed`.
- `git diff --check`: passed.
- Focused Ruff: **failed** with `B008` at
  `src/toto_ai/cli.py:298` because the new list-valued
  `void_event = typer.Option(...)` default is treated as a function call in an
  argument default.
- No full-suite result exists for the current uncommitted state.
- `memory-bank/CURRENT_STATE.md` and `DECISIONS.md` document the reused-pin
  probability refresh but do not yet document VOID semantics.

### Reused-pin probability evidence refresh

The same uncommitted worktree also fixes stale TotoBrief probability evidence
when an exact ready 15-pin mapping is reused:

- the pins/fingerprint remain unchanged;
- only `probability_input_sha256`, `target_fetched_at`, and update time refresh;
- unrelated readiness evidence is preserved;
- updates are monotonic and compare-and-swap protected;
- older evidence is rejected;
- equal timestamp/same hash is idempotent;
- equal timestamp/different hash fails closed;
- malformed or non-normalized 15x3 probabilities fail before persistence.

Reviewed aliases for drawing 4957 were also added for `ТНС`, `Феникс Пилар`,
`Эстер`, and `Варберг`, with exact-match, similar-name rejection, and collision
tests.

## Existing API-Sports/external-data infrastructure

The project already has a substantial **external odds and identity** layer:

- `external_odds.api_sports.APISportsClient`:
  authenticated HTTP transport, sanitized errors, retry, quota reserve,
  safety cutoff, immutable cache, pagination, football/hockey base URLs;
- current public fetch methods:
  - `fetch_schedule()` using football `/fixtures` or hockey `/games`;
  - `fetch_event_markets()` using `/odds`;
- provider-neutral schedule/market records and protocol in
  `external_odds.domain`;
- TotoBrief target parsing, sport classification, team aliases/registry,
  conservative event matching, exact drawing pins, orientation handling,
  consensus probabilities, append-only collection storage, coverage audit,
  prospective collection, and morning/final revalidation.

This infrastructure currently collects identity, timing, schedule, and odds.
It does **not** implement sports statistics:

- no sports-statistics provider protocol;
- no completed-match/team-history fetch API;
- no standings, form, home/away split, rest, lineup, injury, xG, shots, or
  hockey-stat parsers;
- no immutable sports-statistics snapshot tables;
- no canonical football/hockey feature snapshots;
- no feature builder or sports probability model;
- no market/sports calibrated blend;
- no `collect-sports-stats`, `backfill-sports-stats`, or
  `build-probabilities` CLI commands.

The latest prospective external-odds audit in
`reports/rehearsal/4957-prospective-direct-20260727T0855Z` remains
`PENDING`: 6 drawings / 90 events versus the frozen minimum 30 drawings /
450 events. External consensus is therefore still diagnostic and has no PLAY
influence. That sample is for odds coverage, not proof that sports-statistics
features are useful.

## Roadmap status

The approved target is documented in
`plans/hybrid-package-program/plan.md`:

1. market probabilities remain prior/fallback;
2. morning collection freezes lawful pre-match sports evidence;
3. historical backfill must use identical canonical records and as-of rules;
4. football and hockey use separate schemas/models;
5. evening operation must succeed from the last eligible frozen snapshot or
   explicit market-only fallback without a mandatory last-minute request;
6. sports probabilities stay audit-only until chronological no-leakage,
   calibration, coverage, and no-degradation gates pass.

Roadmap Milestone 4 (sports-statistics acquisition and feature store) has not
started. Milestone 5 (calibrated probability blend) and Milestone 6 (hybrid
optimizer using that blend) are also future work. Current package profitability
is not proven.

## Exact next safe implementation slice

Do not start sports-statistics code on top of the current mixed, Ruff-failing
worktree.

First close one small lifecycle commit:

1. fix the `B008` CLI declaration without changing VOID semantics;
2. add a CLI success/pass-through regression for `--void-event` and
   `--void-source`;
3. add an explicit schema-v2 snapshot compatibility regression;
4. document reviewed VOID semantics in `CURRENT_STATE.md`, `DECISIONS.md`,
   and the roadmap;
5. run the full pytest suite, repository-wide Ruff, and `git diff --check`;
6. commit only source/tests/memory/alias changes, excluding operational
   `reports/` and unrelated untracked plans.

Immediately after that, the first sports-statistics slice should be
**provider-neutral, immutable, and audit-only**:

- define separate football/hockey canonical snapshot records plus a provider
  protocol;
- add additive append-only database tables binding drawing/event/provider,
  provider fixture/team IDs, `as_of`, `fetched_at`, source payload hash,
  freshness/missingness, and canonical feature JSON;
- implement deterministic validation/serialization and no-future-data tests;
- do not add network endpoints, models, blending, package selection, scheduler
  behavior, or PLAY influence in this first slice.

This isolates the data contract before API-Sports endpoint/quota assumptions
are introduced. The following slice can then add one lawful football adapter
for completed pre-target fixtures and standings, reusing the existing
transport/cache/identity boundary and preserving explicit market-only fallback.

## Lifecycle patch completion (2026-07-27)

The lifecycle prerequisite described above is now complete in the worktree:

- Ruff `B008` is handled for the repeatable Typer VOID option.
- `--void-event`/`--void-source` has a direct successful CLI regression.
- HTTP(S) evidence parsing requires a real scheme and host, rejects whitespace
  and credentials, and persists the normalized reviewed URL.
- A dedicated schema-v2 snapshot fixture verifies with the current v3 reader.
- VOID settlement and contradiction/fail-closed behavior remain covered.
- Reused-pin probability refresh still preserves unrelated readiness fields
  and retains monotonic compare-and-swap behavior.
- Focused verification: `65 passed in 5.66s`.
- Full verification: `1354 passed in 220.83s (0:03:40)`.
- Repository-wide Ruff: `All checks passed!`.
- `git diff --check`: passed.

No files were staged, committed, pushed, or published. The next isolated
implementation task may begin Milestone 4 with provider-neutral immutable
football/hockey sports-statistics snapshot contracts and no-future-data tests.

## Active-detail stale-cache race fix (2026-07-27)

A later preliminary run exposed one more operational blocker before sports
statistics could start. `sync-prepare` accepted the general TotoBrief detail
cache at about 1618 seconds old, wrote READY evidence for that old BK matrix,
and `run-drawing` then fetched current probabilities and correctly rejected
the mismatch.

The worktree now separates active preparation freshness from historical cache
retention:

- active `sync-prepare` and `prepare-drawing` cache evidence is capped at
  60 seconds;
- an older cache causes a coordinated exact-detail network refresh;
- refresh failure defers preparation and cannot fall back to the stale cache;
- a fresh unchanged probability matrix authorizes the existing exact pins;
- a true change after preparation still fails closed at runner preflight;
- the previous monotonic/CAS evidence refresh and unrelated readiness fields
  are preserved.

Regression tests reproduce the 1618-second stale cache followed by a fresh
runner probability input and separately cover refresh failure with stale cache
and a genuine subsequent probability change. No drawing number is hard-coded
in production behavior. Combined verification after this fix: focused
operational/probability tests `42 passed`; full suite
`1356 passed in 237.33s`; repository-wide Ruff and `git diff --check` passed.

## Sports-statistics replay hardening (2026-07-27)

The audit-only football slice is now implemented locally. The final review P1
was a request-key mismatch: prospective collection cached
`team/season/last=10`, while historical replay searched only for a bounded
`team/season/from/to` key.

The worktree now keeps bounded historical lookup but safely falls back to the
compatible frozen `last=N` key for the same team, season, completed-status
filter, and timezone. It accepts that entry only when its provider observation
time is at or before historical as-of, preserves the real cached request
fingerprint, reapplies strict completed/team/target/kickoff/as-of filtering
locally, and never enables network in historical mode. A newer compatible
cache is rejected.

An end-to-end regression performs a real prospective collection through the
API-Sports transport, disables network, replays historical-as-of from the same
cache, and verifies identical event features and byte-identical reports.
Repeated persistence returns the existing immutable snapshot only when all
semantic evidence is identical; differing evidence still conflicts.

Final verification after this fix: focused sports-stat/provider/collector
tests `38 passed`; full suite `1384 passed in 243.60s`; repository-wide Ruff
and `git diff --check` passed. Nothing is committed or published.
