# Paper Package Visibility and Post-Draw Review Design

## Goal

Make every completed scheduler calculation inspectable, including terminal
`NO BET`, and close every drawing lifecycle with a result-bound review request
after all 15 events are terminal.

This feature never places a wager and never turns a paper package into an
actionable operator package.

## Current boundary

The scheduler already retains a validated `package.csv` checkpoint and the
finished-drawing subsystem already supports immutable package archive,
15-result/VOID settlement, and idempotent retry. The missing pieces are a
stable paper-facing pointer/report for `NO BET`, automatic post-draw retry at
the agreed cadence, and an explicit user-review request.

## Package visibility

Every terminal scheduler result must expose exactly one final package summary:

- `PLAY`: the actionable package remains governed by `.bet-ready`,
  `operator-result.json`, `operator-export`, and T-10 expiry.
- `NO BET` with a computed package: retain the final validated source CSV as a
  paper artifact and expose it through `paper-package-result.json`.
- `NO BET` without a computed package: expose a package-free paper result with
  the reason and the failed/missing stage.

`paper-package-result.json` binds the drawing ID/number, plan ID, decision,
reason, `actionable=false`, source package path and SHA-256 when present,
coupon count, stake, selected cost, probability-input hash, provenance, and
completion time. The referenced paper CSV remains the existing
`rank,coupon,gross_ev,net_ev` research evidence.

Every computed package also has a separate display/download text artifact in
the exact BaltBet text-editor syntax requested by the user. It contains no
header, warning, Markdown, rank, or EV columns. Each coupon occupies one line:

```text
30; 1; X; 2; 1; 1; 2; X; 2; 1; X; 2; 2; 1; X; 2
```

The first field is the configured stake and exactly 15 semicolon-separated
outcomes follow. Coupon order matches the validated source package. The text
artifact must contain exactly `selected_count` unique lines and its implied
cost must equal `selected_count * stake`.

For `NO BET`, warnings such as `PAPER / NO BET / DO NOT WAGER` are shown in
the surrounding CLI/status response only. They are never inserted into the
copyable text artifact, so its format stays valid and deterministic. The
artifact is still non-actionable and must not be exposed through
`operator-export` or `.bet-ready`.

Add a read-only `paper-package-show --plan ...` command. It validates all
bindings, prints the terminal summary and warning to stderr, and writes only
the exact BaltBet-format coupon lines to stdout or an explicit output file.
T-10 deletes only actionable operator-upload surfaces; the non-actionable
paper text artifact remains available for audit and learning.

## Post-draw schedule

For every scheduler plan that reaches a terminal decision, generate a
non-betting post-draw plan bound to the final paper/actionable package hash.
The first check is 12:00 Europe/Moscow on the next calendar day after the
drawing deadline. If fewer than 15 events have terminal results, retry at
15:00, 18:00, 21:00, 00:00, and then every three hours until the existing
bounded expiry policy is reached.

VOID/cancelled events count as terminal only when the authoritative source
provides the explicit status and the existing reviewed-VOID contract accepts
it. A postponed event without an authoritative terminal status remains
pending.

The post-draw runner reuses `sync_finished_drawing`, package archive, and
`settle_archived_package`; it does not create a second settlement algorithm.
Retries are idempotent and preserve immutable result/package bindings.

## Review request

When settlement reaches 15/15, write `review-request.json` with:

- drawing and package identity;
- settlement hash and best coupon hits;
- category 13/14/15 counts;
- fixed misses, zero-exposure misses, and VOID event orders;
- known return/ROI status when official payouts exist;
- `status=AWAITING_USER_REVIEW` and `requested_at`.

The local automation displays one best-effort macOS notification asking the
user whether to review the drawing. The durable JSON file is authoritative;
notification failure does not alter settlement or retry it. On the next Codex
interaction, project status checks must surface every unacknowledged review
request and ask: `Разбираем пакет тиража N?`

User acceptance changes the request to `REVIEW_REQUESTED`; declining changes
it to `REVIEW_SKIPPED`. A completed analysis records `REVIEW_COMPLETE` and a
path/hash to an immutable Markdown postmortem. No state is silently marked
reviewed.

## Postmortem contents

The generated review compares:

- actual 15-outcome result including VOID handling;
- best coupon and hit distribution;
- event exposure versus actual outcome;
- BK, pool, Pin when present, sports-shadow, and selected probability rows;
- fixed and zero-exposure misses;
- estimated EV versus known payout result;
- concrete model/package errors, without claiming causal certainty from one
  drawing.

Conclusions enter research evidence only after user review. A single drawing
may diagnose a defect but cannot activate a model or establish profitability.

## Failure handling

- Missing results: persist `PENDING_RESULTS` and retry after three hours.
- Transport failure: persist the typed error and retry without modifying prior
  snapshots.
- Identity, hash, or terminal-result conflict: fail closed as
  `REVIEW_BLOCKED_INTEGRITY`; do not retry automatically.
- Notification failure: record it as advisory only; keep
  `AWAITING_USER_REVIEW`.
- Missing package: settle the drawing data but produce a package-free review
  explaining why no package existed.

## Verification

Acceptance requires tests for PLAY and NO BET paper visibility, exact
`stake; 15 outcomes` text syntax and pure stdout/file content, package-free NO
BET, T-10 operator expiry without paper deletion, exact 12:00/three-hour
cadence, incomplete and VOID results, idempotent settlement, notification
failure, review-state transitions, and tampered package/result rejection.
