# TOTOAI-RESUME-20260915 — operational context (read-only worker)

## Immediate priority
- **Current drawing5007 / API+DB12127; closes15 September20:00MSK =17:00UTC.** Expected operator T-10 is19:50MSK, but no new plan exists to bind it yet.
- Independently inspected existing fresh `data/raw/drawing_12127.json` + `.meta.json`: source=collector-network, fetched_at2026-09-15T13:23:19.827215+00:00, rawsource statusactive, started_atnull, ended_at2026-09-15T20:00:00.000000Z. Metadata payloadSHA b3e575638081c14a5f47efd19ac3e1f069bae0257db558e117d9f3267a813817 (hash not independently recalculated in this bounded context pass). This is a fresh native network capture, NOT this worker's successful request.
- `src/toto_ai/totobrief_time.py` explicitly interprets Baltbet serialized clocks as Europe/Moscow despite Z. Do not convert20:00rawZ into23:00MSK. Native identity agreesdeadline17:00Z.
- Fresh native state `data/scheduler/morning-dispatch/drawing-12127-20260915T170000Z-bf59ff77d5bb3667.json` at16:23:26.935MSK: deferred / ACTION REQUIRED: unresolved15/15; mapped0, externalcoverage0, eligibilityunknown, span_daysnull, plan_id/pathnull. API-Sports diagnostics: account suspended Sep14–16 and free-date restrictions Sep17–19. No assertion other sources are unavailable.
- Exact fingerprint bf59ff77d5bb3667e1f42e13904219bdf4235c9f92454e04b8502d7d1d6dc80e; detailSHA9f3657586713a1566a769e97e588ed82b0a1c87e6deee7e7cba4fea1cef58b87.
- **Already-running native morning dispatcher PID7678**, `/bin/sh /Users/turshevr/toto-ai/reports/rehearsal/morning-dispatcher-v10-parallel-safe/run-morning-preanalysis.sh`. It retries non75/non3 failures at60s up to2retries. Do not start duplicate dispatcher or hold its locks externally. PID observed about16:25; recheck only before potential conflicting action.
- Own public GET https://totobrief.com/api/v1/community/baltbet-main/drawings?page=1 failed requests.ConnectTimeout(timeout12); no retry or TLS bypass. Webtool open also failed. Do not diagnose worldwide provider outage from this; native job fetched successfully at16:23.

## Database and missing history
Canonical SQLite `/Users/turshevr/toto-ai/data/toto.db`, SQLAlchemy sources under src/toto_ai; read via sqlite URI mode=ro. 2247drawings, sole community baltbet-main, maximum5007. Relevant tables drawings(id,number,name,status,pool_sum,jackpot,started_at,ended_at), events(id,drawing_id,event_order,name,championship,sport,result,score,result_status), quotes; drawing_result_snapshots, archived_packages, package_settlements, drawing_raw_snapshots, sports_stats_runs, sports_event_feature_snapshots, drawing_preparations/pins.

|number|DBid|status|events|nonempty results|
|--|--|--|--|--|
|4999|12106|finished|15|0|
|5000|12107|finished|15|0|
|5001|12110|finished|0|0|
|5002|12113|finished|0|0|
|5003|12116|finished|0|0|
|5004|12119|finished|0|0|
|5005|12121|finished|0|0|
|5006|12124|finished|0|0|
|5007|12127|active|15|0|

No missing summarynumbers4999–5007, but eight finished drawings have absent outcomes and six have absent events. Latest complete result snapshot4998,15events, actual12X1XXXX1111121, retrieved2026-09-07T08:35:25.368016+00:00. Statusfinished alone is NOT result completeness. Do not infer cancellation from empty results/score. Never manually inventvoid.

## Frozen model evidence
Within inspected canonical rehearsal root only evening-4999-20260907T143000Z exists for4999plus; no evening-50* directories. DBarchived_packages>=4999 contains ONE166coupon4980pre_bet_runner archive for4999 at `/Users/turshevr/toto-ai/reports/rehearsal/evening-4999-20260907T143000Z/attempts/final-01-20260907T140002186014Z-7d26d25c/package.csv`.
4999 parallel artifacts exist under that root/parallel-challenger/output (not evaluated or hashvalidated here). No frozen operator archive5000–5006 found in DB or canonical evening roots. Thus postmortem4999 can use archived inputs; new backward generation on laterdraws is retrospective research, not pre-draw forecasting performance. Before modelreplay inspect pre-cutoff raw/sports availability and leakage safeguards using project-local totoai-backtesting skill. Do not claim SportsV3 deployed: memory still says isolatedF4accepted, no realfit/integration/70%gateproof. Existing sidecar familiesquality-v2,sports-shadow,quality-v3,robust. No replayrun here.

## Existing jobs / consent
launchctl list: morning-dispatcher.v1 PID7678; nightly-reconciliation.v1 idle; old4999 primary+parallel+watcher loadedidle, other historicallabels remain. Old5000preflight-retry.12107.93785ccf917d4882 loadedidle. No5007plan/label established. Do not copy oldplan consent. Owner4999authority expiredSeptember7; current5007needs fresh exactplan/bank/stake pre-cutoff authorization before PLAY. No heartbeat; local watcher cannot wake idle chat.

## Exact safe next commands for operations owner (NOT executed)
Always cwd `/Users/turshevr/toto-ai`; commands below use `.venv/bin/python -m toto_ai.cli`. Run bounded with visible supervision; no blind retries.
1. First inspect current dispatcher/state and avoid duplicate preparation. Current-source cache alreadycaptured; don't immediatelyrefetch unchangeddata. Resolve5007timing/identity using native `collect-schedule-sources` and schedule-evidence workflow; inspect commandhelp beforeflags. No fake approvals/sourceprovenance. Today's15unknowns are first operational blocker.
2. Historyselection preview: `.venv/bin/python -m toto_ai.cli reconcile-finished --db data/toto.db --from-drawing 4999 --to-drawing 5006 --batch-size 8 --dry-run` (no network by command contract).
3. Once no competing DBreconciliation owner: samecommand `--apply --max-attempts 1` instead ofdry-run. No --force unless explicitly justified; default preservescooldown/quarantine. WritesDB/raw/state. Capture exit2 partialfailure honestly. Alternative precise individual recovery: `.venv/bin/python -m toto_ai.cli sync-finished-results --drawing-id 12106 --db data/toto.db` (then explicit IDs above asneeded). Do not execute both routes redundantly.
4. Native5007preparation after genuine readiness, no active dispatcher: `.venv/bin/python -m toto_ai.cli morning-dispatch --bank 4980 --stake 30 --env-file /Users/turshevr/toto-ai/.env --project-root /Users/turshevr/toto-ai --state-root /Users/turshevr/toto-ai/data/scheduler/morning-dispatch --scheduler-root /Users/turshevr/toto-ai/reports/rehearsal --db /Users/turshevr/toto-ai/data/toto.db --aliases /Users/turshevr/toto-ai/data/external-odds/team-aliases.json --schedule-evidence-ledger /Users/turshevr/toto-ai/data/schedule-evidence/ledger.json --expected-drawing-id 12127 --expected-drawing-number 5007 --expected-fingerprint bf59ff77d5bb3667e1f42e13904219bdf4235c9f92454e04b8502d7d1d6dc80e --expected-deadline 2026-09-15T17:00:00Z --python-executable /Users/turshevr/toto-ai/.venv/bin/python --activate --goal-shadow-auto --parallel-challenger-auto`. Validate identity fresh after relevantmutation; no parallel-release-auto until consent.
5. Only actual generatedplan: `scheduler-preflight-only --plan <actualpath>` (realdata isolated check; no claimPASSbeforecompletion), `scheduler-status --plan <actualpath>`; canonical watcher `scheduler-status-watch --plan <actualpath> --latest <actualroot>/status-watch/latest.json --history <actualroot>/status-watch/history.jsonl --interval-seconds 30`. These watchflags verifiedCLI. LaunchAgent setup must use native preparedartifact+ordinaryOSapproval, not inventedplanid or copiedcalendar. Exact current plan/jobspec absent today; do not pretend installed.
6. Archivedsettlement aftercomplete snapshots: `settle-drawing --drawing-number 4999 --package-file <verifiedarchivedfile> --stake 30 --db data/toto.db`. For fourmodel comparison, bind exactfrozen sidecars/inputs beforeevaluating; payouts require actualsettlementevidence, not guessedcoefficients.

## Boundaries / handoff
Read ACTIVE_PLAN firsttop checkpoints, rootAGENTS, targeted coordination rolefields andoperationalhandoff. Parent019f7afa-72e2-7403-85cd-d05f408a4ef3 ownsproduction; two historicaluserownedreview/modeltasks remainisolated. Contextworker makes NOoperations/code/memory/Git/DB/job/secretchanges; onlythisfilewrite. Existing memorylatestcheckpoint isSeptember7 and is stale forruntime; preserveunfinishedchecklist, don't restart fullaudit. No newnestedagents/modelcalls. Timing investigation extended beyond3min duecommandlatency and networktimeout; immediate blocker delivered separately. No success/publishing/runtimeverification claimed beyond facts above.
