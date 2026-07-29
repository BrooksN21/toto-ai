# TOTO-AUDIT-4952 context

Collected locally only on 2026-07-23 (Europe/Moscow); no network, settlement, source edits, Git, or backtests.

## Exact drawing / SQLite
- DB: `/Users/turshevr/toto-ai/data/toto.db` (opened read-only with sqlite3).
- Drawing: visible **4952**, internal id **11970**, status `finished`, `ended_at=2026-07-22T16:00:00.000000Z`, `pool_sum=9282304.0`, `jackpot=14166529.0`.
- SQLite has 15 events (orders 0..14), but **0/15 results populated** (`result` and `score` blank). No SQLite package, payout, or settlement tables were present; schema includes drawings/events/quotes/preparation only.
- Preparation row: id 1, status `ready`, mapped_count 15, unresolved `[]`, eligibility `playable`; created `2026-07-22T10:06:20.859942+00:00`, updated `2026-07-22T10:44:32.886167+00:00`.

## Morning / scheduler evidence
- Morning preliminary artifacts inspected under `/Users/turshevr/toto-ai/reports/rehearsal/morning-4953/`; stdout repeatedly reports TotoBrief sync success from cache, then 4953 `unresolved`, `mapped_count=0`, `eligibility_status=unknown`, all event orders unresolved. stderr empty.
- 4952 scheduler plist: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/totoai-scheduler.plist`; scheduled 2026-07-22 18:15 Moscow, RunAtLoad false, wrapper `run-scheduler.sh`, logs `logs/scheduler.stdout.log` and `logs/scheduler.stderr.log`.
- Scheduler log records an earlier FAILED preflight due to missing `/data/raw/drawing_11970.json`; later local emergency-final artifacts exist.

## Final 166-coupon / 4980 RUB package
- Exact upload text: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/emergency-final/baltbet_package_4952_4980.txt`.
- File mtime `2026-07-22T18:49:36+0300`, 166 non-empty coupon lines; each starts with stake `30`, so 166*30 = **4980 RUB**.
- Associated final report: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/emergency-final/ev_package_4952_playable_bank_4980.md` (mtime `2026-07-22T18:47:23+0300`): decision `PLAY`, selected 166, cost 4980, unused 0, modeled expected payout `251036.219120874302`, modeled ROI `49.408879341541`; explicitly modeled, not observed.
- Run JSON: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/emergency-final/drawing_run_4952_20260722T160000Z_562dae935596.json`; terminal reason `EV package selected playable coupons`, finished `2026-07-22T15:47:23.632844+00:00`, target internal id 11970 / visible 4952, schema 4.
- Other audit/research copies exist under `reports/final-acceptance-4952`, `reports/final-p2-acceptance-4952`, and `reports/current-systematic-research-4952-20260722T105232Z`; they also report coupon_count 166, but are not settlement evidence.

## Settlement/results completeness
- **Incomplete / absent.** No local settlement/payout output was found by filename search; no settlement/payout CLI or implementation occurrence was found in `src`, `tests`, or `README.md` (apart from generic payout math in `src/toto_ai/ev/reference.py`). SQLite has no populated 4952 results, hence no observed payout/profit/ROI can be computed.

## Exact safe next command (not run)
For read-only synchronization diagnostics only, from repository root:
```bash
.venv/bin/python -m toto_ai.cli sync-prepare --open --sync-only \
  --db data/toto.db \
  --raw-cache-dir data/raw \
  --totobrief-rate-state data/totobrief-cache/request-state.json
```
This is explicitly documented as “synchronize and validate TotoBrief only; do not write preparation/pins.” Do **not** run settlement: no safe local settlement command exists in the inspected CLI/source, and settlement was intentionally not performed.
