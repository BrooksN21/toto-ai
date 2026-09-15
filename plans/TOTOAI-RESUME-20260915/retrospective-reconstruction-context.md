# Retrospective reconstruction: actual local data, not another implementation plan

Task **TOTOAI-RESUME-20260915**; delegated CONTEXT-only worker, cwd `/Users/turshevr/toto-ai`. Fresh SQLite `mode=ro` + `query_only` queries, exact archived RAW reads, existing B/C receipts and current narrow API inspection. No network, generation, fitting, Git, livejobs, consent or DB writes. Only this MD + adjacent JSON written. Observed time and full source/file hashes are in JSON.

## Decision for the separate planner
**The market data exist for all eight drawings. Missing old captures does NOT make all retrospective reconstruction impossible.** All eight imported finished payloads contain15 positive BK triples,15 positive crowd triples, pool and jackpot, event identity/order and15 target outcomes. All eight archive byte SHA256 values match their DB payload SHA256. Numeric data could drive a common-bank **post-event-source scenario experiment** after a dedicated outcome-blind reconstruction adapter is reviewed. Current software does not yet accept this data class; no such eight-draw generation happened in this job.

**Do not confuse feasible computation with verified ex-ante performance.** For5001–5006 the only checked native snapshots were fetched15Sep, after the draws. Quotes have no observation timestamp, market status/is-closing marker or historical change log. It is UNESTABLISHED whether they are frozen pre-match closing quotes or later values. Thus these arrays may be evaluated as explicitly `POST_EVENT_MARKET_SCENARIO_UNVERIFIED_ASOF` (proposed label, NOT a native accepted domain), but not as leakage-free historical predictive evidence. Simply removing result fields does not prove the remaining quotes are causal. Obtaining trusted closing-market provenance would upgrade this classification; missing prospective capture alone need not block a separate reconstruction protocol.

## Fresh per-drawing inventory

|Draw|DB ID|BK triples|Crowd triples|Optional norm decimal triples|Active RAW records*|Sports runs / best complete events|Finished pool ₽|
|---|---|---|---|---|---|---|---|
|4999|12106|15/15|15/15|10/15|41|21 / 13|6,095,775|
|5000|12107|15/15|15/15|9/15|9|0 / 0|6,876,692|
|5001|12110|15/15|15/15|9/15|0|0 / 0|5,994,413|
|5002|12113|15/15|15/15|14/15|0|0 / 0|5,888,193|
|5003|12116|15/15|15/15|14/15|0|0 / 0|8,068,257|
|5004|12119|15/15|15/15|13/15|0|0 / 0|7,655,725|
|5005|12121|15/15|15/15|15/15|0|0 / 0|7,378,887|
|5006|12124|15/15|15/15|13/15|0|0 / 0|7,068,713|

*Active record count is lifecycle state, not automatic proof each capture precedes the required cutoff.4999 has42 total records,5000 has10;5001–5006 each have1. All15 event `start_at` values are null in every checked finished RAW. `pin_*` values are absent for all120events. RAWquote keys and complete paths/timestamps are saved in JSON. `norm_*` is an optional odds-shaped field, not a verified replacement for BK probabilities; do not fill its gaps with invented margins.

- All8 draw-result snapshots are `complete=1`,15events, retrieved15Sep13:32:15–13:32:29UTC. Payments are null throughout; economic ROI cannot be measured from these inputs alone. Target labels are already in `events` and separate `drawing_result_snapshots`: no need to recollect results.
- SQL `quotes` has BK/crowd/norm/pin columns but no quote-time columns; use immutable RAW+metadata, not mutable latest quote rows, as experiment inputs.
-4999/5000 finished six-column BK/crowd matrices DIFFER from the latest respective active matrices. This alone does not establish outcome-dependent updates: elapsed legitimate market movements also suffice. It disproves treating the two snapshots as the same input without checking.
- Finished pools are5.88–8.07million; each comfortably clears the numeric1% cap for4980/166, using that finished-pool scenario. That does not reconstruct the actual earlier pool. The verified5000 early input had pool78748 and is capped780/26. **Never call its prior26coupon run a4980/166 result.** If keeping mixed genuine early sources, choose common780 across arms/draws or separate cohorts; if using finished sources at4980, all arms must explicitly share that different retrospective scenario.
- BaltBet `ended_at` serialized `Z` uses native Moscow interpretation; per-event kickoff is missing here. Sports reconstruction needs separately verified fixture times/IDs, not drawing closure substituted as kickoff. Feature cutoff must be the historical package-decision time (before bets close), not just target kickoff when a match starts later.

## Five variants: exact ability today

|Variant|4999|5000 genuine early input|5001–5006 finished-source data|
|---|---|---|---|
|quality-v2|166coupon frozen archive and genuine input already evaluated; B2 proves case-specific ordered native parity|Actual26coupon B2 run complete|All required market columns present; needs reviewed retrospective admission + RAW→surface binding; current strict loader rejects finished capture|
|quality-v3 (package optimizer)|Frozen166coupon archive evaluated|Actual26coupon B2 run complete|Same numeric feasibility/admission issue; not Sportsv3 probabilities|
|robust|Frozen archive exactly equals control; full sidecar had sports input|Actual market-only native robust math; equals control, fallback/optimum reason not exposed|Market-only variant possible, must be named so; full sports-composed robust not possible until sports input exists|
|sports-shadow (SportsV2 hybrid)|Genuine pre-draw13/15 sports coverage +2 explicit fallbacks; frozen V2 binding validated in C receipt|No drawing-specific sports runs/features|No drawing-specific sports runs/features; zero-weight BK substitution would not establish a sports-model test|
|Sports v3 trained|Inert fit/inference code accepted; no accepted trained predictor/15-event fit-ready corpus in existing handoffs|No fit-ready sports inputs/model|Same missing history/identity/scope and fit/evaluation contracts; not a runnable fifth trained arm|

B-raw-adapter.md is an OLD blocked checkpoint; **B2-native-replay.md supersedes it** for bounded numeric generation. B2 actually ran5000,139.53s total, quality-v2=10best hits,quality-v3=9,robust-market-only=10; sports armsSKIPPED.27focused tests and frozen4999parity are prior recorded evidence, not newly rerun tests. Equivalence remains case-specific, not universal. `research/native_quality_core.py` takes caller-supplied EVSurface; high-level binding must tie that surface to the exact sanitized input/config. No live generator/provenance change is needed merely to design this isolated boundary.

Current `research/raw_package_replay.py:112–213` requires genuine active capture, empty result/score sentinels and capture strictly before historicalT−10. Existing `prepare`/`generate` CLI cannot be pointed at imported finished RAW and honestly succeed. A **different explicitly retrospective source contract/adapter**, with real capture time retained, is a concrete software task—not permission to relabel raw active, backdate or disable live guards. Do not substitute budget-oracle or plain EVtopN for native families.

## Sports history that actually exists

- Canonical `sports_stats_runs`:4999 has21GOAL runs,06Sep18:09:33UTC through07Sep14:20UTC; maximum13complete event histories. `sports_event_feature_snapshots` has315rows (21×15),13distinct mapped home IDs/13away IDs, not315independent matches. No runs/feature rows for5000–5006; exact `reports/sports-analytics/<draw>` dirs also absent for those7draws. Other-drawing caches were not globally enumerated; reuse coverage is UNCONFIRMED, not impossible.
- Accepted C source-validation receipt contains26original4999 team-history captures /260rows /13paired targets, genuinely collected06Sep; another24captures/240rows concern5007 collected15Sep. The later C envelope/bridge acceptance is narrower:24archives /12target events of4999, remaining target orders9/12/14 per later publication handoff. These are different acceptance stages, not contradictory coverage counts. Scope is still unknown, reliability0,53feature/full-fold gate not passed. Source hashes and captured-time summary are in adjacent JSON and linked receipt.
-5007 histories can contain earlier games useful for older targets, but are not automatically suitable: first exact canonical team-ID join, then exclude the target fixture and all games not finished/available before the historical decision cutoff; retain only verified regulation90 scores. Do not join by similar names or use later standings. No5000–5006 reuse coverage was established in this bounded pass.
- Existing C feasibility sample proves GOAL `/v1/teams/{team_id}/results?limit=10` returned dated IDs/teams/kickoff/status/FT90scores/createdAt/updatedAt. Fresh15Sep sample for4999Elche/RealSociedad retained8prior games per team after excluding target and later match. Several rows updated12Sep: possible later corrections, not proof scores changed. Last10 endpoint loses older rows as time passes; dated pagination is not verified. No new provider requests here. This is concrete partial historical source availability, not a promise to recover120/120events.
- Numeric blockers: missing exact target mappings/times for seven draws; full prior windows, opponent histories, historical season standings, market margin. Some core features can be computed from dated match facts; complete standings require complete season-to-cutoff ledger, not current table. Use train-only imputation only for native supported feature families, preserving missingness/coverage denominators.

## Scope review, chronology and fit are separate issues

`reports/rehearsal/TOTOAI-RESUME-20260915/C-scope-contract-review/proposed-contract.json` exists and remains `PROPOSED_NOT_IMPLEMENTED_NOT_APPROVED`. It proposes independently reviewed canonical team-ID + gender/age/squad taxonomy + valid_from/to + field-level evidence and lineage, with per-fixture binding. **No requirement to hunt legal participation regulations**: supported dated provider/official team classification can be used. One validated team assertion can cover multiple genuinely matching historical occurrences, not all same-name teams or all dates. Current proposal does not itself establishmissing data or approve a reconstruction training domain.

For a retrospective corpus retain distinct historical decision cutoff, actual fetch time, event kickoff/finish evidence, source revision date, declared publication date and information-availability confidence. Today's fetch of an older match is not inherently target leakage; including a target score/futuregame is. A result fetched15Sep does not get `available_at=oldkickoff` invented. Historical publication availability may be reconstructed with evidence/explicit research uncertainty; causal chronological fit needs a reviewed corresponding contract. The existing trainer only accepts `FROZEN_HISTORICAL_INPUT` / `SYNTHETIC_TEST_ONLY`, not a late-capture reconstructed domain. Add/review a separate retrospective path if desired; preserve production gates.

Before scoring, freeze sanitized input and generated package hashes. Labels (including earlier-draw training labels) go through separate loaders; train/impute/calibrate only on earlier eligible whole draws, never evaluate on outcomes used to tune that fold. Since today's imported label snapshots are all dated15Sep, strict historical label availability is another reconstruction field to establish—not a reason to erase labels or falsely backdate them. Eight newly finished draws alone do not constitute independent training plus held-out proof; the first evaluated draw needs earlier qualifying training data or an explicitly untrained baseline. Current F4 atmost7folds requires a reviewed extension/protocol for8, not dropping failures. Old67/105 versus74/105 coverage ceiling belongs to the previous corpus, not a fresh measurement of these120events; do not lower70% or reuse that denominator here.

## Concrete handoff, no new implementation plan

1. Planner can immediately scope an outcome-blind **finished-market reconstruction adapter** with explicit unknown-asof scenario class, same-bank matrix and hash-bound surface; reuse reviewed native numeric helpers. This is real work possible now without sports data, not a prospective-quality claim.
2. Separately scope exact target-ID/time reconstruction and reusable reviewed entity-scope registry; consume existing dated histories, fill missing windows only with attributable archives, report target/future exclusions and revision uncertainty. Keep true pre-draw4999/5000 cohort separate from unknown-time markets.
3. Five-way evaluation and Sportsv3 fitting remain blocked by concrete sports corpus/fit-contract gaps, not simply absent pre-draw snapshots. After corpus availability, seal/version fitted artifacts and independently validate inference/sidecar; do not activate because historical hits look better. Full production robust and sports-shadow require genuine sports inputs, with disclosed fallbacks.

No new packages/training/source fetches/tests were run; no active process left by this job. New files: this MD and `retrospective-reconstruction-context.json` only. User's main thread owns publication and separate planning.
