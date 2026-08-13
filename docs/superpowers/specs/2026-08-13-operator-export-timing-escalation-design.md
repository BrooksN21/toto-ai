# Operator Export and Timing Escalation Design

## Goal

Prevent any unbound, research-only, expired, or `NO BET` coupon file from
being presented as a BaltBet operator package, and make a `READY 15/15`
preparation with missing event times an explicit recoverable preflight state.

## Operator export boundary

Add one read-only `operator-export` command. It accepts a scheduler plan and an
output path. It loads only that plan's `operator-result.json` and exports only
when all of these conditions hold:

- the result has the same plan and drawing identity;
- `decision == "PLAY"`, `operator_status == "PLAY"`, and `actionable == true`;
- automatic wagering is false;
- the current time is strictly before the plan's T-10 publication deadline;
- `coupon_path` is the canonical scheduler-owned `baltbet-upload.txt` under the
  current last-known-good checkpoint;
- the LKG pointer, manifest, authoritative drawing, package bytes, coupon
  count, cost, bank, stake, and every SHA-256 validate through the existing LKG
  loader;
- the operator result fields equal the validated LKG fields.

The command writes the already validated bytes atomically. It never derives,
ranks, copies from, or converts research coupons. On any mismatch it writes
nothing and exits non-zero. Existing scheduler `NO BET` results remain
non-exportable even if they retain an audit-only LKG path.

The unbound 4973 file is retained only as quarantined post-draw evidence and is
not imported as a production package.

## Missing-time escalation

Morning preparation continues to distinguish event identity from event time.
A baseline-only event may complete identity preparation while still lacking a
start time. Such an event becomes a `timing_unknown` preflight item:

- preparation may remain `ready` with `mapped_count == 15`;
- eligibility remains `unknown` and no evening plan is created;
- `ACTION_REQUIRED.md`, `attention.json`, retry plan, and reviewed-schedule
  queue identify the exact event orders and names;
- retries remain bound to drawing ID, visible number, deadline, and
  fingerprint, stop before T-60, and may activate the evening scheduler only
  after a later retry reaches playable 15/15 timing;
- multi-day and late drawings remain fail-closed.

An attention record is resolved only when preparation is ready, all identity
and timing issues are gone, and eligibility is playable.

## 4973 regression evidence

Record the official result and post-draw comparison as research evidence:
166 coupons, 4,980 RUB cost, best 7/15, zero 10+/13+/14+/15. The unbound file
must fail `operator-export`. This evidence does not modify probabilities or
release quality-v2 for real money.

## Verification

- RED/GREEN tests for all export rejection and success invariants.
- RED/GREEN tests for ready-15/15 timing escalation, retries, queue generation,
  eventual resolution, and activation eligibility.
- Frozen 4973 regression test for the observed hit distribution.
- Focused tests, full `pytest`, Ruff, and `git diff --check` before commit.

