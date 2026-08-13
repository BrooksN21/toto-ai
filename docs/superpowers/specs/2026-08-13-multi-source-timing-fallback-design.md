# Multi-source kickoff fallback design

Date: 2026-08-13

## Goal

Prevent an ordinary API-Sports schedule gap from becoming a daily manual
`timing_unknown` incident. Morning preparation must automatically seek public
kickoff evidence from other sources before deferring the drawing. It must not
guess a kickoff or weaken the existing fail-closed package boundary.

This feature resolves schedule identity and time only. It does not change
outcome probabilities, EV, coupon selection, bank handling, paper-only release
policy, or manual wager placement.

## Acceptance policy

An automatic kickoff observation is accepted only when all conditions hold:

1. The target is currently unresolved only because its kickoff is absent.
2. At least two current HTTPS claims are available from distinct domains.
3. One claim is from an allowlisted official domain and one from an
   allowlisted independent schedule domain.
4. Both claims identify the exact same teams, orientation, scheduled status,
   and UTC kickoff.
5. Team identity is exact after existing reviewed aliases and deterministic
   normalization/transliteration. Fuzzy similarity and search rank are never
   acceptance evidence.
6. The competition is compatible and the kickoff lies between the drawing
   deadline and the existing maximum five-day drawing window.
7. The pages were fetched before kickoff, within the configured freshness
   window, and their immutable snapshots and SHA-256 values were persisted.

Any disagreement, redirect outside the allowlist, ambiguous identity,
conditional pairing, unknown source role, stale page, unsupported parser,
network failure, or missing second source leaves the event `timing_unknown`.
No package may be enabled while any such event remains.

## Architecture

### 1. Source discovery

`PublicScheduleDiscovery` receives only the unresolved target event and bounded
date window. It queries pluggable public discovery adapters and returns
candidate HTTPS URLs. Discovery output is untrusted: it cannot establish team
identity, source role, or kickoff.

The initial implementation supports:

- exact-domain official adapters for structured tournament/league pages;
- independent match-page discovery for allowlisted schedule sites;
- a best-effort public HTML search adapter used only to discover candidate
  URLs on allowlisted domains.

Discovery runs in the morning and during identity-bound retries, never in the
heavy final package phase. Requests are rate-limited, cached, bounded by size
and timeout, and contain no repository data or secrets beyond public team,
competition, and date strings.

### 2. Extraction

`SchedulePageExtractor` converts a fetched page into zero or more immutable
claims. The generic extractor reads schema.org `SportsEvent` JSON-LD and
explicit HTML `time` elements. Small source-specific extractors are allowed
only for stable public formats that the generic extractor cannot represent.

Each claim records source URL/domain/role, raw team names, orientation,
kickoff, status, capture time, parser version, snapshot path, content hash, and
the exact structured fragment that produced the claim. Parser failure is data,
not an exception that terminates the complete morning run.

### 3. Trust registry

A versioned project-local source policy maps domains to `official` or
`independent`. Official domains are scoped to compatible competition aliases
or canonical organizer identities. Unknown domains and club fan/media pages
remain diagnostic-only. Redirects must end on an allowed domain with the same
role.

The registry is configuration, not a per-drawing exception. Match IDs,
drawing numbers, event positions, team outcomes, and kickoff values are never
hardcoded in production code or policy.

### 4. Exact consensus

`AutomaticScheduleConsensus` groups claims by canonical oriented team pair,
competition, scheduled status, and exact UTC kickoff. It emits one accepted
observation only when a group satisfies the official-plus-independent policy.
Competing valid groups produce `CONFLICT`, never a majority vote.

Automatic evidence is labelled explicitly with
`verification_mode=automatic_consensus`; it is not represented as a human
review. The evidence schema remains backward-compatible with existing human
reviewed rows.

### 5. Operational persistence and scheduler binding

Automatic observations and snapshot metadata are stored transactionally in
the operational SQLite database. Source page bytes are stored beneath a
contained operational evidence directory and addressed by SHA-256. Repeated
runs are idempotent; an existing observation identity cannot be changed.

The tracked human seed ledger is not mutated by daily automation. Before
preparation, the system materializes one canonical per-drawing evidence
snapshot from:

- the tracked human seed ledger; and
- validated automatic observations relevant to the current target.

The merged snapshot is immutable for the preparation attempt. Existing
schedule-evidence validation is reused, and the evening scheduler binds its
absolute path, content SHA-256, and semantic hash exactly as it does today.
Any later evidence change requires a new morning preparation and a newly bound
plan.

### 6. Morning data flow

1. Synchronize the exact open TotoBrief drawing.
2. Fetch API-Sports schedule and prepare using existing evidence.
3. If and only if baseline-only events still have unknown kickoff, run the
   fallback collector for those events.
4. Validate and transactionally persist accepted consensus observations.
5. Materialize the merged evidence snapshot.
6. Re-run preparation using the same TotoBrief detail and cached API-Sports
   schedule plus the merged snapshot; do not repeat unrelated network work.
7. If READY/playable, create and optionally activate the ordinary evening
   plan. Otherwise write the existing ACTION_REQUIRED queue and retry plan.

Fallback retries retain the current drawing ID, visible number, deadline and
fingerprint guards and stop before T-60. The fallback has its own bounded
request budget so it cannot consume final package runtime.

## Operator visibility

Morning/preflight output adds, without exposing secrets:

- unresolved events submitted to fallback;
- source URLs/domains and assigned roles;
- parser and fetch status per source;
- accepted/conflicting/missing consensus counts;
- resulting kickoff and evidence hashes;
- whether preparation was retried and its final 15/15 status.

`timing_unknown` remains visible when fallback cannot prove a result. There is
no silent baseline-only promotion.

## Security and reliability

- HTTPS only; no disabled TLS verification.
- Allowlisted domains and bounded redirects.
- Response size/content-type limits and request timeouts.
- Shared rate limiting and immutable cache/snapshot hashes.
- No cookies, login, browser automation, API keys, or secret transmission.
- No automatic wager placement.
- Partial evidence never authorizes a package.
- Source outages affect only their claims and remain retryable before T-60.

## Testing

Implementation follows TDD with network-free fixtures.

Required regressions:

- frozen drawing 4974: API-Sports misses events 8 and 15; official plus
  independent snapshots resolve both automatically and preparation reaches
  the same 15/15 timing state as the reviewed incident fix;
- repeated collection is byte/idempotent and does not duplicate observations;
- official-only, independent-only, conflicting kickoff, reversed teams,
  ambiguous aliases, wrong competition, stale page, unknown domain, unsafe
  redirect, oversized response, malformed JSON-LD, and conditional match all
  remain `timing_unknown`;
- one accepted event may be retained for reuse, but one remaining unresolved
  event keeps the complete drawing fail-closed with no evening plan;
- evidence snapshot/hash drift prevents scheduler execution;
- bank remains dynamic and unrelated to fallback behavior;
- no drawing number, event order, fixture ID, or target kickoff hardcode exists
  in production source policy.

After unit and integration tests, run full pytest, Ruff, diff-check, a frozen
4974 rehearsal, and an activation-disabled live morning drill. Real evening
activation remains governed by the existing paper-only and scheduler safety
boundaries.

## Non-goals

- Predicting match outcomes from these pages.
- Scraping lineups, injuries, xG, or form in this feature.
- Accepting a single source because the match appears obvious.
- Automatically learning aliases from fuzzy matches.
- Guaranteeing universal coverage of every league. Unsupported events remain
  safely unresolved and are added through reusable source adapters/policy,
  never one-off drawing patches.
