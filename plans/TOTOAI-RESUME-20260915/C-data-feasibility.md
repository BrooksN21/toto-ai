# C-data feasibility — concrete sample, not model readiness

Task TOTOAI-RESUME-20260915. Read-only production DB; no source, jobs, memory, consent or model changes. Two bounded GOAL requests, zero API-Sports retries. Public raw saved only under ignored `reports/` (.gitignore line28). No key/cookie/header persisted or printed.

## Result
**YES: GOAL provides event-level finished team history with concrete score/date/identity fields; a partial historical reconstruction is feasible. NO: this does not establish full4999–5006 coverage or compatibility with current F4 strict pre-asof capture gate.**

Sample:4999 position2 (DB event_order1), **Elche—Real Sociedad**, bound fixture `cmt7202whtllnt107g9xjoh4q`, target07Sep19:30UTC. Research historical asof07Sep14:00:02.186014UTC (17:00MSK), drawing close14:30UTC. Existing DB records bind exact provider home/away IDs, target kickoff and pre-draw run7210e8… captured06Sep18:09:33UTC. This is existing identity evidence, not a newly independently approved full F4 scope receipt.

| Team | HTTP | Fetched UTC15Sep | Rows returned | Before asof after exclusion | Old-update afterasof | Quota remaining |
|---|---|---|---|---|---|---|
|Elche|200|2026-09-15T14:13:25.988664+00:00|10|8|2|882|
|Real Sociedad|200|2026-09-15T14:13:26.401451+00:00|10|8|4|881|

Endpoint template: `https://api.goal-api.com/v1/teams/{team_id}/results?limit=10`. Existing nativeGoalAPIClient validates success=true, matchingteamId, boundeddata shape and freezes response. Exact endpoints and complete SHA256 values are in companionJSON. Both fresh snapshot file hashes/readbackpayloads independently matched native receipts. Provider is a public API aggregator, **not an independently corroborated official federation archive**.

Raw fields: id/apiId, teamId, homeTeamId/awayTeamId, nested homeTeam/awayTeam names+IDs, kickoffUtc, matchStatus=FINISHED, homeTeamFtScore/awayTeamFtScore, separate extra/penalty scores, leagueId/leagueYear, createdAt/updatedAt. These support score-based rolling form, goal rates, home-away slices and elapsed-time/rest candidates. No current league table or target final odds requested.

Important: team-results response contains the target and one latergame perteam. They were fetched incidentally as part of endpoint response, **excluded before feature rows**, and not scored/evaluated. Full raw is quarantine/source evidence only, never inference input. The filtered artifact contains only16 earlier fixtures. This was feasibility extraction, no fitting/inference.

## Actual retained examples (FT90, not target results)

### Elche
- 2026-08-28T17:00:00.000Z Racing Santander—Elche 3:2; fixture cmsvp41119a5zpg078zv153bv; updatedAt 2026-09-12T12:10:17.841Z.
- 2026-08-23T19:30:00.000Z Elche—Barcelona 0:5; fixture cmsp4mt6pu57dpn0662nfx41d; updatedAt 2026-09-12T07:22:27.146Z.
- 2026-08-17T19:00:00.000Z Dep. A Coruna—Elche 1:1; fixture cmsmgy15dkcuwpn06mzzg4b0w; updatedAt 2026-08-28T00:04:25.884Z.
- Candidate aggregate over retained8 only: {"n": 8, "goals_for": 12, "goals_against": 14, "ppg": 1.25, "home_n": 6, "away_n": 2, "days_from_last_kickoff_to_target": 10.104166666666666}. This is not old10-match model input and not independent coverage proof.

### Real Sociedad
- 2026-09-03T19:00:00.000Z Real Sociedad—Celta Vigo 0:0; fixture cmt1fijd279v2pd07jzzt5rcp; updatedAt 2026-09-12T12:15:04.458Z.
- 2026-08-29T17:00:00.000Z Real Sociedad—Espanyol 2:1; fixture cmsvp4w1u9ep9pg07iru8ng83; updatedAt 2026-09-12T12:12:01.865Z.
- 2026-08-26T19:00:00.000Z Real Madrid—Real Sociedad 4:1; fixture cmsvp46j59aympg07337ou5a8; updatedAt 2026-09-12T12:09:46.866Z.
- Candidate aggregate over retained8 only: {"n": 8, "goals_for": 10, "goals_against": 15, "ppg": 0.875, "home_n": 2, "away_n": 6, "days_from_last_kickoff_to_target": 4.020833333333333}. This is not old10-match model input and not independent coverage proof.

## What this proves / does not prove
- Current history contains8eligible earlier rows for each team, all16 IDs already present in the corresponding pre-draw stored10-match DBwindows. Old window captured06Sep, not fabricated now. DB also retained aggregated form/rest. Exact old raw hashes are referenced in those source receipts, but were not found in the defaultcache by the two exact fingerprints checked; no broad search. **Old individual-scorebytes were not reverified.**
- New endpoint is “latest10”; latergames displace oldergames. Cannot claim reconstructed full last10 before historicaltarget from only8remainingrows. Need verified older snapshot reuse or documented dated/paginatedhistory; date/pagination support not verified here.
- Some earlier fixtures have updatedAt12Sep, afterasof. This is not proof that their scores changed, but does mean today's row-version is not itself proof of then-known values. createdAt alone does not prove score availability. Exact final whistle/result publication time is not provided in the sampled fields. Prior games are days/weeks beforetarget, so temporal use is causally plausible, but strict information-availability grade stays UNKNOWN without archived/equivalent evidence.
- Remaining F4missing fields: independently dated opponent histories, exact season standings, BKmargin. Team aggregate alone does not supply opponent-adjustedstrength or marketfeatures. For5001–5006 missing oldmarket/pool cannot be invented from footballhistory.
- SofaScore/TSDB history endpoints were not probed: one working GOALsample suffices for this boundedfeasibility question. TheSportsDB public documentation page was reachable, but this is not API/history coverage proof: https://www.thesportsdb.com/api.php . No API-Sports suspended call, no broad provider audit, no commitment to restore120/120features.

## Minimal honest adapter / next checkpoint
Separate `HISTORICAL_RECONSTRUCTION` schema with real fetched_at, per-field information_available_at/evidenceorUNKNOWN, exact identity/scope, strict target/future exclusion, FT90 normalization, row hashes, sorted/unique windows and missing-window counts. Keep today'sraw isolated and filtered rows separate; prefer independently verified genuine pre-draw captures when available. Do not alter current history_backfill capture checks, old chronologyrejections,67/105versus74coverage or independent review requirements. CurrentF4 cannot accept this latecapture as FROZEN_HISTORICAL_INPUT. A separately reviewed reconstruction protocol/time-evidence contract is needed; fullgate/fit/rollout remains NOT_READY.

**Concrete next scoped checkpoint:** recover the two already referenced old snapshot bytes via existing source manifest (not a full tree scan), compare priorfixture FT90values/hashbinding against current16rows; then test one additional previously-uncovered5000–5006target's exact team identity and datedhistory coverage. Only if evidence permits, build stageCcorpus and stageDfolds. Missingdata no longer means “no source exists”: this provider demonstrably returns usable historical facts; completeness/then-knownvalues remain separate questions.

Artifacts: companion `C-data-feasibility.json`; ignored publicraw directory `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-feasibility/`; clean filtered rows `filtered-historical-rows.json`. No implementation performed.
