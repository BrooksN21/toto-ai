# Safe Drawing Runner Design

## Context

TotoAI can already collect one fresh external-odds snapshot, retry within the
API-Sports quota, classify drawing duration, audit stored evidence, and build a
modeled-EV package. The operator currently has to coordinate these commands and
the drawing deadline manually.

One live drawing completed the fresh collection in about 69 seconds, but that
single observation is not a timing guarantee. The operational workflow needs a
visible schedule, a safety cutoff, exact target binding, and one deterministic
result artifact. The runner must never place a bookmaker bet.

## Goal

Add one operator command that prepares immediately, waits until 20 minutes
before the BaltBet deadline, then performs the existing collection, timing,
audit, and package workflow without silently changing any accepted model.

The command reduces operational error and accumulates prospective external-odds
evidence. It does not make external probabilities playable before the existing
30-drawing/450-event gate and a separate approved integration.

## CLI

Add:

```bash
python -m toto_ai.cli run-drawing \
  --open \
  --bank 5000 \
  --stake 30 \
  --mode playable
```

Options:

```text
--open                               required
--bank INTEGER                       required, positive multiple of stake
--stake INTEGER                      default 30
--mode research|playable             default playable
--final-lead-minutes INTEGER         default 20
--safety-stop-minutes INTEGER        default 5
--db PATH                            default data/toto.db
--report-dir PATH                    default reports
--provider TEXT                      default api-sports
--aliases PATH                       existing external aliases default
--quota-reserve INTEGER              existing provider default
--max-passes INTEGER                 existing prospective default
--max-expansion-passes INTEGER       existing expansion default
--retry-delay-seconds FLOAT          existing prospective default
--cache-root PATH                    existing fresh-cache default
```

Validate `final_lead_minutes > safety_stop_minutes >= 1`. The command always
uses a fresh invocation cache. Shared historical cache reuse is intentionally
not available through this production-oriented command.

## Timing State Machine

All wall-clock comparisons use aware UTC datetimes. Waiting uses an injectable
monotonic clock and sleeper, with the wall clock re-read after every wake-up.

1. **Preflight** resolves the nearest open drawing and fetches its exact
   drawing-info payload. It records drawing ID, visible number, deadline, and
   canonical target fingerprint. It validates configuration, API-key presence,
   database writability, report paths, and provider construction without
   persisting the key. Last stored quota is advisory only; live quota remains
   unknown until a provider response supplies headers.
2. **Too early** means `now < deadline - final_lead`. The runner displays a
   Rich countdown and sleeps in bounded increments. It performs no bookmaker
   package generation while waiting.
3. **Final window** means
   `deadline - final_lead <= now < deadline - safety_stop`. The runner starts
   immediately, whether it reached the window by waiting or was launched
   inside it.
4. **Safety stop** means `now >= deadline - safety_stop`. The runner does not
   start another collection phase or package build and returns a recorded
   zero-cost `NO BET`. An already in-flight HTTP request may finish under its
   configured timeout, but cannot trigger a new runner-level attempt after the
   cutoff. T-5 is also the publication cutoff: a package computation that
   finishes at or after T-5 is suppressed to zero-cost `NO BET`.

The runner re-resolves and re-fetches the open target immediately before final
collection. Drawing ID, number, deadline, and canonical fingerprint must equal
preflight. Any change is a fail-closed `NO BET`; the runner never rolls forward
to another drawing.

## Orchestration

Implement a new provider-neutral orchestration module rather than invoking CLI
commands as subprocesses. Dependencies are injected for tests.

Final execution order:

1. Revalidate the pinned target and safety window.
2. Call the existing fresh prospective collector with the pinned target,
   two-day base horizon, and approved expansion through day five.
3. Persist every complete 15-event collection pass through the existing
   append-only storage.
4. Read the exact latest drawing/fingerprint eligibility from SQLite.
5. Run the existing external coverage audit and deterministic reports. Its
   `GO/PENDING/STOP` result remains diagnostic and does not inject external
   probabilities into the package.
6. Build the existing EV package from another fresh payload and the same exact
   read-only timing resolver. Its current fingerprint check protects the final
   boundary against a target change between collection and package generation.
7. Publish one runner manifest and Markdown operator report atomically.

The prospective orchestrator gains an optional already-resolved target payload
for this runner. When supplied, it validates and pins that payload without
resolving a different open drawing; the existing standalone collection command
keeps its current resolution behavior.

The coverage audit uses the latest complete snapshot for each of the latest 30
collected drawings, matching the existing CLI default and sample gate. It
remains diagnostic until a separate approved probability integration.

No probability row, EV formula, payout proxy, ranking rule, category
definition, bank rule, stake rule, consensus threshold, coverage gate, or
multi-day eligibility definition changes.

## Decisions and Failure Behavior

The terminal decision is one of:

- `PLAY`: the existing playable EV package selected coupons and timing is
  exactly `playable` before the safety cutoff;
- `NO BET`: a valid fail-closed outcome, including timing veto, expired safety
  window, target mismatch, collection failure that prevents an exact stored
  eligibility verdict, missing eligibility, or the existing EV threshold
  selecting no package;
- `RESEARCH ONLY`: research mode completed and produced diagnostic coupons.

An event-level provider-odds fallback does not itself veto the current
TotoBrief-BK package. It remains explicit audit evidence because external
probabilities are not yet part of playable EV.

`NO BET` is a successful operator decision and exits with code zero. Invalid
arguments, unreadable/writable-path violations, unsanitized internal failures,
and corrupt persisted state are command failures and exit nonzero. The report
must distinguish the terminal decision from command success/failure.

Secrets are accepted only through the existing environment variable. They are
never included in exceptions, caches, SQLite, progress output, manifests, or
reports. `KeyboardInterrupt` exits promptly, preserves already committed
append-only collection snapshots, and never publishes a successful final
manifest.

## Artifacts

Publish a rollback-safe pair under `report_dir`:

```text
drawing_run_<drawing_number>_<deadline>_<run_id>.json
drawing_run_<drawing_number>_<deadline>_<run_id>.md
```

`run_id` is a short SHA-256 prefix over the canonical preflight target,
preflight timestamp, and runner configuration. Distinct invocations cannot
silently overwrite one another; identical deterministic test inputs reproduce
the same identity and bytes.

The canonical JSON manifest contains:

- schema version and deterministic run identity;
- drawing ID/number, deadline, preflight fingerprint, and final fingerprint;
- configured bank, stake, mode, lead, safety stop, and provider;
- preflight, final-start, collection-finish, package-finish timestamps;
- collection IDs, pass counts, requests, cache hits, final horizon, and stop
  reason;
- eligibility status, span, timing source counts, and fingerprint match;
- external coverage gate decision as diagnostic provenance;
- EV/package decision, package cost, unused bank, and package-report paths;
- sanitized warnings and terminal reason.

The Markdown report is an operator-readable rendering of the same canonical
facts. Coupons may appear only when the existing EV package is allowed to
publish them. A timing-vetoed or expired run cannot leak diagnostic coupons.

## Tests

Tests use fake clocks, sleepers, TotoBrief clients, and providers. Real network
calls and real sleeping are forbidden.

Acceptance must prove:

- preflight before T-20 waits and then starts exactly at the final window;
- launch between T-20 and T-5 starts immediately;
- launch at or after T-5 records zero-cost `NO BET` without provider access;
- drawing, deadline, or fingerprint change after preflight is `NO BET` and
  never rolls to the next draw;
- safety cutoff is rechecked before final collection and package generation;
- a package finishing at or after T-5 is suppressed and cannot publish coupons;
- ordinary, expanded, multi-day, unknown, absent, and mismatched timing use the
  existing eligibility behavior;
- arbitrary valid banks remain capped exactly and stake remains configurable;
- external coverage `PENDING` cannot enter EV probabilities or change ranking;
- append-only snapshots and audit/package reports remain valid;
- manifest/Markdown publication is deterministic and rollback-safe;
- interruption cannot publish a successful final artifact;
- API keys are absent from every persisted and displayed surface;
- existing collection, audit, eligibility, EV, and CLI tests remain green.

## Non-Goals

This feature does not:

- submit a bet to BaltBet or any bookmaker;
- run as a background daemon or install `cron`/`launchd` configuration;
- guarantee that the machine remains awake or connected while waiting;
- use API-Sports consensus in playable EV calculations;
- bypass the prospective external-probability gate;
- tune probabilities, EV thresholds, or package optimization;
- claim profitability.
