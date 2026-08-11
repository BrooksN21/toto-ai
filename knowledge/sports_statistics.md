# Sports statistics evidence

## Current contract

Sports evidence is collected before the BaltBet drawing deadline and stored as
an immutable, content-addressed audit snapshot. Each event records:

- exact drawing/event/provider fixture and team identities;
- target start, deadline, captured-at and as-of times;
- source request fingerprint, payload hash and fetch time;
- up to ten completed fixtures strictly before both as-of and target kickoff;
- overall and home/away W-D-L and goals, points/form, rest days;
- current standing when the provider lawfully supplies it;
- explicit status and missing reasons.

Cancelled, postponed, scheduled, live, target, and future fixtures are excluded.
Rows for unrelated teams are ignored. A history window exists only when at
least one eligible completed fixture exists; provider errors, plan denial, and
missing history remain `None` with an explicit missing reason. CSV and Markdown
numeric fields stay blank rather than showing a fabricated `0-0-0`.

Historical `--historical-as-of` is a frozen-input replay. Drawing detail must
come from a hash-verified raw cache plus metadata sidecar captured at or before
the requested as-of, and every API-Sports payload must already exist in cache
at or before that boundary. The historical path performs zero network access
and fails closed when frozen drawing evidence is absent or newer than as-of.

Prospective team history is normally requested as `last=N`. Historical replay
uses a bounded `from/to` request identity but may reuse that exact frozen
`last=N` cache entry for the same team, season, completed-status filter and
timezone. The cache is accepted only when `fetched_at <= as_of`; its real
request fingerprint is retained, and fixtures are filtered locally again so
only the requested team's completed matches strictly before both target
kickoff and as-of survive. A replay never converts a cache miss into a network
request. Repeating a replay from the same frozen evidence reproduces identical
event features and report bytes.

## Activation policy

The evidence has no production package influence. The current production
probability matrix remains exclusively normalized TotoBrief BK; pool
probabilities are crowd/EV input.

The shadow sports-probability provider, evaluator, and CLI are implemented.
They emit `NOT_ACTIVATED` machine-readable artifacts containing BK,
sports-shadow, candidate blend, raw feature summaries, content/source
provenance, and explicit fallback reasons. They are deliberately not connected
to `EVInput`, package selection, scheduler decisions, or betting state.

The experimental sports estimate is a Jeffreys-smoothed venue-only W-D-L
projection. It uses the home team's home W-D-L and the away team's away W-D-L,
and is untrained. Both venue windows must contain pre-as-of observations.
Missing or invalid venue data is labelled `non_venue_unavailable` and falls
back to normalized BK; aggregate W-D-L is retained as a diagnostic but is never
substituted, never described as venue evidence, and cannot satisfy the
activation coverage gate. The candidate blend weights sports evidence against
BK using only the matched venue observation count and requested-history prior;
it does not claim fitted coefficients. Goals, overall form, rest, and standings
remain visible in the artifact as diagnostics until lawful data and OOS
evidence support a trained model.

Every event validates immutable content hashes, as-of/deadline and pre-match
boundaries, drawing fingerprint, target event identity, provider fixture/team
orientation, canonical pins, and source timestamps. Any unproved event uses
normalized BK unchanged.

OOS BK probabilities come only from the hash-bound frozen authoritative
drawing snapshot embedded in the shadow artifact and captured no later than
`as_of`; mutable current quote rows are forbidden. Missing/late authority,
fingerprint drift, future sources, and missing/mismatched orientation are
blocking integrity failures. Ordinary missing sports history is instead a BK
fallback that lowers coverage without being classified as leakage.

The chronological evaluator reports multiclass log loss, Brier score,
confidence ECE, drawing/event counts, sports coverage, fallback, and validation
failures for BK, sports-shadow, and candidate blend. The fail-closed gate needs
at least 30 drawings / 450 events, at least 70% sports coverage, strict blend
improvement over BK in log loss and Brier, calibration within tolerance, and
zero leakage/fingerprint/validation failures. Even a pass is
`PASS_REVIEW_REQUIRED`; production remains `NOT_ACTIVATED` until a separate
reviewed architecture change. No profitability is proven.

The sample and coverage values are non-reducible hard minima. The documented
calibration tolerance of 0.02 is a maximum; callers may request stricter values
only.

Injuries, lineups, xG, and Elo are not implemented.

## API-Sports free-plan finding

The drawing-4957 acceptance run showed that target fixture context is
available, but current-season team history and standings are denied by the
configured free plan. The implementation records
`provider_plan_unavailable` and market-only fallback instead of querying
current state retrospectively, using old-season substitutes, or fabricating
zeros.

The reviewed rerun on 2026-07-27 produced 15 partial events, zero complete
events, and blank history/W-D-L/goals fields under
`provider_plan_unavailable`. It remained `AUDIT ONLY` with `MARKET ONLY`
fallback and did not alter package or PLAY state.

The next provider must offer lawful current-season completed fixtures and
standings with stable team/fixture IDs, source timestamps, and enough quota for
pre-deadline collection.
