# TotoAI Data Health

- Contract version: `1.1.0`
- Report schema: `2`
- Use case: `result_settlement`
- Strict: `false`
- Exit status: `pass`
- Drawings: 13
- Healthy: 3
- Unhealthy: 10
- Gaps: 0
- Duplicate visible numbers: 0

## Inventory counts

| Metric | Count |
|---|---:|
| event_rows | 195 |
| finished_drawings | 13 |
| finished_incomplete_result_drawings | 7 |
| missing_terminal_results_in_finished | 77 |
| valid_pool_drawings | 12 |
| complete_bk_drawings | 12 |
| raw_snapshot_drawings | 9 |
| result_snapshot_drawings | 3 |
| actionable_package_drawings | 0 |
| unsettled_actionable_package_drawings | 0 |
| reconciliation_tracked_drawings | 4 |
| reconciliation_cooldown_drawings | 1 |
| reconciliation_quarantined_drawings | 0 |
| reconciliation_complete_drawings | 3 |

## Use-case totals

| Use case | Healthy | Unhealthy |
|---|---:|---:|
| historical_inventory | 3 | 10 |
| backtest_probability | 6 | 7 |
| result_settlement | 3 | 10 |
| prospective_generation | 12 | 1 |

## Selected-use-case reasons

| Reason | Drawings |
|---|---:|
| all_results_missing | 5 |
| incomplete_results | 2 |
| missing_result_snapshot | 10 |

## Metadata

- Gaps: none
- Duplicates: none

## Drawing detail

| Number | ID | Status | Health | Reasons | Events | Pool | BK | Results | VOID | Reconcile state | Attempts |
|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|---:|
| 4946 | 11955 | finished | unhealthy | incomplete_results, missing_result_snapshot | 15 | 15 | 15 | 14 | 0 | cooldown | 1 |
| 4947 | 11957 | finished | unhealthy | missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4948 | 11959 | finished | unhealthy | missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4949 | 11962 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4950 | 11964 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4951 | 11968 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4952 | 11970 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4953 | 11972 | finished | unhealthy | missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4954 | 11975 | finished | unhealthy | incomplete_results, missing_result_snapshot | 15 | 0 | 0 | 14 | 0 | - | 0 |
| 4955 | 11977 | finished | healthy | healthy | 15 | 15 | 15 | 15 | 0 | complete | 1 |
| 4956 | 11981 | finished | healthy | healthy | 15 | 15 | 15 | 15 | 0 | complete | 1 |
| 4957 | 11983 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4958 | 11986 | finished | healthy | healthy | 15 | 15 | 15 | 15 | 0 | complete | 1 |
