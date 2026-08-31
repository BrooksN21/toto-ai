# Drawing 4993 parallel challengers and Sports Analytics v2

## Objective

Preserve the existing drawing-4993 quality-v2 scheduler as the immutable,
fail-safe operator control while evaluating quality-v3, sports-shadow and a
robust recombination from the same frozen final input, bank and stake.  A
challenger may become the experimental manual package only through a separate,
hash-bound, pre-T-10 selection record and only when all common safety checks
pass.  Automatic wagering remains disabled.

## Non-negotiable safety boundary

- Do not change, regenerate, unload or delay scheduler plan
  `bd649bfd70e5b165` while implementing the parallel path.
- The quality-v2 scheduler must publish normally even when every challenger
  fails or times out.
- Challengers run in a separate process and output tree after a frozen
  scheduler input exists.  They may not mutate scheduler attempts, phase
  state, last-known-good data or the quality-v2 operator result.
- One shared final input, requested bank, effective budget, stake, event order
  and deterministic seed are mandatory.
- No package may be exported after T-10.  No automatic wager is permitted.

## Candidate packages

1. `quality-v2`: unchanged operator control.
2. `quality-v3`: direct bounded-uncertainty candidate generation using BK,
   BK flattened 10%, and BK flattened 20%.
3. `sports-shadow`: quality-v2 package generation over a frozen, pre-kickoff
   sports probability artifact with event-local BK fallback.
4. `robust`: maximin selection from the union of eligible candidate coupons
   across the control, quality-v3 and sports-shadow packages, evaluated over
   BK, bounded-uncertainty and sports probability models.

## Experimental winner policy for 4993

The policy is predeclared before the final input exists.

1. Reject a candidate on identity/provenance mismatch, timeout, duplicate or
   malformed coupons, cost/capacity mismatch, incomplete sports evidence, or
   common package-safety failure.
2. Evaluate every eligible package under the same model set and exact category
   definitions: P13+, P14+, P15.
3. A challenger is promotable only when it does not reduce BK P13+, P14+ or
   P15 versus quality-v2 beyond numeric tolerance and strictly improves the
   worst-model P13+; concentration must not be worse than the control.
4. Among promotable candidates choose lexicographically by worst-model P13+,
   mean-model P13+, worst-model P14+, worst-model P15, then deterministic
   package hash.  If none qualifies, quality-v2 remains the winner.
5. Promotion is manual/experimental and requires a hash-bound record tying the
   exact winner policy, scheduler plan, final input, package and deadline.

This conservative rule prevents an unvalidated sports or robust model from
trading away the market-model category probabilities merely because it scores
well under its own assumptions.

## Implementation sequence

1. Add a common challenger evaluation/selection module with deterministic,
   coupon-free public reports and internal hash-bound package artifacts.
2. Add focused tests for fail-open isolation, identity/budget equality,
   selection ordering, safety rejection, timeout fallback and T-10 expiry.
3. Extend the existing final hybrid sidecar to include the canonical
   quality-v3 package and combined robust model set without changing the main
   scheduler.
4. Add a separate experimental manual promotion/export gateway.  The quality-v2
   operator result remains untouched; the gateway can export only the selected
   hash-bound winner before T-10.
5. Prepare a 4993 sports artifact and run a training comparison from the
   current immutable training input.  Install the challenger sidecar only after
   this succeeds.
6. Replay quality-v2 and quality-v3 on frozen pre-result inputs for 4990, 4991
   and 4992, then settle against the actual results.  Treat three drawings as a
   diagnostic, not proof of profitability.
7. Start Sports Analytics v2 behind the same shadow boundary: leakage-safe
   Elo/team strength, venue form, goals/xG where sourced, rest/congestion and
   availability features; immutable as-of provenance; calibrated residual
   blending around BK; per-event BK fallback.
8. Run focused tests, full pytest and Ruff.  Update memory-bank and commit
   locally.  Remote push requires separate approval.

## Verification evidence required before live installation

- Existing scheduler plan bytes and plan ID unchanged.
- Existing scheduler tests unchanged and passing.
- Challenger failure/timeout leaves quality-v2 operator result byte-identical.
- Training comparison completes within a bounded sidecar runtime.
- Selected winner record binds plan, input, budget, package, policy and T-10.
- Replays use only snapshots captured before each historical drawing result.
