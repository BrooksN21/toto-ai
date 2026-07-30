# TotoAI Data Health

- Contract version: `1.1.0`
- Report schema: `2`
- Use case: `historical_inventory`
- Strict: `false`
- Exit status: `pass`
- Drawings: 13
- Healthy: 0
- Unhealthy: 13
- Gaps: 0
- Duplicate visible numbers: 0

## Inventory counts

| Metric | Count |
|---|---:|
| event_rows | 195 |
| finished_drawings | 13 |
| finished_incomplete_result_drawings | 8 |
| missing_terminal_results_in_finished | 92 |
| valid_pool_drawings | 10 |
| complete_bk_drawings | 10 |
| raw_snapshot_drawings | 6 |
| result_snapshot_drawings | 0 |
| actionable_package_drawings | 0 |
| unsettled_actionable_package_drawings | 0 |
| reconciliation_tracked_drawings | 0 |
| reconciliation_cooldown_drawings | 0 |
| reconciliation_quarantined_drawings | 0 |
| reconciliation_complete_drawings | 0 |

## Use-case totals

| Use case | Healthy | Unhealthy |
|---|---:|---:|
| historical_inventory | 0 | 13 |
| backtest_probability | 3 | 10 |
| result_settlement | 0 | 13 |
| prospective_generation | 10 | 3 |

## Selected-use-case reasons

| Reason | Drawings |
|---|---:|
| all_results_missing | 6 |
| empty_event_names | 3 |
| incomplete_bk | 3 |
| incomplete_results | 2 |
| missing_quotes | 3 |
| missing_raw_snapshot | 7 |
| missing_result_snapshot | 13 |

## Metadata

- Gaps: none
- Duplicates: none

## Drawing detail

| Number | ID | Status | Health | Reasons | Events | Pool | BK | Results | VOID | Reconcile state | Attempts |
|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|---:|
| 4946 | 11955 | finished | unhealthy | incomplete_results, missing_raw_snapshot, missing_result_snapshot | 15 | 15 | 15 | 14 | 0 | - | 0 |
| 4947 | 11957 | finished | unhealthy | missing_raw_snapshot, missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4948 | 11959 | finished | unhealthy | missing_raw_snapshot, missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4949 | 11962 | finished | unhealthy | all_results_missing, missing_raw_snapshot, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4950 | 11964 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4951 | 11968 | finished | unhealthy | all_results_missing, missing_raw_snapshot, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4952 | 11970 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4953 | 11972 | finished | unhealthy | missing_result_snapshot | 15 | 15 | 15 | 15 | 0 | - | 0 |
| 4954 | 11975 | finished | unhealthy | empty_event_names, missing_quotes, incomplete_bk, incomplete_results, missing_result_snapshot | 15 | 0 | 0 | 14 | 0 | - | 0 |
| 4955 | 11977 | finished | unhealthy | empty_event_names, missing_quotes, incomplete_bk, missing_raw_snapshot, missing_result_snapshot | 15 | 0 | 0 | 15 | 0 | - | 0 |
| 4956 | 11981 | finished | unhealthy | empty_event_names, missing_quotes, incomplete_bk, missing_raw_snapshot, missing_result_snapshot | 15 | 0 | 0 | 15 | 0 | - | 0 |
| 4957 | 11983 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
| 4958 | 11986 | finished | unhealthy | all_results_missing, missing_result_snapshot | 15 | 15 | 15 | 0 | 0 | - | 0 |
