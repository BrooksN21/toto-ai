# TOTO-DRYRUN-NEXT context

Collected 2026-07-23 from local state only; no network/API sync, scheduler installation, betting, Git, or external systems used.

## Exact target / blocker

- Current open drawing: visible number **4953**, internal ID **11972**, status `active`, started at `2026-07-23T15:30:00.000000Z`.
- Local preparation for 4953: `status=unresolved`, `mapped_count=0`, `eligibility_status=unknown`, updated `2026-07-23T07:34:49.564555+00:00`.
- Therefore exact blocker: **4953 is not locally prepared/playable (0/15 mapped; eligibility unknown)**. No dry-run target is safe/actionable from the existing DB without a fresh synchronization/preparation step; that step was not attempted under the no-sync instruction.
- Last locally playable drawing: 4952 / internal ID 11970, finished, preparation `ready`, 15/15, eligibility `playable`; it is not an open/playable next draw.

## Existing DB evidence

Database: `data/toto.db`.
- `drawings`: 4953 active; 4952 finished.
- `drawing_preparations`: 11972/4953 unresolved, 0 mapped, unknown; 11970/4952 ready, 15 mapped, playable.
- `drawing_event_pins`: only valid 15-pin set observed for 11970/4952.
- Recent complete external collections are for 4952 and marked playable; no playable collection for 4953.

## Environment safety check

- `.env` is readable and non-symlink.
- `API_SPORTS_KEY` is present with a non-empty value; value was not printed.

## CLI help inspected

Executable: `./.venv/bin/toto-ai`.

- `toto-ai scheduler-plan --dry-run` generates/prints a scheduler plan JSON and requires `--drawing`, `--ended-at`, `--bank`, `--output-dir`; optional `--drawing-id`, `--db`, `--env-file`, thresholds, and bounded-pass controls.
- `toto-ai scheduler-execute --dry-run --plan PATH` prints an existing plan JSON without executing; `--simulate` is explicitly network-free simulation.
- `toto-ai run-drawing` has no `--dry-run`; it requires `--bank` and can use `--offline-replay`, but is not a suitable next target while 4953 is unresolved.
- `toto-ai morning-preanalysis-plan` is explicitly non-betting and generates, but does not install, a launchd candidate.

## Recommended exact disposition

**BLOCKED: no exact dry-run/scheduler execution target can be authorized from local data because open drawing 4953 is unresolved 0/15 and not playable.** Do not fetch, install, or bet under this run’s constraints. A later operator run should first perform the bounded `sync-prepare --open --expected-drawing-number 4953` workflow, then re-check readiness before generating or simulating a scheduler plan.

## Failure diagnosis (dryrun 4953, 2026-07-23)

- Dryrun artifact: `reports/rehearsal/dryrun-4953-20260723/sync_prepare_attempt1.{stdout.log,stderr.log,meta.txt}`. Detail sync itself succeeded from network (HTTP 200); the command exited 2 after preparation. Stderr is empty. The meta records 50.241 seconds and exit code 2.
- Target raw detail: `data/raw/drawing_11972.json`. TotoBrief has `start_at=null` for every event; `ended_at=2026-07-23T15:30:00Z` is the drawing deadline, not an event start. Event order 6 is **Флора — ТНС**, target event ID **178689**, championship **Европа. Лига конференций УЕФА. Квалификация**. Best provider candidate is fixture **1589427**, **Flora Tallinn — The New Saints**, UEFA Europa Conference League, starts **2026-07-23T16:00:00Z** (19:00 Moscow), same orientation.
- The authoritative preparation row is in `data/toto.db`, `drawing_preparations.drawing_id=11972`: `status=unresolved`, `mapped_count=0`, `unresolved_event_orders=0..14`, `eligibility=unknown`, `provider_count=14`, and `missing_event_orders=[6]`. The readiness JSON records matches for orders 0-5, 7-14 with fixture IDs `1593519,1593522,1556544,1556543,1593520,1556511,1556512,1593493,1556513,1556523,1593476,1593496,1593492,1556522` respectively; no pins were written.
- Order 6 review is `team_registry_reviews` row for drawing 11972, status `pending`. All ten retained candidates (provider fixture ID / orientation / home score / away score / pair score) are: `1589427 same 0.900000/0.352941/0.626471`; `1593487 reversed 0.400000/0.433333/0.416667`; `1562970 reversed 0.522727/0.281818/0.402273`; `1556546 reversed 0.348485/0.444444/0.396465`; `1562967 reversed 0.307692/0.444444/0.376068`; `1598509 same 0.522727/0.222222/0.372475`; `1546712 reversed 0.315789/0.428571/0.372180`; `1591900 same 0.444444/0.285714/0.365079`; `1547773 same 0.388889/0.333333/0.361111`; `1548018 same 0.352941/0.363636/0.358289`. Best-vs-runner margin is **0.2098039**. The leading candidate is the only one in the correct UEFA Conference League context; the remaining candidates are mainly friendlies/Sudamericana and have weaker league evidence.
- Why diagnostic “14 matches” became authoritative `mapped_count=0`: this is intentional atomic persistence, not a count bug. `src/toto_ai/external_odds/preparation.py` publishes pins only when all 15 resolutions are matched, no required schedule date failed, and timing is playable; otherwise it writes `pin_specs=()` and `mapped_count=0`, with every order unresolved for fail-closed readiness. Order 6 fails the generic resolver: although pair score 0.626 is just above `MIN_PAIR_SCORE=0.62`, away/team score 0.353 is below `MIN_TEAM_SCORE=0.52`; no reviewed/provider-ID/transliteration identity exists. The resolver therefore does not accept the one high home-side fuzzy score. This is not a weakened/one-draw matcher policy.
- Schedule diagnostics in the authoritative row are successful for `2026-07-22`, `2026-07-23`, `2026-07-24`, and failed for `2026-07-25`, `2026-07-26`, `2026-07-27`, each with the exact locally persisted reason **`API-Sports returned provider errors`**. The raw HTTP status and provider JSON body are not present locally: `src/toto_ai/external_odds/api_sports.py::_validate_top_level_payload` collapses any non-empty top-level `errors` into that sanitized exception and failed responses are not cached; the dryrun stderr is empty. Therefore HTTP/provider payload cannot honestly be reconstructed from this workspace. It is not evidence of quota/auth/no-fixtures: the key was present, earlier requests succeeded, and the cached 2026-07-24 response has quota `daily_remaining=99`, `minute_remaining=9`. Given the failure starts exactly beyond the successful date horizon and project history documents the API-Sports free-plan future-date boundary, the safest classification is **provider date-horizon coverage**, not quota exhaustion, auth failure, or stale cache; preserve this as an inference until raw response logging is added.
- Root cause is composite: **one ordinary unresolved alias/identity case (Флора/ТНС vs Flora Tallinn/The New Saints) plus unavailable provider schedule coverage beyond the free-plan date horizon**, with correct atomic 15/15 persistence converting partial diagnostics to zero authoritative pins. It is not stale cache (detail was network-fresh and provider cache was reused only for successful dates), not a generic “14 is enough” policy defect, and not a one-off draw ID defect.

## Safest general fix / regression scope

- Do not lower global scores, accept “14/15”, or hardcode drawing 4953/fixture 1589427. Add a reviewed, context-scoped provider identity/alias path for Cyrillic-to-provider team pairs (including provider team IDs), then rerun the same conservative resolver and require unique fixture, correct competition, orientation, and start-time evidence. Keep atomic 15/15 publication and explicit unresolved status.
- Persist sanitized HTTP status plus a non-secret provider error code/message (never the API key) in per-date schedule diagnostics so future incidents distinguish date horizon, quota (429), auth (401/403), empty/no-fixtures, and transport errors without guessing.
- Regression cases: (1) this exact Flora Tallinn/The New Saints alias resolves only after reviewed identity and never by a one-draw special case; (2) same pair with ambiguous/weak context remains unresolved; (3) 14 matched plus one ambiguous yields zero pins/zero mapped; (4) successful dates plus a failed required date remains atomic unresolved; (5) 2026-07-25..27 provider errors retain status/payload classification; (6) cached successful dates do not mask a fresh required-date failure; (7) known-start and reversed-orientation cases preserve existing thresholds.
