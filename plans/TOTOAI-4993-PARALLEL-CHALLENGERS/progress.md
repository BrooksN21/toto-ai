# Progress

## Completed

- Kept the primary 4993 quality-v2 scheduler unchanged and verified its loaded
  LaunchAgent.
- Implemented deterministic quality-v2 / sports-shadow / quality-v3 / robust
  comparison and non-degradation selection.
- Added a separate plan-bound, manually authorized pre-T-10 companion release;
  automatic wagering remains disabled.
- Loaded the isolated 4993 sidecar for 16:30 MSK.
- Replayed equal-cost quality-v2/v3 on 4990 and 4991; generated pending 4992.
- Started Sports Analytics v2 with conservative goal/venue features.

## Current evidence

- 4990 actual best hits: quality-v2 11, quality-v3 9.
- 4991 actual best hits: quality-v2 11, quality-v3 11.
- 4992 results are not terminal yet.
- 4993 GOAL sports coverage: 11/15, four event-local BK fallbacks.
- Current 4993 training selector outcome: quality-v2. Sports reduced BK model
  metrics; quality-v3 and robust failed the concentration non-degradation gate.

## Remaining

- Observe the live 4993 final/T-10 sidecar output.
- Settle all four 4993 candidates after terminal results.
- Persist and walk-forward test Sports Analytics v2 before activation.
