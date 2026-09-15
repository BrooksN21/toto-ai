# R1 — final implementation receipt

Task: TOTOAI-RESUME-20260915. Updated: 2026-09-15T20:44:25.843909+03:00.

## Completed
- All8drawings4999–5006 completed; 3variants ×8drawings =24 frozen packages. Each166coupons, bank4980 ₽, stake30 ₽.
- Generation747seconds (exact747.0977929180008); no regeneration after reporting correction.
- Read-only scoring ran only after all packages were frozen and hash-bound. No13+ package. Robust matched the quality-v2 coupon set in5/8:4999,5001,5003,5004,5006. Equality does not prove a native fallback reason.
- M1 fixed: set comparison separate from order equality; original coupon order/file bytes/hashes preserved. Regression PASS.
- Final focused verification:52passed,1deselected,1.34s; Ruff PASS. Heavy real-surface test passed previously and independently. This receipt-only step ran no tests/generation/scoring.

## Actual maximum hits per166-coupon scenario package
|Drawing|quality-v2|quality-v3|robust-market-only|
|---|---:|---:|---:|
|4999|10|10|10|
|5000|12|12|12|
|5001|10|9|10|
|5002|10|10|10|
|5003|11|11|11|
|5004|10|9|10|
|5005|11|10|11|
|5006|11|10|11|

## Evidence boundaries
- POST_EVENT_MARKET_SCENARIO_UNVERIFIED_ASOF: quote availability remains unknown. This is not a prospective or causal historical backtest, not a fit dataset, and not an operator package. ROI unknown, not zero.
- **Original4999 true predraw archive:max11; new4999 closed-snapshot scenario:max10. These are different inputs. The original archived result has not been overwritten or rechecked.**
- sports-shadow and Sports-v3 were not run; missing sports input/fit must not be represented as a fifth evaluated model.
- Original generation manifest retained. Comparison records original generation_code separately from current scoring_code. No live code/scheduler/DB/consents/Git changes.

## Source/test scope
- `/Users/turshevr/toto-ai/src/toto_ai/research/closed_market_scenario_replay.py`
- `/Users/turshevr/toto-ai/tests/test_closed_market_scenario_replay.py`

## Results
- [manifest.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/closed-market-scenario-v1/manifest.json)
- [comparison.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/closed-market-scenario-v1/comparison.json)
- [comparison.md](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/closed-market-scenario-v1/comparison.md)
- [comparison.csv](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/closed-market-scenario-v1/comparison.csv)
- [summary.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/closed-market-scenario-v1/summary.json)

## Remaining handoff
- Independent generation review PASS. M1 correction awaits independent recheck, then separate finalizer publication and canonical-memory update.
- No owned generation/scoring process remains. Sessions95602,54818 and final verification11959 completed exit0. No further commands after this receipt update.
- Prior partial checkpoint/hashes preserved as historical evidence in the companion JSON; finalizer must hash current source before publication.
