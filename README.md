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

## Project Memory

TotoAI uses a repository-local memory bank for persistent project context.
Before making changes, read [AGENTS.md](AGENTS.md) and the files in
[memory-bank/](memory-bank/).
