# 5008 — native20:45 observation

Task TOTOAI-RESUME-20260915. Saved2026-09-15T20:46:55.547500+03:00; read-only runtime inspection, report-only writes.

- Scheduled20:45MSK; native completion record2026-09-15T20:45:04.914852+03:00; returncode75. Separate actualstart timestamp unavailable.
- Fallback collection/consensus completed; `deferred`, `ACTION REQUIRED: timing unknown 1/15`; **14/15**, planidnull. LaunchAgentnotrunning, activecount0,runs2,exit75 at20:45:35. No PID retained after terminal exit.
- GOAL0candidates/41requests; Sofascore1candidate; TheSportsDB0candidates/2cachehits/0requests; consensus0promotions. No valid newtiming evidence. No manualrun/restart.

## Only remaining event9
**Willand Rovers—Westbury United / Уилланд Роверс—Уэстбери Юнайтед**,16September, Southern Division One South.

| Source | Displayed UK time | MSK if UK-local display | Known fixture publication/update |
|---|---|---|---|
| Officialleague https://www.southern-football-league.co.uk/overview/divonesouth |19:30|21:30|UNKNOWN; captured15Sep20:33:03MSK|
| Officialawayclub https://westburyunited.co.uk/ ; https://www.westburyunited.co.uk/teams/westbury-united/fixtures-results |19:45|21:45|UNKNOWN; captured15Sep20:33:05MSK|

**Additional timezone ambiguity**: league raw`dateTime=2026-09-16T19:30:00.000Z` contradicts interpreting displayed19:30asUK-local. LiteralZwould22:30MSK. Do not claim21:30asvalidatedUTC or apply TotoBrief-specific repair to league. NativeSofascore=18:45:18UTC=21:45:18MSK;18seconds preserved.

IndependentSWSN https://southwestsportsnews.com/football/fixtures/8349-southern-league-fixtures-september-15-16-2026 lists19:30; published15Sep05:45,updated07:25,page timezoneunspecified. It does not prove which officialsource is outdated. Officialhomeclub https://www.willandrovers.co.uk/ refers to leaguefixtures, not a new independenttimestamp/correction.

## Remaining reconciliation / proposed next step
No alreadyverifiednewer evidence resolves knownconflict. Narrow nextcheck: exactofficialfixture https://www.southern-football-league.co.uk/match/6a5a1a66ce9ef452b61f4246 for explicit timezone/date and datedkickoffcorrection, against Westburyfirstteamfixture. If none, officialconfirmation required. Preserve sourceconflict, do not pickmajority or round. Any acceptedreview/nativepreparation belongs to a separateimplementationjob; none applied here. Next existingnative retry21:15MSK.

Machineevidence: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/5008-checkpoint-2045.json`. No ACTIVE_PLAN/Git/code/DB/consent/jobs mutations.
