# GOAL history regulation-score normalization

The shared GOAL research history importer (`goal_probe_research._load_history_snapshot`)
feeds both V1 evidence and the explicit native Sports Analytics V2 projection.
AFTER_ET/AFTER_PEN history uses only the complete `homeTeamFtScore`/`awayTeamFtScore`
pair for football W/D/L and goals. Generic `*Score`, `*ExtraScore`, and `*PenaltyScore`
are not alternatives or reconstruction inputs. Missing/null FT skips the observation
with `regulation_score_missing`; malformed/ambiguous/bool/negative FT skips it with
`invalid_regulation_score`. Existing canonical nonnegative integers/numeric strings
are accepted. FINISHED retains its existing valid generic-score contract.

Raw evidence bytes and payload provenance are unchanged. Duplicate fixture identity
remains fail-closed (including conflicting FT observations); team, target exclusion,
terminal status and strict chronology checks remain. All-skipped usable history takes
the existing per-event BK fallback; no invented scores or probabilities.

2026-09-06 implementation:70 new focused cases include13 exact local captured AET/PEN
observations (12 generic-vs-FT mismatches); with existing GOAL/V2 regressions81PASS,
Ruff3PASS. Corrected frozen research seed14/15+1fallback;280 observations retained,
13 use explicit FT;28 team goals/WDL aggregates verified against independent FT sums.
This candidate still requires independent review; it is not activated/trained/profit
validated. No live plan/jobs/pinned seed changes. Exact evidence and hashes:
`plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/history-90min-implementation-receipt.json`.
