# 5008 Sports-v3 same-engine replay-v2 independent review

**Task:** `TOTOAI-RESUME-20260915`  
**Verdict:** **PASS** — no P1/P2 findings; no code changes requested or made.

## Evidence reviewed

- `src/toto_ai/research/sports_v3_same_engine_replay.py`
- persisted research-only `.../5008-same-engine/replay-v2/` artifacts
- prior reproducibility handoff `5008-sports-v3-final-regression-and-repro.md`

The original hash-only run remains explicitly **not reproduced**. `replay-v2` is correctly marked `NEW_REPLICATION`; its selected hashes differ from the historical hashes and no original-selection claim is made.

## Independent artifact and runner validation

A local validator (without printing coupon strings or 5008 labels) verified all six persisted payload hashes against `hashmanifest.json`; all four source-byte hashes; frozen final-input, snapshot, and model bindings; and the persisted candidate/selected artifacts.

- candidate universe: **293 unique** 15-symbol `1/X/2` coupons;
- both selections: **166 unique** 15-symbol coupons from the same universe;
- settings: category 13, 10,000 samples, declared selector seed, flatten `[0.1, 0.2]`, `exposure_constraints=null`, and no fallback arm;
- frozen matrices: 15 rows each, 12 `SPORTS_APPLIED` / 3 `BK_FALLBACK`; common fallback status is recorded;
- all artifacts are `research_only=true`, `operator_compatible=false`, `automatic_wagering=false`; saved coupons are JSON analysis arrays and contain no semicolon upload encoding.

The real runner rejected the populated `replay-v2` directory before writing. It then performed four fresh isolated replays only:

- `.../review-isolated-replay-a` and `.../review-isolated-replay-b` establish behavior with absolute caller paths;
- `.../review-isolated-replay-c` and `.../review-isolated-replay-d` replayed from the persisted relative source-path spelling and are byte-identical to each of the six persisted replay-v2 payloads and manifest values.

The A/B `inputs.json` differs only because the module faithfully records caller path spelling (absolute rather than the persisted relative spelling); source content hashes, selections, comparison, and all C/D canonical replay bytes validate. This is not a silent overwrite or a result divergence. The callable function accepts explicit paths, has no runtime/operator dependency, and the persisted relative paths replay from the repository root.

Ruff on the reviewed module passed.

## Exact fixed-package P(13+)

| Fixed package | COMMON_BK | COMMON_SPORTS_V3 |
|---|---:|---:|
| BK | 0.0149405241 | 0.0205591630 |
| SPORTS_V3 | 0.0143227176 | 0.0214419447 |

These are exact conditional values under named frozen matrices only—not empirical performance, calibration, profitability, production eligibility, or a wagering recommendation.

## Limitations retained

`maximum_outcome_share=1.0` is a recorded concentration warning, not an exposure constraint or acceptance result. The universe is the fixed 293-coupon top-product union, not the production 14,140-candidate quality-v3 generator. No outcomes/labels were read; no refit, core-math, runtime, DB, gate, consent, operator, or publication action occurred.
