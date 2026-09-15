# Exact7GOALpages replay — protected conflict reproduced

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Finished 2026-09-06T11:32:35.167959+00:00.

**Outcome:** current accepted updatedAt-only fix does **not** resolve this capture. Native `GoalAPIClient.fetch_schedule` consumed all7 savedpages and raised exactly `GOAL API duplicate event identity conflicts`. This is a protected content difference, not merely capturemetadata/updatedAt. No code/policy change is justified automatically.

##Exact witnesses (only relevant public fields)
| GOAL ID | Differences beyond updatedAt | Capture positions, zero-based rows |
|---|---|---|
| `cmt63ihwdf62st107zcaaswfn` / apiId`782981` | homeHT `None` → `1`; awayHT `None` → `0` | offset500 row98 → offset600 row0 |
| `cmt63ihwff62ut1075qx5dhf0` / apiId`784841` | homeHT `None` → `0`; awayHT `None` → `0` | offset500 row99 → offset600 row1 |

Both observations: kickoff2026-09-05T14:00:00Z,statusFINISHED. First finalscore1–0;second0–1,unchanged acrosspages. Halftime fields go missing→present; this is **not proof of different underlying team identity**, but current strict contract deliberately treats allscore fields as semantic. `updatedAt` is also different but already excluded; excluding it still produces differing native semantic hashes.
- Before pageSHA `5830724e760f4efe76d80bfbb6fad946814a8410c6b5a53c1be59b5fd14f036d`, fetched_at2026-09-06T09:34:20.835560Z.
- After pageSHA `172c063616b503489b5bd2199d2d922b7d8581ab734a155b6c25f4797cbecae7`, fetched_at2026-09-06T09:34:21.049466Z.
- Exact old/new raw-event hashes, updatedAt values, paths and all7 page/request/response hashes: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/sports-goal-replay-receipt.json`.

##Method and bounds
One subprocess bounded25seconds, exit0 for successful diagnostic reproduction; native parser result is failure above, **not schedulePASS**. Temporary transport adapter supplied exact saved payloaddata/pagination and original `GoalAPIRequestEvidence` to unchanged nativefetch_schedule. No fakeHTTPresponses, paginationterminator, requestIDs or capturetimes. Independently parsed the complete700rowprefix with same native `_parse_event`/`_schedule_semantic_hash` to enumerate bothconflicts, without weakening nativefailclosed.
Verified provider/schema, responsehash, requestfingerprint, filename/filehash, exact parserimportfrommain. ParserSHA `73d6d9e6185c35fab07565ce0566c15f869ad19f907547ab70f89bed5b28ccbb`,unchanged afterrun. All7rawbytes unchanged. Auditguard deniednetwork/DB/unscopedwrites/processescape;blockedactions[]. Onlytemporarywrite root, then these2receiptfiles. No jobs/auth/pinnedseed/mainmemory/Git operation; no backgroundprocess remains.

##Counts and what is NOT recoverable
-7pages×100=700 parsedrows,698uniqueproviderIDs,2duplicateobservations,2protectedconflicts,0parse-shape errors.
-All700kickoffs are2026-09-05;0eligibleobservations at actual2026-09-06capture.
-0verified4998mappings recovered; nativefetch returned no schedule. This is **not** a finding that4998fixtures do not exist atGOAL.
-Capture is incomplete: offsets0…600, lastpagehasMore=true,total1513. Even removing the conflict would request missingoffset700; neither remainingSep5pages norSep6/7pages may be invented or assumedempty.
-Bound originalcoverage stillhistory_source_count0/sports_eligible_count0. Nohistoryavailability established beyond saved0; nohistory fetched, no probabilities manufactured.

##Smallest next action / conditional operational handoff
Independent review can now consider exactly the two null→known halftime-score witnesses and decide whether to support a narrowly specified representation/observation reconciliation or fail-closed quarantine of terminal fixtureconflicts without letting them become scheduledtargets. **Do not simply ignore halftime fields or select lastrow**: that would change the accepted safetycontract. Existing updatedAt-only parser behaves as designed. This task applies nofix.
The requested “if offlineparsevalid, refresh then bind” condition is **not met**. New live capture/history is still needed; no ready operational refresh is claimed. Known nativecollection entrypoint, for a separately authorized laterjob only:
`/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli collect-goal-shadow-input --drawing-id 12102 --queue <validated-current4998-queue> --raw-cache-dir data/raw --output-dir <NEW-immutable-project-capture-dir> --env-file .env --request-budget 120`.
Actual observed timestamps must come from collection,neverbackdated. Do not delete/rewrite goal-auto/current.json.
`parallel-sidecar-prepare --scheduler-plan ... --coverage-summary ... --as-of ...` can generate a seed but **does not replace existing pinnedbinding**: `final_hybrid_sidecar.py:118` reuses existing wrapper's sportspath; `_write_expected`1323 rejects unrelated bytechanges. No supported in-place seed-refresh/rebind command was established for thisalreadyinstalled plan. Do not overwrite seed/wrapper, recreatejobs or alterplan/consent as workaround. A separately reviewed narrowbindingoperation is required before promising pre16:30adoption.

ReceiptJSON SHA `11f643ddab3abc3187d525625a4c8087c7bf5be0067d3d309314abcc8f4c138a`. DONE:exactofflineverification/witnesses. BLOCKER:protectedhalftimecontentconflict + incompletecapture. NEXT:parent/reviewer receives evidence; no blindretry or providercall here.
