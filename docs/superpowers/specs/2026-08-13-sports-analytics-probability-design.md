# Sports Analytics Probability Layer Design

## Goal

Improve pre-match 1/X/2 probabilities with leakage-safe sports evidence while
keeping TotoBrief BK as the production control and activating no new model
until it proves out-of-sample improvement.

The goal is a better probability estimate and, ultimately, better 13+/14+/15
package performance. Profit is not assumed and cannot be promised.

## Recommended approach

Build a provider-neutral evidence and feature layer, then compare a calibrated
market baseline against a conservative sports-adjusted ensemble in shadow
mode. Do not replace BK with a raw form heuristic and do not wire sports data
directly into package selection before the gate passes.

The alternatives were rejected:

- a pure sports model discards the strongest available market prior and is too
  fragile for sparse leagues;
- manual match-by-match expert overrides are not reproducible or backtestable;
- immediate production blending would turn incomplete prospective evidence
  into unmeasured real-money risk.

## Data-source hierarchy

Use only public, authorized sources and store source URL/API identity,
retrieval time, as-of boundary, request fingerprint, payload hash, and coverage
for every observation.

1. Existing API-Sports data remains the current source for supported fixture
   identity, completed results, venue form, goals, rest, and standings.
2. TheSportsDB free API is evaluated as the first automatic fallback for
   schedules, results, teams, and standings. Its free tier is rate-limited and
   cannot be assumed complete.
3. football-data.org is evaluated for covered competitions under its free
   registered plan; unsupported competitions fall through rather than being
   guessed.
4. football-data.co.uk CSV data is used for historical result/odds/statistics
   backfill where league coverage exists.
5. StatsBomb Open Data is research-only because it covers selected
   competitions, but it can validate feature/model ideas on richer event data.

The Odds API is the first external market-odds provider to be evaluated. It is
not a sports-statistics source and does not replace the hierarchy above. Its
role is to provide independently collected pre-match 1/X/2 prices from 1xBet,
Pinnacle where available, and a broader bookmaker consensus for comparison
with the frozen TotoBrief BK control.

No website scraping, unofficial credential reuse, or fabricated fixture/team
matching is allowed. Provider gaps are explicit. The system may fall back per
event to the frozen BK row.

## The Odds API shadow audit

The integration remains read-only and `NOT_ACTIVATED`. It must not alter
production probabilities, package selection, scheduler eligibility, `PLAY`,
or operator exports during the audit.

For every eligible open drawing, capture up to three immutable observations:

- morning/pre-analysis;
- the existing control checkpoint before the final run;
- final T-10.

Requests are quota-aware. Query only sports represented in the target drawing,
the European bookmaker region, and the head-to-head market needed for full-time
1/X/2. Record request-credit headers and stop optional calls before exhausting
the configured reserve. Exhausted quota, timeout, HTTP errors, malformed data,
or missing bookmaker coverage are typed missing evidence and must not block the
existing TotoBrief-BK package path.

An event is accepted only after deterministic identity validation of sport,
competition where available, normalized participants, home/away orientation,
and kickoff tolerance. Reversed or ambiguous matches remain diagnostics and
cannot provide an odds row. Football must use full-time 1/X/2; hockey must use
the regulation-time three-way market expected by the target Toto event rather
than a two-way moneyline including overtime.

Each accepted snapshot stores provider event ID, bookmaker key, raw decimal
prices, normalized overround-free probabilities, bookmaker update time, local
retrieval time, source endpoint identity, request fingerprint, response hash,
target fingerprint, orientation, matching disposition, freshness, and quota
cost. Persist 1xBet, Pinnacle, and bookmaker consensus as separate views; never
substitute one silently for another.

The first live probe is a current-drawing shadow rehearsal. The prospective
audit then covers at least 30 consecutive completed drawings / 450 events.
Reports compare exact event and bookmaker coverage, freshness, failures and
quota cost, followed after settlement by log loss, Brier score, calibration,
and unchanged-package shadow replay against TotoBrief BK. Coverage alone cannot
activate the source. Any later production use requires the existing activation
gate and a separate explicit decision.

The API key is read only from the protected environment variable
`THE_ODDS_API_KEY`. Its value must never appear in logs, reports, fixtures,
exceptions, documentation, Git history, or request fingerprints.

## Market baseline

For each event preserve three independent market views when present:

- normalized TotoBrief BK;
- TotoBrief Pin fields as a benchmark supplied by TotoBrief, not by direct
  Pinnacle access;
- pool probabilities as a crowd/payout model, never sports truth.

First establish chronological BK, Pin, and calibrated-BK metrics by sport,
competition family, probability band, and season. Pin cannot be silently
substituted when absent.

## Football feature set

All features must be computable strictly before the frozen `as_of` instant:

- exponentially weighted Elo with home advantage and competition-strength
  shrinkage;
- home/away W-D-L and goals-for/goals-against windows;
- recent form and rest days;
- current table strength only from snapshots available before kickoff;
- schedule congestion;
- promoted/new-team and sparse-history flags;
- optional injuries and confirmed lineups only when a licensed/public source
  provides timestamped, identity-matched evidence.

Aggregate league form may diagnose coverage but may not masquerade as team
venue evidence. Missing features are represented by flags and shrinkage to the
market prior, not zero-filled as real observations.

The first trained candidate is a regularized multinomial log-odds adjustment
around BK. It predicts residual correction rather than a standalone outcome:

```text
candidate logits = log(BK probabilities) + fitted sports residuals
```

This preserves the market prior and lets sparse or uncertain evidence receive
near-zero adjustment. Training is deterministic and implemented with the
project's NumPy stack; coefficients, normalization statistics, data cutoff,
training IDs, and content hashes are immutable artifacts.

## Chronological evaluation

Use walk-forward splits by drawing deadline. A row is eligible only when the
target, team orientation, result, feature sources, and frozen BK/Pin snapshot
are hash-bound and all source timestamps precede `as_of`.

Compare:

- BK control;
- Pin benchmark where present;
- calibrated BK;
- current Jeffreys venue shadow;
- trained sports residual model;
- conservative BK+sports ensemble.

Primary model metrics are multiclass log loss, Brier score, confidence ECE,
coverage, and fallback rate. Secondary end-to-end metrics rerun the unchanged
package selector and report P(13+/14+/15), actual category hits, diversity,
cost, and settlement ROI where official payouts are known.

The same final packages are always settled and reviewed, including `NO BET`
paper packages. This prevents selection of a model solely because it looks
good on event-level accuracy.

## Activation gate

The candidate remains `NOT_ACTIVATED` until all conditions are met on a
predeclared prospective holdout:

- at least 30 complete drawings and 450 events;
- at least 70% sports-feature coverage;
- no leakage, identity, orientation, or fingerprint failures;
- strictly lower log loss and Brier than BK;
- ECE no worse than BK by more than 0.02;
- no material degradation of 13+/14+/15 package outcomes across registered
  bank sizes;
- independent user review of the evaluation report.

A pass produces `PASS_REVIEW_REQUIRED`, not automatic activation. Production
integration is a separate approved change with an instant rollback to BK.

## Delivery sequence

1. Audit source coverage on recent Toto drawings without changing predictions.
2. Backfill immutable historical sports evidence and compute leakage-safe
   features.
3. Establish market baselines, including existing Pin fields.
4. Train and walk-forward evaluate the residual model and ensemble.
5. Start prospective shadow collection for every new drawing.
6. Evaluate package-level and settlement outcomes.
7. Consider production activation only after the full gate passes.

## Verification

Tests must cover provider failure/fallback, exact team orientation, duplicate
and ambiguous fixtures, timestamp leakage, sparse/new teams, deterministic
Elo/features/training, probability normalization, walk-forward separation,
model artifact hashes, BK fallback, dynamic banks, and unchanged package
selection when the sports model is not activated.
