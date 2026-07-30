# TotoAI

TotoAI provides a small Python client and CLI for the TotoBrief community API.

## Installation

```bash
python -m pip install -e ".[dev]"
```

## CLI

```bash
toto-ai supported
toto-ai drawings --name baltbet-main --page 1
toto-ai info 12345
```

## Python

```python
from toto_ai.api.client import TotoBriefClient

client = TotoBriefClient()
print(client.supported_drawings())
print(client.drawings(name="baltbet-main", page=1))
print(client.drawing_info(12345))
```

## Development

```bash
python -m pytest
python -m ruff check .
```

## Morning Synchronization and Preparation

Use one command to refresh TotoBrief page-one metadata, synchronize the exact
open drawing, and prepare the API-Sports fixture/team/time pins:

```bash
set -a
source .env
set +a
.venv/bin/python -m toto_ai.cli sync-prepare \
  --open \
  --db data/toto.db \
  --aliases data/external-odds/team-aliases.json \
  --raw-cache-dir data/raw \
  --totobrief-rate-state data/totobrief-cache/request-state.json
```

The TotoBrief client coordinates requests across CLI processes through the
project-local state file, waits at least two seconds between attempts, honors
`Retry-After` (including a final exhausted `429`), and retries bounded
`429`/temporary `5xx` and transport failures. Page-one status changes are
committed before drawing detail is requested, and the open candidate is chosen
only from that fresh page-one response. A fresh exact drawing cache is reused
only when its mandatory sidecar, payload hash, identity, 12-hour freshness,
and complete 15-event/quote structure all validate. Preparation therefore
does not immediately issue the same detail request again. Progress reports
waits, retries, cache provenance, and deferred status.

The command fails closed with exit code `2` when exact drawing detail is not
available or preparation is unresolved. `start_at = null` remains null in the
TotoBrief data; the existing bounded API-Sports date expansion supplies
preparation evidence rather than inventing a start time. For deterministic
testing or replay, pass `--schedule-cache`; otherwise `API_SPORTS_KEY` must be
present in the environment.

To synchronize and diagnose TotoBrief without calling API-Sports or writing
preparation/pins, use:

```bash
.venv/bin/python -m toto_ai.cli sync-prepare \
  --open \
  --sync-only \
  --db data/toto.db \
  --raw-cache-dir data/raw \
  --totobrief-rate-state data/totobrief-cache/request-state.json
```

The full `sync-prepare` path writes preparation and pins only after fresh
page-one selection, exact detail identity/status/deadline validation, complete
15-event cache validation, and successful API-Sports resolution. Schedule
dates are loaded incrementally and resolution is evaluated without publishing
after each successful date. Once all 15 events resolve uniquely within the
normal playable two-day timing rule, later dates are not requested. If the
configured horizon is still needed, any attempted date failure before readiness
keeps the run fail-closed. Country context uses stable Russian/English/ISO
identities rather than drawing-specific aliases. Any failed gate exits closed.
An explicit operational `prepare-drawing --target-cache`
must be the canonical `drawing_<id>.json` file, must have its valid sidecar,
requires `--drawing-id`, and must match an already synchronized playable local
drawing; sidecar-free fixtures are accepted only by the explicit
non-production `run-drawing --offline-replay` workflow.

After a successful morning run, `prepare-drawing --open` uses the synchronized
local drawing and exact validated cache by default and makes no TotoBrief
detail request. Use `--refresh-totobrief` only for an explicit remote refresh.

For a one-off operator run, synchronization may still be bound to an expected
visible drawing number. The guard is checked against the freshly fetched
TotoBrief page-one candidate before any detail request, API-Sports preparation,
or pin write:

```bash
.venv/bin/python -m toto_ai.cli sync-prepare \
  --open \
  --expected-drawing-number 4953
```

## Generated Scheduler Artifacts

`scheduler-plan` can generate the evening wrapper and LaunchAgent candidate
without installing either one. When `--env-file` is supplied, it must be a
regular non-symlink file owned by the current user with permissions no broader
than `0600`. The generated wrapper repeats those checks at runtime, requires a
non-empty `API_SPORTS_KEY`, uses `umask 077`, and never prints or embeds the
secret. The plist contains only the wrapper path. Current schema-v4 candidates
contain five exact local triggers at T−45, T−30, T−20, T−16, and the T−12
publication cutoff. Generation still does not install or load the LaunchAgent,
and no command uploads or places a bet.

```bash
.venv/bin/python -m toto_ai.cli scheduler-plan \
  --drawing 4952 \
  --drawing-id 11970 \
  --ended-at 2026-07-22T16:00:00Z \
  --bank 4980 \
  --stake 30 \
  --min-gross-ev 1.0 \
  --env-file /Users/turshevr/toto-ai/.env \
  --output-dir /Users/turshevr/toto-ai/reports/rehearsal/evening-4952
```

The generated scheduler command passes the configured `--min-gross-ev` to
`run-drawing`; the CLI validates the same finite threshold and preserves the
existing default of `1.0`.

`morning-preanalysis-plan` now generates one generic non-betting dispatcher
wrapper and plist under `reports/rehearsal`. The recurring artifact contains
no drawing identity. At each configured time it resolves exactly one fresh
current drawing, prepares it, and—only when it is ready 15/15, playable, and
still before T−45—creates one exact schema-v4 evening scheduler pinned to its
visible number, internal ID, deadline, and fingerprint. Repeated morning runs
reuse the same per-drawing plan, including when one allowed two-day drawing is
still active the next morning; unresolved preparation may retry. Generated
state is persisted before activation, and a bootstrap retry verifies and
reuses the exact plan/wrapper/plist bytes rather than overwriting them.
Ambiguous selection, no drawing, multi-day or greater-than-five-day timing,
and late dispatch all fail closed. No code uploads coupons or places a bet.

Generation of the generic morning candidate itself does not install or load
launchd. The generated wrapper is also **passive by default**: it performs
morning synchronization/preparation and may generate an exact evening plan,
but it does not install that evening plan. `--activate-evening` is an explicit
post-drill opt-in:

```bash
.venv/bin/python -m toto_ai.cli morning-preanalysis-plan \
  --env-file /Users/turshevr/toto-ai/.env \
  --bank 4980 \
  --stake 30 \
  --at 08:00 \
  --at 10:30 \
  --retry-count 2 \
  --retry-delay-seconds 60 \
  --project-root /Users/turshevr/toto-ai \
  --output-dir /Users/turshevr/toto-ai/reports/rehearsal/morning-dispatcher
```

Do not add `--activate-evening` until an activation-disabled live 15/15 drill
has passed. Passive installation can collect operational evidence without
creating an actionable evening job.

### One-time stale LaunchAgent cleanup

Migration status on 2026-07-28: the five known obsolete jobs below were
booted out and their plist files were removed. A follow-up inspection found no
installed or loaded `com.totoai.*` LaunchAgent. On 2026-07-29 the passive
generic morning dispatcher was installed as
`com.totoai.morning-dispatcher.v1` for 08:00 and 10:30 Moscow time. Its wrapper
contains neither `--activate` nor a drawing number. The atomic evening
scheduler remains **not installed**. The
activation-disabled 4958 drill correctly deferred because one women fixture
was absent from API-Sports; no plan or package was created.

Production schema-v4 execution is always a short-lived idempotent tick.
`scheduler-execute --run-id` is supported only with `--simulate`; production
use is rejected rather than entering the incompatible legacy long-running
path.

The code does not perform this migration automatically. If the obsolete jobs
reappear on another machine, inspect and remove only these exact labels. These
commands are documentation; they are not executed by tests or artifact
generation:

```bash
for label in \
  com.totoai.morning-preanalysis.4953 \
  com.totoai.production-scheduler.a28e7c2c9c77683e \
  com.totoai.production-scheduler.df543a668bb7557a \
  com.totoai.run-drawing-4947 \
  com.totoai.run-drawing-4950
do
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
```

Unknown `com.totoai.*` jobs must be reported and reviewed, never deleted by a
wildcard cleanup.

## Deterministic Offline Drawing Replay

`run-drawing --offline-replay` replays one exact saved target and provider
schedule through the production preparation, pinning, schedule revalidation,
runner, and manifest-v4 path without reading `API_SPORTS_KEY` or constructing
network clients. The replay clock is supplied explicitly, and both cache
payload hashes and exact drawing identity are validated before work begins.
An explicit `--replay-root` is mandatory. Replay SQLite, reports, provider
cache, and temporary artifacts are derived beneath it; live defaults are never
inherited. Roots that overlap the repository root, `data/`, `reports/`, cache,
or scheduler-marker state, and roots traversing symlinks, fail before writes.

The sanitized drawing-4951 fixture can be replayed with:

```bash
python -m toto_ai.cli run-drawing \
  --offline-replay \
  --drawing-id 11968 \
  --target-cache tests/fixtures/drawing_4951_totobrief_target_cache.json \
  --schedule-cache tests/fixtures/drawing_4951_api_sports_schedule.json \
  --replay-as-of 2026-07-21T15:41:00+00:00 \
  --replay-root /private/tmp/toto-4951-replay \
  --mode research \
  --bank 4980
```

The manifest is written as
`/private/tmp/toto-4951-replay/reports/drawing_run_4951_20260721T160000Z_7d6517bbfe6d.json`.
Offline replay is always `RESEARCH ONLY`, writes no production EV package, and
does not create scheduler markers. If a replay manifest is supplied to the
scheduler, execution records an explicit non-production `ignored` status and
creates no `.bet-ready`, `.no-bet`, `.failed`, or replacement marker. `--open`,
playable mode, timing overrides, naive timestamps, stale schedules, changed
hashes, cross-drawing caches, and output overrides outside the replay root fail
closed.

## Expected-Value Package Workflow

Verify the complete 15-event EV surface before using the operational commands:

```bash
python -m toto_ai.cli benchmark-ev --events 15 --samples 20
```

Build a research package from the next playable TotoBrief drawing:

```bash
python -m toto_ai.cli ev-package --open --mode research --bank 6000 --stake 30
```

Build a playable package only when the modeled gross-EV threshold is met:

```bash
python -m toto_ai.cli ev-package --open --mode playable --bank 6000 --stake 30 --min-gross-ev 1.0
```

`backtest-ev` requires an existing frozen experiment manifest and does not
create one automatically. Before the first backtest, freeze the drawing IDs,
protocol, data hashes, and code version into a manifest:

```bash
python -m toto_ai.cli freeze-strategy-experiment --db data/toto.db --last 500 --holdout 150 --output reports/my_frozen_strategy_manifest.json
```

Then run the chronological modeled-EV backtest with that exact manifest path:

```bash
python -m toto_ai.cli backtest-ev --db data/toto.db --last 100 --banks 4800,6000,9600 --thresholds 0.90,0.95,1.00,1.05 --frozen-manifest reports/my_frozen_strategy_manifest.json
```

The bank can be any positive multiple of the configured stake. Research mode
always returns a comparison package; Playable mode can return `NO BET` and does
not lower the threshold to spend the bank. A `PLAY` decision is model output,
not a profit guarantee. The prize-fund proxy, independent-event crowd model,
and resulting modeled ROI remain experimental and require prospective payout
validation.

Audit any complete 15-event package without changing its coupons:

```bash
python -m toto_ai.cli package-audit \
  --package reports/my_package.csv \
  --strategy ev \
  --bank 6000 \
  --effective-bank 4980 \
  --stake 30
```

The command writes deterministic schema-v1 JSON, event-exposure CSV, and
Markdown. It reports canonical package/audit SHA-256 values, dynamic
requested/effective/used bank, event concentration, union brief, and exact
category coverage for 15 through 9. `cover`, `ev`, and `hybrid` are distinct
strategy labels; an EV/Hybrid union-brief category is descriptive and is not a
Cover target guarantee. Optional `--probabilities` JSON enables auditable
fixed-low-probability warnings and conditional union-brief category
probabilities.

## External Odds Coverage Workflow

External odds collection is a prospective coverage audit only. It does not feed
`ev-package`, does not change `PLAY` decisions, and does not prove probability
quality or profitability.

Before each future drawing deadline, register one lawful API-Sports free
account, keep the key local, and collect the next playable drawing:

```bash
read -s API_SPORTS_KEY
export API_SPORTS_KEY
python -m toto_ai.cli collect-external-odds --open --provider api-sports --db data/toto.db
```

Then audit the latest complete stored collections without provider network
access:

```bash
python -m toto_ai.cli audit-external-coverage --db data/toto.db --last 30 --min-bookmakers 3
```

API-Sports free football and hockey APIs each allow 100 requests per day. The
collector keeps a configurable reserve with `--quota-reserve` (default `10`) so
collection fails closed before spending the last daily or minute requests.
Schedule and odds endpoints are fetched page-by-page with explicit `page`
queries; inconsistent provider paging fails closed. Reported `requests_made`
counts actual HTTP attempts, including retries and extra pages, while cache
hits are reported separately and are not counted as requests.
Every collection stores all 15 event dispositions. Events with unknown sports,
missing or ambiguous matches, provider failures, quota exhaustion, stale or
incomplete markets, semantic market rejection, or fewer than three eligible
bookmakers keep the TotoBrief BK triplet with an explicit fallback reason.
The collection timestamp is the external observation time and is at least as
late as every consumed provider market fetch timestamp; the fresh TotoBrief
snapshot timestamp is preserved separately as target provenance.

The coverage gate is truthfully `PENDING` until at least 30 prospective drawings
and 450 events have been collected. After that floor, the audit can return
`GO` only if the registered predicates pass: unique match rate at least 80%,
usable consensus rate at least 70%, zero consumed ambiguous matches, and one
explicit external-or-fallback disposition for every event. A coverage `GO`
authorizes designing a separate calibrated ensemble and untouched prospective
evaluation; it does not authorize wiring external consensus directly into
`PLAY`.

The deterministic CSV exposes each matched schedule fetch timestamp/hash,
aligned market fetch/update timestamps and payload hashes, collection request
attempts, cache hits, TotoBrief target fetch provenance, remaining-quota
counters, the three-bookmaker/36-hour consensus settings, and every gate
predicate with its actual value, threshold, and observed result. The Markdown
report repeats the collection run, consensus configuration, gate decision, and
predicate outcomes for operator review.

## Data Health Contract

`data-health` is a read-only, versioned quality gate for the complete local
`baltbet-main` history:

```bash
python -m toto_ai.cli data-health --db data/toto.db
python -m toto_ai.cli data-health --db data/toto.db \
  --use-case backtest_probability --last 500 --no-strict
python -m toto_ai.cli data-health --db data/toto.db \
  --from-drawing 4940 --to-drawing 4959
```

Contract v1 reports every drawing and separate eligibility for:

- `historical_inventory`;
- `backtest_probability`;
- `result_settlement`;
- `prospective_generation`.

It treats a pool triplet `0/0/0` as invalid and accepts `*`/VOID/cancelled only
with an explicit source status/evidence as terminal results. Missing RAW/result snapshots are
preserved as distinct reason codes. A missing settlement is an error only for
a canonical `pre_bet_runner` package; legacy/rehearsal imports do not create a
settlement obligation.

The default is `--strict`. Exit code `0` means the selected use case passed,
`3` is a controlled data-quality failure, and `4` is an execution failure.
CSV, JSON, and Markdown reports are written under `reports/data-health` by
default. `--last` cannot be combined with range selectors.

Baseline brief generation and the MVP/baseline/strategy historical backtests
reuse the same fail-closed API. Historical commands expose only the explicit
`--allow-unhealthy-research` bypass and label its output as research-only;
prospective generation has no bypass.

## Finished-Drawing Lifecycle

Finished lifecycle freshness is stricter than row completeness. A finished
drawing remains stale until SQLite contains 15 terminal source outcomes and a
complete immutable result snapshot linked to an append-only RAW snapshot.
An active/expected cache can never satisfy a later finished summary.

Every network/cache payload is written first to a content-addressed archive
with capture time, source, lifecycle status, payload hash, metadata hash, and
snapshot hash. Only then may the shared full-detail importer merge drawing,
event, quote, result, score, and result-status fields. Empty/null/zero source
fields never erase stronger stored values; `0/0/0` is not useful pool data;
conflicting terminal outcomes fail closed.

Finished results are synchronized only by an explicit visible number or
internal ID. These commands never select an open or next drawing:

```bash
python -m toto_ai.cli sync-finished-results --drawing-number 4952
python -m toto_ai.cli reconcile-finished --last 20 --dry-run
python -m toto_ai.cli reconcile-finished --from-drawing 4940 \
  --to-drawing 4959 --batch-size 10 --apply
python -m toto_ai.cli repair-canonical-raw \
  --drawing-number 4954 --drawing-number 4955 --drawing-number 4956 --dry-run
python -m toto_ai.cli settle-drawing --drawing-number 4952 \
  --package-file reports/rehearsal/evening-4952/emergency-final/baltbet_package_4952_4980.txt \
  --stake 30
python -m toto_ai.cli post-draw-run --drawing-id 11970 \
  --package-file /absolute/package.txt --state-file /absolute/post-draw.json
```

`sync-finished-results` requires a finished, identity-matching drawing-info
payload with exactly 15 ordered results and scores. Operational event columns
are updated for convenience, while every distinct result/payment observation
is appended as an immutable hash-bound snapshot. Identical observations are
idempotent; official corrections append a new snapshot.

`reconcile-finished` is the non-betting nightly-ready command contract. It
selects only incomplete finished drawings, supports exact ranges or `--last`,
bounded retries/backoff, request pacing, batch limits, durable resume state,
and a network-free `--dry-run`. Each attempt ends explicitly as repaired,
source-incomplete, or exhausted; transport failures are never called source
absence.

`repair-canonical-raw` performs evidence-only offline recovery. Dry-run is the
default. It can restore only fields present in a validated local canonical RAW
payload and reports missing local evidence separately. It never synthesizes
historical data.

Package archives retain the canonical coupon hash, target identity, stake,
coupon count, source path, original bytes/hash, and provenance. Import legacy
evidence explicitly with `archive-package`; new actionable scheduler packages
publish a hash-bound `package-archive.json` before `.bet-ready`, which can be
imported with `archive-package --pre-bet-manifest`. Settlement never creates
its first archive after the draw.

Settlements bind the package archive to one result-snapshot hash and are
append-only/idempotent. Hit distribution and best coupon are known from 15/15
results, but category entitlement, return, and ROI remain unknown without
explicit supported official category/payout evidence. For drawing 4952,
payments are null, so return/ROI are null with `unknown_until_payouts`; they
are not inferred from the lack of a 10+ hit, pool, or jackpot totals.

Generate optional local scheduler candidates without installing anything:

```bash
python -m toto_ai.cli post-draw-plan --drawing-id 11970 \
  --ended-at 2026-07-22T16:00:00Z --package-file /absolute/package.txt \
  --state-file /absolute/post-draw.json --output-dir /absolute/scheduler
```

The generated plan preserves exact target identity and an absolute first-run
instant strictly after `ended_at`; its wrapper can only invoke that target.
Polling is bounded with exponential delay and writes terminal machine-readable
`complete`, `pending`, or `failed` state. It never installs automation or
places a bet.

## Project Memory

TotoAI uses a repository-local memory bank for persistent project context.
Before making changes, read [AGENTS.md](AGENTS.md) and the files in
[memory-bank/](memory-bank/).
