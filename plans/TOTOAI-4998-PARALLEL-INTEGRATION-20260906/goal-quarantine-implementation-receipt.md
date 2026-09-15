# GOAL per-fixture quarantine — implemented, review pending

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Finished 2026-09-06T11:41:50.544893+00:00.

- RED confirmed: missing opt-in API; then implementation and scoped verification.
- Exact5-file patch: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/goal-quarantine-implementation.patch` SHA256 `b463ced484c99b6ff12400329b876d3cdd1f0bb2a3e95d032dc7f621afad3b54`.
- Default strict `fetch_schedule` preserved; all other existing client methods (including history/transport) AST-identical. UpdatedAt-only semantic hash unchanged.
- Opt-in collector quarantines whole conflictingID permanently for currentrequestwindow, retains all immutable raw/page provenance and protected fields; continuespagination. Unrelated valid targets may remain independent candidates after fullpagination; affectedtarget cannot be replaced by convenient alternativeID. Noledgerpromotion.
- Statuspartial_conflicts withpagination_complete=true on complete-but-quarantined collections; budget/schema/transport failures remain source_failed withpagination_complete=false and no partialcandidate return.

##Verification
**84passed/0.90s**,6 scoped no-DB testfiles; **8-fileRuffPASS**. Includes28newcases: forward/reverse protectedID/team/league/kickoff/status/score/unknownfield conflicts; resurrection prevention; nextdate; latecapture; requestbudget; affected-vs-unrelatedtarget;2realrawnull→halftime witnesscases with originalhashes.
Exact saved7page replay:700rows,2fixtureIDs quarantined; nativepath reaches missingoffset700 instead of crashing atoffset600. `pagination_complete=false`;0current4998mapping/history recovered. Rawcapture not fabricated or overwritten. `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/goal-quarantine-offline-replay.json` SHA `9a208cf6ae9f6f488f975bfeb6f13436b79c8f4255e90c12992feb554cb9ced2`.

Limits preserved: earlier73-pass harness post-check caught an expected blockedDNS; expandedtest attemptedSQLite and was denied after88passes. Finalscoped84passes still records1deniedDNS inexistingcollector test. Noactualnetwork/DBoperation. ResearchDBtests not claimedgreen; safetyguard not weakened. Commands/failures retained inJSON.

##Paths and hashes
- `/Users/turshevr/toto-ai/src/toto_ai/external_odds/goal_api.py`: 73d6d9e6185c35fab07565ce0566c15f869ad19f907547ab70f89bed5b28ccbb → `026e393656eb24728f9c25a1563f4e0615c0811d468644d59a7962645e938db9`
- `/Users/turshevr/toto-ai/src/toto_ai/external_odds/schedule_source_collector.py`: 5e01024b17c1bf15b99bc93d9ea9600e85ce08606887ce277c0c03babfceb328 → `51901ca513206dc154a8c211e702f7a4b4a4283a9c3068907ff3ccd752fafe0c`
- `/Users/turshevr/toto-ai/tests/test_goal_api_fixture_quarantine.py`: None → `01b0f4fc84c6ee7f850e958ec47ecc6eb48c588da5d07eb37bfd70099b621f48`
- `/Users/turshevr/toto-ai/tests/fixtures/goal_schedule_quarantine_conflicts.json`: None → `a2a6fec36b0d5ff3a3be4d47b15bc1b944e3eb34041b6f28915d4d5942c853ca`
- `/Users/turshevr/toto-ai/knowledge/goal_schedule_fixture_quarantine.md`: None → `467d9cfa5dab502da7af440e5cbb42597f2eefed19e64ee76d443dabb5939031`

`goal_probe_collection.py` untouched; afterSHA `1c1d5378700d1f4563a051142cf21eac66ebb5c1fa39c8c521c774192202eb62`, unchanged=True. No jobs/auth/pinnedseed/mainmemory/Git changes, no publication or ownedprocess. ExistingPR/publisher not touched. Newdoc recordsboundary, not activation/profitability.

Receipt `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/goal-quarantine-implementation-receipt.json` SHA `b0885fb51060e02a6090bfc2c9c0cdfc4b0d74968915f1bbc6da8cb97bfe4dad`. NEXT: independentreview; cachefix/newcapture/history/binding separate. This patch does not itself deliver Sports4998coverage.
