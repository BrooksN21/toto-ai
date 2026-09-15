# Shared90-minute GOAL history fix — implementation ready, independent review pending

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906; saved 2026-09-06T15:56:42.305943+03:00. **Not ACCEPT / not activated / not published.**
Source: `goal_probe_research._load_history_snapshot`, shared by V1 and explicit V2.
AET/PEN use complete valid FtScore only; missing/invalid FT emits explicit skip reason.
FINISHED score contract retained; raw/team/chronology/provenance unchanged; duplicate
identities fail closed. No `goal_probe_collection.py`, CLI, comparison/sidecar change.

Exact5 candidate paths:
- `src/toto_ai/sports_stats/goal_probe_research.py` — `73f2c05dd2f2a4f417f12fcffbd431cbdece1c08ab7ad629575786fb5143c93e`
- `tests/test_goal_probe_research.py` — `c0cf0f854b8614757dc16fa13a954191b2294acbc27b12e05d2a980cb3fed292`
- `tests/test_goal_history_regulation_score.py` — `e02ef14e70b01711d1322df4b99a9212ed3a1bf36a1ff0c21b3f266f2c841579`
- `tests/fixtures/goal_regulation_score_captured_contracts.json` — `eb4ac9b13d60df79091961c317c7b40fe6c45921bc0926a728cb411aced27d18`
- `knowledge/goal_history_regulation_score.md` — `4920647dac30eecc840e162a11e463177ddecd2558cec90408523b5c81d4fecb`

Patch `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/history-90min-implementation.patch` SHA256 `dc150fdc3ccd10fdbc9280b97ff99974248f233add7dda1a668947a75e011275`. Before/source/after hashes in `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/history-90min-implementation-receipt.json`.
RED:2 real captured mismatches failed0.39s. GREEN final:81PASS1.05s (70new+11existing);
Ruff3PASS. No tests excluded. Earlier green81/1.47s retained as historical evidence.
Corrected V2 seed `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-quarantine-refresh-20260906T115118375156Z/sports-v2-regulation90-pending-review/sports_probability_shadow_4998_ac04ea9b30359094.json`
fileSHA `2d5003c79378fb0b5f425ddf8cfdc0902327e727c0c0f3bb43843b43f2139e78`; artifactSHA `ac04ea9b303590945dbdc3c12a451840d300350b641593f5cf07b74054d5f32e`.
14/15coverage;280/280observations; excluded0;13AET/PEN exactlyFT;28team goals/WDL
aggregates independently matched. Event9 remains BKfallback. prior3/cap0.2, UNTRAINED_V2.
Proof `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-quarantine-refresh-20260906T115118375156Z/sports-v2-regulation90-pending-review/REGULATION90_PROOF.json`; same capture/as_of, no new API/DB/operational generation.
All19 protected paths unchanged; old pinned and contaminated research seeds retained.
No owned process; no activation/push. Reviewer next: exact5paths+FT contract/proof;
activation/publication only as separately authorized next jobs after ACCEPT.
Requested10min window missed; no continuous-work claim for15:06–15:53gap.
