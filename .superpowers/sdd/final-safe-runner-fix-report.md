# Final Safe Drawing Runner Fix Report

## Status

GREEN. All Important and Minor findings from `final-safe-runner-review.md` are
implemented and locally verified. Independent final approval remains pending.
The prospective 30-drawing/450-event gate remains `PENDING`.

## RED

The review recorded five Important failures: in-pass T-5 provider work,
post-complete actionable publication/interruption handling, computed-`NO BET`
coupon leakage, second-fetch target mutation, and preflight publication-path
protection. It also recorded the invalid 5000/30 example and stale plan/state
status. This handoff began after the corrective patch had been applied; it did
not replay a behavioral RED by reverting current user work. The original review
is the authoritative RED evidence.

## Implemented Corrections

1. **Strict in-pass T-5:** cutoff and injected UTC clock now cross the
   prospective collector/provider boundary. Schedule dates/pages, market
   requests/pages, and API-Sports retries recheck before work. Closure permits
   no later provider call, completes all 15 dispositions with explicit safety
   fallback where needed, persists the immutable pass, and records
   `stop_reason="safety_stop"`.
2. **Deadline/interruption-safe publication:** orchestration rechecks after
   `complete`; publication rechecks before actionable EV/runner artifacts.
   Child and runner artifacts share one outer `BaseException` transaction.
   Pre-commit interruption restores/removes every artifact; interruption after
   commit is treated as successful publication.
3. **No computed-`NO BET` leakage:** every runner `NO BET` omits the EV child
   report. A real `run-drawing` CLI threshold case confirms in-memory
   diagnostic top coupons do not appear in the manifest, Markdown, or linked
   coverage artifacts.
4. **Second-fetch target mutation:** package construction receives the expected
   `PinnedDrawing`, compares the one fresh EV payload before timing/heavy EV,
   and returns zero-cost coupon-free target-mismatch `NO BET` with
   `ev_run=None`. Structural corruption still fails.
5. **Preflight/input protection:** all possible coverage, EV, and runner paths
   are computed after target pinning and before waiting. Lexical/symlink
   collisions with database, aliases, cache root, or sibling outputs fail
   before provider construction. Report/cache writability and provider
   construction are probed; guards repeat before publication; every writer,
   including coverage reports, receives protected inputs.
6. **Documentation:** the stake-30 example now uses bank 4980. Completed plan
   steps are checked, stale ready-for-execution text is removed, and final
   independent approval remains explicitly pending.

## GREEN Regression Coverage

- T-5 boundary: `test_safety_stop_prevents_transport_retry`,
  `test_safety_stop_prevents_later_schedule_date_request`,
  `test_safety_stop_prevents_later_odds_page_request`,
  `test_safe_runner_stops_in_pass_after_market_request_reaches_cutoff`, and
  `test_safe_runner_stops_before_retry_when_collection_reaches_cutoff`.
- Publication: `test_complete_callback_reaching_cutoff_suppresses_actionable_result`,
  `test_publication_rolls_back_actionable_children_when_deadline_closes`,
  `test_publication_rolls_back_installed_children_on_runner_base_exception`,
  and `test_publication_treats_interrupt_after_transaction_commit_as_success`.
- Coupon suppression and target mutation:
  `test_run_drawing_cli_computed_threshold_no_bet_leaks_no_coupon_artifact`,
  `test_second_fetch_target_mismatch_is_coupon_free_no_bet`, and
  `test_safe_runner_refuses_second_fetch_target_mutation_without_starting_ev`.
- Path protection: `test_runner_preflight_rejects_db_output_collision_before_any_access`,
  `test_runner_preflight_rejects_symlink_alias_collision`,
  `test_runner_preflight_rejects_unwritable_output_roots_before_provider`,
  `test_coverage_writer_rejects_input_output_collision`, and
  `test_publication_rechecks_symlink_swap_before_replacing_inputs`.

## Verification

- Focused modified-module pytest: `200 passed in 2.81s`.
- Full pytest: `930 passed in 10.81s`; final repeat after documentation and
  memory updates: `930 passed in 11.92s`.
- Repository-wide Ruff: `All checks passed!`.
- `run-drawing --help`: exit 0.
- `collect-external-odds --help`: exit 0.
- `ev-package --help`: exit 0.
- `git diff --check`: passed.

Tests used no configured network, real sleep, or betting. Dynamic bank/stake,
category, probability, EV, consensus, timing, and coverage-gate definitions
remain unchanged; external consensus remains audit-only.

## Remaining Concerns

No known corrective implementation issue remains. Independent reviewer
approval is still required. The acceptance fixture intentionally uses a
reduced EV surface after capturing the real 15-event input; full-space EV
mathematics remains covered by the separate EV verification suite.
