# Accepted backfill/retry integration boundary

The 2026-09-06 engineering candidate combines only the accepted history-backfill
input-validation fix and retry-calendar/unknown-cleanup corrections. It does not
change probability, category, budget, cutoff, consent, or operator definitions.

- Backfill validates all manifest inputs before database initialization. Invalid
  inputs preserve database absence/bytes; mixed inputs retain explicit PARTIAL
  semantics, not an undocumented all-or-nothing rollback guarantee.
- Retry activation-policy changes preserve the existing calendar and hard stop.
  Unknown job state cannot authorize cleanup, plist deletion, or restoration.
  Integration tests mock job-control calls; live job operations are out of scope.
- Storage requires the matching domain semantic-persistence implementation.
  Target parsing must retain the accepted immature-pool handling. These already
  exist in the current main working tree and are hash-bound dependencies, not
  files to overwrite from an older checkout.
- The backfill CLI import/command is already in dirty main. Only that exact
  delta was materialized in the isolated review checkout for integration tests;
  it yields byte-identical CLI contents. The main-relative candidate therefore
  guards CLI unchanged rather than replacing it. New synthetic CLI tests cover
  successful import, validate-only, rejection without SQLite initialization,
  and partial-success exit status.

The candidate patch and manifest must be used together. The read-only verifier
checks the exact HEAD, repository-wrapper bytes, dependency/before hashes,
patch SHA-256, strict context, exact target set, and reconstructed after hashes.
It does not apply changes. Recheck immediately before separately authorized main
application; a changed dependency or user edit is a conflict, not permission to
overwrite. Preserve policy and all unrelated dirty work.

A current-working-tree patch is not a claim that an arbitrary clean HEAD alone
contains the dirty dependencies. The integration receipt records the bounded
release dependency set; future staging/commit must include that coherent set.
Full-project release validation, live application, staging, commit, push, and
PR creation remain separate. F3, GOAL deduplication, current drawings, historical
audits, and model activation are not part of this candidate.
