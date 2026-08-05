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

The evidence is `AUDIT ONLY`. It has no package influence and falls back to the
bookmaker market prior. A sports model or blend is allowed only after frozen
chronological out-of-sample evaluation on at least 30 drawings / 450 events,
with adequate feature coverage and no reproducible degradation versus the
bookmaker baseline.

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
