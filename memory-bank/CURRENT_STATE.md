# Current State

## Drawing 4990 freshness recovery and robust package research (2026-08-29)

The first real schema-v9 T-120 checkpoint terminalized plan
`3a9fa3fe29a2290b` because reviewed-catalog freshness had split into three
different production call sites: the CLI/source path used the approved
24-hour next-day window, while preparation refresh and scheduler preflight
still hard-coded 12 hours. All production loaders now use the single
`REVIEWED_SCHEDULE_MAX_AGE` contract. Regressions cover a reviewed claim
collected the previous day and the scheduler preflight binding. The focused
reviewed/preparation/scheduler suite passes 189 tests; the full pre-robust
suite passes 2,112 tests with 13 deselected.

Because the original state was already terminal, exact-input recovery plan
`5708c4b517c0f1e3` was generated in a separate output scope and its LaunchAgent
was installed. A real recovery T-120 TLS preflight completed successfully at
14:42 MSK with the same drawing, bank, probability and evidence bindings. The
scheduled T-90 API preflight then completed successfully at 15:00 MSK. The
remaining T-60 through T-10 checkpoints still require observation; this
recovery is not a profitability claim.

A separate research-only maximin selector now recombines a finite union of BK
and sports package candidates. Its primary objective is the worst sampled
category coverage across the two probability models, with mean coverage and
cross-model coupon probability only as deterministic tie-breakers. The final
GOAL comparison sidecar now writes three equal-bank artifacts: BK control,
sports shadow and robust BK/sports recombination. The robust artifact remains
non-operator, cannot affect scheduler state and is not activation evidence.

The first frozen historical canary recombined the 330 unique coupons from the
4989 BK/sports pair into 166 coupons. Robust exact P(13+) was 0.012465 under BK
and 0.011034 under sports, above both controls' cross-model minimum. Actual
settlement still produced only 11 best hits and zero 13+, although mean hits
improved to 6.253. This is encouraging model-robustness evidence on one input,
not evidence of profit or readiness for activation. Details are in
`research/drawing_4989_robust_recombination_canary_20260829.md`.

## Drawing 4989 paired research settlement (2026-08-29)

The complete authoritative result snapshot for drawing 4989 is
`21122X1222XX2X1` (`snapshot_sha256=57593fc86bb9c0a2160e396b0a9400aa1b474f5abf3e267afa9f943f9ed7fc40`).
The two post-deadline research packages were settled against that exact row.
The 166-coupon BK control reached best 11/15, mean 6.054 and zero 13+;
the 166-coupon GOAL sports-shadow reached best 10/15, mean 6.060 and zero
13+. Their 330-coupon unique union still reached only 11/15.

The sports probability matrix was marginally better than BK on this one
drawing (log loss 1.0692 versus 1.0770; multiclass Brier 0.6465 versus
0.6509), but that did not translate into a better package. Six actual outcomes
were BK rank 3. Every actual event outcome had non-zero package exposure, so
the category miss was joint-combination failure rather than a fixed/zero-cover
failure. Durable analysis is in
`research/drawing_4989_package_postmortem_20260829.md`; machine-readable
settlement is in
`reports/research/final-goal-hybrid-4989-postdeadline-20260828/settlement-20260829.json`.
This one paired result is not activation or profitability evidence.

## Drawing 4989 category-hit activation (2026-08-28)

The category-hit hybrid selector is now active for drawing 4989 under the
regenerated schema-v8 scheduler plan `e27c56d2ef849b11`. The plan is bound to
candidate source `cover14_bk_fill_then_ev_hybrid`, release protocol
`quality-v2-category-hit-hybrid-v2`, bank 4,980 RUB, stake 30 RUB, the existing
READY 15/15 preparation and the independently verified 18:00 MSK operational
cutoff. The superseded EV/crowd plan `ceaa292700dbb903` was unloaded and its
record/output directory were archived without deletion.

The regenerated morning dispatch installed and verified LaunchAgent
`com.totoai.production-scheduler.v8.e27c56d2ef849b11`. Its non-actionable
training run produced 166 unique coupons for 4,980 RUB with
`STRUCTURAL_PASS` and no unused bank. A separate real package-free daytime
preflight passed exact drawing identity, data access, configuration and
reviewed schedule validation. The scheduler is waiting for the first 16:00
MSK checkpoint; T-25 final is 17:35, retry is 17:44 and the operator boundary
remains T-10 at 17:50. Automatic wagering remains disabled and no
profitability claim is made.

The owner explicitly authorized one experimental manual release for exact plan
`e27c56d2ef849b11`; it expires at T-10 and does not enable automatic wagering
or prove profitability. A separate package-free preflight still passes.

GOAL sports-shadow collection for 4989 found 10/15 exact/same-orientation
fixtures and retained events 4/8/9/12/15 as explicit TotoBrief BK fallbacks.
The frozen research input contains 15 events, 20 team histories and no
scheduler influence. A same-config category-hit hybrid comparison at bank
4,980 produced two 166-coupon research packages. The BK candidate modeled
P13=0.012195996 under BK; the sports candidate modeled P13=0.010685331 under
the experimental sports blend. The sports package beats the BK package under
the sports model (0.010685331 versus 0.009114524), while BK beats sports under
BK (0.012195996 versus 0.009481680). Their overlap is 0/166. This is model
disagreement, not activation or evidence of profitability. The artifacts are
below `reports/research/goal-sports-hybrid-4989-20260828/`.

The reusable `compare-final-goal-hybrid` command now binds both hybrid
calculations to one immutable scheduler final input. A live training check on
4989 completed in 168 seconds and produced 166 coupons per candidate. The
separate `run-final-goal-hybrid-sidecar` waits for scheduler-owned PLAY,
requires at least 240 seconds before T-10, validates/re-exports the operator BK
package, and fails if its recomputed BK control differs. The sports output
remains research-only and non-uploadable. Exact LaunchAgent
`com.totoai.goal-hybrid-sidecar.4989.e27c56d2ef849b11` is loaded for
17:37 MSK; it has never run yet and does not alter the main scheduler.

## Drawing 4988 settlement and selector defect (2026-08-28)

Drawing 4988 is now synchronized from authoritative TotoBrief result snapshot
`62a24d563372b94c1acb0fdef55486215911738fdf58d692853db69e1be09177`
and its archived
166-coupon / 4,980-RUB package is settled. The actual result was
`1X1X21XX12X2121`; best hits were 8, mean hits 5.404, and no coupon reached
9/13/14/15. Settlement SHA-256 is
`f5e24c7dfd2126504a57ba64fd4a4cc8ac0dd443b66df6a2d5e1021e42bb8774`.

The frozen equal-input audit identifies a package-construction defect rather
than only bad luck. The EV/crowd package modeled `P(13+)=0.00339451`; a
full-bank BK top-probability control on the same bytes modeled
`P(13+)=0.02167641`, about 6.4 times larger. Nine actual outcomes had only
3.0%-7.8% package exposure. The selector starts from EV-ranked coupons and
performs only 12 local quality swaps, so its declared probability-first repair
objective is not a global package-generation objective. Existing strict and
legacy diagnostics show the same EV/crowd deficit.

The postmortem is
`research/drawing_4988_package_postmortem_20260828.md`; the approved next-step
design is
`plans/TOTO-4988-POSTMORTEM-4989-IMPROVEMENT/plan.md`. EV/crowd must remain a
shadow comparator. The next candidate comparison adds BK-only and a full-bank
Cover-14 plus unique BK-fill challenger. This is not profitability evidence.

Drawing 4989 remains active. Identity/pins are READY 15/15, kickoff timing is
10/15, and orders 3/7/8/11/14 remain under the loaded passive retry. A fresh
10:38 MSK EV research preview again showed the defect: modeled
`P(13+)=0.00220526` versus `0.01105551` for BK-only on the same current BK
matrix. No final scheduler package exists yet.

## Drawing 4989 automatic preparation and scheduler v8 (2026-08-27)

The generic morning dispatcher selected drawing 4989 (internal ID 12074)
without operator prompting. Identity preparation is READY 15/15; kickoff
timing is confirmed for 10/15 events and the remaining orders 3/7/8/11/14 are
owned by the loaded identity-bound passive retry job. A live retry after the
cutoff fix returned the expected deferred code 75 rather than fatal code 2.

An unresolved-only source refresh can no longer erase an earlier hash-verified
conservative cutoff. The persisted 18:00 MSK operational cutoff remains bound
to drawing 4989 while later reports may only tighten it. The generic discovery
LaunchAgent now runs every 900 seconds, retains the fixed calendar checkpoints,
and always invokes `morning-dispatch --activate`; it never places wagers.

Scheduler schema v8 moves the atomic primary final from T-20 to T-25 while
retaining T-10 expiry and the full quality/bank configuration. This gives a
normal successful calculation five additional minutes for manual operator
delivery without reducing search work. Verification is green: `2087 passed,
13 deselected`; Ruff and diff check pass.

A verified pre-T-10 PLAY now also writes stable `operator-delivery.json`.
While READY it carries the canonical upload path, package/archive hashes,
coupon count, cost, publication time and expiry. At T-10 it atomically becomes
EXPIRED, clears the upload path and retains only audit metadata; automatic
wagering remains false. Publication/expiry/rollback regressions pass.

## Expired package audit policy clarified (2026-08-27)

T-10 still irrevocably removes wagering and upload eligibility. The project
owner may now explicitly request the exact hash-verified scheduler archive for
read-only post-draw analysis, with an `EXPIRED — ANALYSIS ONLY — NOT FOR
WAGERING` label. Research/rehearsal packages cannot be substituted.

## Drawing 4988 schedule pins and exact final-input refresh (2026-08-27)

Pins backed by TotoBrief baseline, reviewed schedule, or the bound
schedule-evidence ledger now revalidate against that exact local evidence and
do not require a live API-Sports schedule call. Only pins that actually depend
on the live provider participate in provider schedule requests and freshness
timestamps; mixed preparations remain fail-closed per pin.

Every real fallback package run and atomic final package run now parses the
exact immutable `final-input.json` payload at its recorded capture time and
refreshes the existing READY 15/15 preparation evidence before spawning
`run-drawing`. Missing, changed, or non-READY preparation remains a terminal
integrity failure; the probability hash guard is not weakened. Snapshot retry
reuses the same immutable input and performs the refresh idempotently again.

Scheduler regressions use real persisted READY preparations instead of
stubbing this production guard. Dedicated fallback/final tests prove refresh
ordering and fail-closed behavior. The six reported regressions pass, the full
scheduler module passes 147 tests, partial-enrichment passes 13 tests, and
targeted Ruff is clean.

An isolated atomic-immediate control for drawing 4988 completed in 156.49
seconds with READY 15/15 revalidation and zero API-Sports schedule requests.
It calculated the full-bank 166-coupon, 4,980-RUB paper candidate and reached
the internal safety decision `PLAY`. The operator decision remains `NO BET`:
the quality-v2 release policy still requires explicit experimental manual-risk
authorization. No coupon contents were recorded here, no operator export or
wager occurred, and no remote operation was performed. The full repository
suite was not rerun for this final fix.

## Drawing 4988 preflight and automatic GOAL shadow input (2026-08-27)

Drawing 4988 (internal ID 12071) is READY 15/15 under schema-v7 plan
`095bea62149ea735`. The immutable identity deadline is 22:00 MSK, the
independently tightened operational cutoff is 19:00 MSK, and T-10 is 18:50
MSK. The production LaunchAgent is loaded for 17:00 through 18:50. A separate
package-free real preflight LaunchAgent is loaded for 16:00; it uses the exact
production target/preparation path but cannot generate a package, training
artifact, scheduler transition or wager.

GOAL team-history collection is now reusable and idempotent. It freezes one
15-event schedule binding plus 30 team histories per drawing below
`reports/sports-analytics/<drawing>/goal-auto/`, publishes a hash-bound current
marker only after complete 15/15 success, and reuses that marker on later
morning runs without new provider requests. Generated morning dispatchers and
passive retry children pass `--goal-shadow-auto`. Collection failure is
reported but cannot block production; package influence remains `NONE` and
automatic wagering remains disabled.

The first 12:00 live run exposed a status-contract omission before evening:
an already activated exact plan returns morning status `reused`, while the new
hook initially accepted only `scheduled`. The hook now accepts both successful
states, with a dedicated CLI regression. A live retry then collected 15/15
events and 30 histories in 67 requests (quota remaining 864). An immediate
second live retry returned `reused=true` from the same hash-bound snapshot and
made no new GOAL collection.

The first live 4988 research capture completed 15/15 with 30 histories in 67
requests. The equal-bank 4,980/30 BK and sports-shadow packages each contain
166 coupons and overlap on 23. The sports candidate is better under its own
model, while the BK package is better under BK cross-evaluation. This is model
disagreement, not evidence of superiority or profitability. Production remains
normalized TotoBrief BK until prospective settled comparisons justify a
separate activation decision.

The pre-fix focused GOAL/probability/morning/scheduler suite passed 82 tests and
the `reused` regression subset passes 65 tests. Final full verification passes
2,076 tests with 13 intentionally deselected; repository Ruff and
`git diff --check` are clean.

## Drawing 4987 evening incident and scheduler remediation (2026-08-26)

Drawing 4987 ended with scheduler-owned `NO_BET`; no valid operator package was
published. TLS, API and the old shallow freshness preflights completed, while
warmup, refresh and final each timed out. The primary defect was a split time
contract: schema-v7 correctly anchored parent phases to the earlier
`operational_cutoff`, but the child `run-drawing` still built its internal wait
schedule from the later TotoBrief identity `ended_at`. For 4987 those instants
differed by three hours, so the child spent its parent phase budget waiting for
the wrong windows and was terminated before useful package work completed.

The child now receives the immutable non-extending `operational_cutoff` and
uses it for all waiting while retaining `ended_at` only as target identity.
The T-60 freshness phase is now a bounded full end-to-end package canary rather
than a shallow configuration check. Scheduler phases have admission checks,
package-runtime reserves, phase-specific safety stops, sanitized timeout
artifacts, shared one-hour verified schedule cache across phases, and isolated
market-odds caches. A successful T-60 canary may seed an LKG; later unavailable
sources preserve it. Phase locking is covered against canary/warmup overlap.
API-Sports request timeouts are clamped to the remaining safety window so a
single transport call cannot knowingly overrun the child stop boundary.

Regression and full verification after the main remediation passed 2,054
tests with 13 intentionally deselected and repository Ruff clean. The added
HTTP timeout-clamp regression passes in the 55-test API-Sports provider suite.
A controlled preparation of next drawing 4988 then failed closed at 0/15
because API-Sports still returns the provider semantic error `Your account is
suspended`; this is external-source evidence, not a successful production
rehearsal. A full fresh scheduler rehearsal remains required once 4988 becomes
the selected current drawing and independent schedule evidence is available.

## Drawing 4987 frozen GOAL sports-shadow comparison (2026-08-26)

The reusable research-only command `compare-goal-shadow-packages` now imports
the exact frozen drawing-4987 GOAL schedule binding and 30 team-results
snapshots without a live provider request. It validates drawing/event order,
same orientation, provider fixture/team IDs, source-report semantic hash,
source paths and hashes, frozen TotoBrief authority, and strict pre-`as_of` /
pre-kickoff chronology. GOAL `FINISHED`, `AFTER_ET`, and `AFTER_PEN` map to the
existing provider-neutral `FT`, `AET`, and `PEN` terminal contract. All 300
rows were eligible at the frozen `2026-08-26T10:00:18.237832Z` boundary; 142
were venue-matched.

The shadow has 15/15 sports coverage and remains
`PAPER_ONLY_NOT_ACTIVATED`. It uses the existing Jeffreys-smoothed home-team
home plus away-team away W-D-L projection and sample-count shrinkage toward BK;
blend weights range from 0.1667 to 0.3750. Production BK, scheduler state,
operator-result and PLAY paths are unchanged.

Both comparison branches use bank/stake 4,980/30 and contain exactly 166
unique coupons at cost 4,980. They overlap on 5 coupons; each has 161 unique
to that branch, and exposure changes on 13 events. Own-model diagnostic
P(13+) is 0.00098391 for the BK baseline and 0.00266955 for the sports
candidate. These one-drawing model diagnostics do not prove superiority,
profitability, calibration, or activation.

Artifacts are under
`reports/research/goal-sports-dual-package-4987/`; manifest semantic SHA-256 is
`e1f31d7bfff64d8390a649d36bb31b0d1f5cdbcae1cd01b1a425e2e5037dcce8`.
Package CSV/TXT files carry explicit research-only fields/headers and are
deliberately not BaltBet upload syntax. All 34 frozen sources and ten output
artifacts verified by hash; the nine existing evening-scheduler files were
byte-identical before and after execution. Focused verification: 5 tests
passed; targeted Ruff and `git diff --check` passed.

## GOAL API adapter and drawing 4987 canary (2026-08-25)

- New candidate-only provider module:
  `src/toto_ai/external_odds/goal_api.py`.
- The existing source collector now includes GOAL API alongside Sofascore and
  TheSportsDB. It never mutates the reviewed schedule ledger and has no path
  into prediction probabilities, package selection or operator export.
- Protected authentication works with the mandatory stable user agent. The
  live drawing-4987 fetch used 37 documented paginated date requests; the
  final observed quota was 883/1,000. API-Sports remains configured and is not
  removed while its account reports provider-side suspension.
- TotoBrief drawing 4987 (internal ID 12068) is synchronized with 15/15 local
  events. GOAL API contains all 15 exact fixture identities. Automatic
  candidate matching resolves 15/15 without drawing-specific code or manual
  aliases.
- The canary uncovered a blocking timing inconsistency: 12/15 GOAL kickoffs
  are earlier than TotoBrief `ended_at=2026-08-26T18:45:00Z`. Those rows are
  explicitly `timing_conflict`; only three rows are ordinary independent
  candidates. Five representative fixtures were independently confirmed at
  identical kickoffs through Sofascore. This is source evidence, not
  permission to reinterpret the betting deadline or generate a package.
- Official BaltBet rules require placement before the earliest event. For
  4987 the confirmed earliest kickoff is `2026-08-26T15:45:00Z` (18:45 MSK),
  so the conservative T-10 boundary is 18:35 MSK. TotoBrief `ended_at`
  (21:45 MSK) is unsafe as an operational cutoff for this drawing. The current
  collector exposes and blocks the conflict; scheduler-owned conservative
  cutoff propagation is the next P0 change.
- Focused provider/collector/morning regression: 86 passed. Full default suite:
  `2008 passed, 13 deselected in 191.10s`; repository Ruff, diff check, CLI
  smoke and protected-key leak scan passed.
- Canary artifact:
  `reports/canary/goal-api-4987/output-v3/schedule-source-candidates.json`.


## Free schedule-provider audit correction (2026-08-25)

No single free source can guarantee every arbitrary BaltBet event and permanent
account availability. TheSportsDB remains a useful keyless secondary source,
but its documented free tier does not support the previously proposed generic
team-ID search fallback; that roadmap item is closed as rejected rather than
implemented.

GOAL API is the strongest new football candidate for a controlled bake-off:
its free plan advertises 1,000 requests/day and its exact public catalogue lists
1,019 competitions, including Russia Second League B. It is not production
approved because the service is new and its own terms disclaim guaranteed
fixture coverage. SportsDataAPI is second choice because its official pages
contradict each other about free competition coverage. Neither source is wired
to the scheduler, ledger or package path. The next step is a candidate-only
10-drawing exact coverage/stability bake-off documented in
`research/free_schedule_provider_audit_20260825.md`.

The protected GOAL API key has now been validated. The free account reports a
1,000-request daily quota. A bounded drawing-4986 fixture canary found all
15/15 targets; the three apparent misses were only provider-name differences
(`Blackburn`, `Cambridge Utd`, and `Vladimir`). The source also supplied all
three events missing from the existing Sofascore/TheSportsDB union. One request
with Python's default user agent returned an unstructured 403, while all
subsequent requests with a stable TotoAI user agent succeeded; this must be a
tested transport contract, not hidden as empty coverage. Details are in
`research/goal_api_coverage_drawing_4986.md`.

API-Sports remains configured and must not be removed. Its current status call
still returns the semantic provider error `Your account is suspended`, so it
is retained for future recovery but cannot currently supply schedule data.

## Non-activating morning source collection repair (2026-08-25)

The morning CLI previously ran independent and UEFA-consensus source
collection only inside `if activate`, so a safe rehearsal produced a review
queue but reported `source_collector=null`. Source collection now runs whenever
a review queue exists. `--activate` controls only LaunchAgent installation.

A fresh identity-bound drawing-4986 rehearsal without `--activate` completed
in about 55 seconds and reported the expected source evidence: Sofascore 10/15,
TheSportsDB 12/15, source union 12/15, three unresolved events, and no ledger
mutation. Exact UEFA consensus promoted 0/15, so preparation correctly remains
`deferred`, with no scheduler plan, training package, operator package, or
wager. A regression proves that non-activating runs invoke both collectors and
cannot call the LaunchAgent installer.

## Drawing 4986 production CLI coverage check (2026-08-25)

The real `collect-schedule-sources` CLI completed successfully against the
immutable drawing-4986 review queue after reviewed-alias wiring and conflict
handling. Sofascore produced 10/15 independent candidates; TheSportsDB
produced 12/15; their union covered 12/15. TheSportsDB added events 180086 and
180088 beyond Sofascore. Events 180090, 180091 and 180092 remain unresolved.

TheSportsDB used its complete 30-request transport budget without exhausting
it (`attempted=30`, `skipped=0`, `budget_exhausted=false`). One catalog/ledger
alias conflict, normalized key `рапид вена`, was skipped deterministically and
reported through bounded `alias_conflicts_skipped` diagnostics. The ledger was
not mutated. Both sources remain independent and non-promoting, so this result
does not open the release gate and does not justify scheduler activation yet.

## Reviewed gender-safe team aliases for TheSportsDB (2026-08-25)

The versioned source-independent reviewed alias catalog now includes the 18
requested Cyrillic-to-canonical team mappings for nine drawing-4986 pairs.
TheSportsDB collector entry points preserve the catalog's canonical spelling
for query construction and normalize that same mapping for the existing exact
matcher. Deferred morning collection and the standalone collector both load
this reviewed source; Sofascore names remain lookup hints only and never become
trusted matcher aliases.

Network-free collector regressions resolve the seven previously rejected
Cardiff/Norwich, Blackpool/Lincoln, Cambridge/Millwall,
Fleetwood/Shrewsbury, Stoke/Hull, Southampton/West Ham, and Nottingham/Leeds
pairs. Stevenage/Reading and LASK/Celtic produce their exact canonical
forward/reverse query names. Explicit gender markers are retained, and
gender-incompatible provider events are excluded before matching; women's
variants do not inherit the unmarked men's mappings. An unrelated low-score
pair remains rejected.

Matcher pair/team/margin thresholds, the three-hour timing window, the
five-day search window, request budget, source authority, and promotion policy
are unchanged. Focused verification passed all 17 tests in
`tests/test_thesportsdb_schedule_collection.py` in 32.80 seconds. No network
request, ledger mutation, scheduler activation, package, wager, commit, or
remote publication was performed.

## TheSportsDB canonical-query and run-budget hardening (2026-08-25)

The independent schedule collector now constructs deterministic TheSportsDB
query candidates from the normalized original team name, directly available
canonical aliases, Cyrillic-to-Latin transliteration, and Latin home/away names
from an earlier independent candidate. One best Latin/canonical forward query
is prioritized, the reverse is bounded, and duplicate query strings are not
requested. Independent names remain lookup hints only and are not promoted to
matcher aliases or ledger evidence.

Women's/gender markers are preserved. Gender-incompatible canonical mappings
are ignored, so a women's target is never queried or matched through a men's
alias. The client now enforces a hard default/max transport budget of 30
requests per run. Valid cache hits occur before budget enforcement and consume
no transport; diagnostics and provider status report attempted, skipped and
budget-exhausted state without exposing the API key.

TheSportsDB and Sofascore remain independent and non-promoting with
`ledger_eligible=false` and `ledger_mutated=false`; release and promotion
policy did not change. Team-ID lookup and `/eventsnext.php` fallback were not
added and remain a possible separate next step. The two focused provider and
collector test files pass 28 tests.

## TheSportsDB UTC-naive event-time normalization (2026-08-25)

A live TheSportsDB `/searchevents.php` smoke request returned HTTP 200 but the
event parser rejected the provider's timezone-naive `strTimestamp` with
`TheSportsDB timestamp must include a timezone`. The event parser now applies
the provider-specific contract documented by TheSportsDB: a timezone-naive
`strTimestamp` is interpreted explicitly as UTC and every parsed event kickoff
is normalized to an aware UTC datetime. Explicit offsets retain their instant
and are converted to UTC. The shared/internal timestamp parser remains strict,
so cache timestamps and unrelated providers do not acquire this exception;
malformed event timestamps still fail closed.

Known unknown timing remains non-actionable. `TBD`, `Time TBD`, an equivalent
`strTime` marker, or a scheduled/fixture/not-started row carrying a date-only
midnight placeholder is normalized to `status=unknown` and
`eligible=false`. A missing `strTimestamp` with a known event date and TBD time
is retained only as an ineligible diagnostic placeholder. TheSportsDB remains
independent, non-promoting and `ledger_eligible=false`; this parser correction
does not change release policy.

## Provider hardening and TheSportsDB v1 free access (2026-08-25)

The documented TheSportsDB v1 event-day/search provider is implemented behind
the existing non-promoting schedule-source collector. It now uses the
documented public v1 key `123` when `THESPORTSDB_API_KEY` is absent; a configured
override remains redacted. Only the official TheSportsDB HTTPS host and exact
v1 path are allowed before transport. The transport enforces five-day windows,
30/minute pacing, ten-second default timeout, one retry by default, immutable
content/hash-bound snapshots and secret-safe API-Sports-shaped diagnostics.

Normalized candidates retain provider event/team IDs, sport, competition,
home/away, UTC kickoff, status, public source URL and capture/provenance hashes.
Only pre-kickoff scheduled/not-started rows enter the existing alias and
same/reversed-orientation matcher. The collector queries both team orientations
and deduplicates provider event identities. Collection reports TheSportsDB
independently from Sofascore, but every accepted row remains
`ledger_eligible=false`, `ledger_mutated=false`, and non-promoting; the
official-plus-independent reviewed promotion policy is unchanged. No live
TheSportsDB request, ledger mutation, scheduler activation, package, wager,
commit or remote publication was performed for this implementation.

API-Sports public exception strings retain their established caller contract;
new HTTP/provider/quota detail is available only through structured,
secret-safe diagnostics and existing artifacts. Preparation likewise preserves
specific sanitized provider reasons such as `future date unavailable` instead
of replacing them with a generic exception class. A controlled health check on
2026-08-25 at 10:33 MSK still returned HTTP 200 with provider semantic error
`access: Your account is suspended`; quota remained available, so API-Sports
is currently unusable because the provider account is suspended, not because
of project quota or request exhaustion.

## Morning wrapper CLI compatibility (2026-08-24)

Generated morning dispatcher wrappers now obtain their complete
`morning-dispatch` argv from one scheduler command builder. The generated argv
contains only current CLI options; the removed `--training-category` option is
not part of the generator. A contract regression shlex-parses the command from
the generated shell wrapper and passes that exact argv to the Typer CLI with
`--help`, so a removed or unknown generated option fails the test before any
network or dispatcher execution.

The replacement candidate was generated, but not installed or executed, at
`reports/rehearsal/morning-dispatcher-v4/`. It preserves `StartInterval=3600`
and the exact 08:00, 10:30, 12:00, 17:05, 17:12 and 17:20 calendar triggers.
The wrapper SHA-256 is
`dcff05772c37c50db189bcdbc3c5551533cd984f8438678073afcadfd187a14b`, the
plist SHA-256 is
`72bf0760a1213f9838da73212175b32cf6cd7bc9f52e029f8de225a4c4f5762d`.
The wrapper exports optional TheSportsDB environment overrides only when
present and persists neither the public default nor any private override. It
remains an uninstalled candidate; no LaunchAgent was loaded.

## Drawings 4982-4985 catch-up (2026-08-24)

Drawing 4982 has a verified complete, non-VOID actual vector
`X211112211X2X21`. Scheduler plan `7dddf0c68bf09df1` produced a non-actionable
`TRAINING_PAPER` package of 166 coupons for 4,980 RUB. Its best realized coupon
reached 7/15; hit13, hit14 and hit15 were zero. The best coupon missed positions
1, 3, 6, 8, 9, 11, 13 and 14. This is paper audit evidence and does not
establish profitability.

Drawing 4983 is complete 15/15 with no `VOID`; the verified actual is
`2111XX21XX2XX22`. Drawing 4984 is complete 15/15 with no `VOID`; the verified
actual is `11112X1X1121121`. Neither drawing has a scheduler-owned package, so
no package performance or return is attributed to them. The concise records
are in `reports/audits/drawing-4982-package-audit.md`,
`reports/audits/drawing-4983-package-audit.md`, and
`reports/audits/drawing-4984-package-audit.md`.

At the latest passive retry scheduled for 21:00 MSK (18:00 UTC), drawing 4985
remained **deferred with all 15 events unresolved**. API-Sports returned
provider semantic errors for the near dates and plan-coverage errors for the
expanded dates. Independent discovery found five candidates, but none had the
required official/review evidence; official consensus promoted 0/15. No
scheduler plan, scheduler-owned package, operator result, or operator marker
was created.

## Drawing-4981 package audit (2026-08-21)

The supported result synchronization refreshed drawing 4981 (internal ID
12050) to a complete 15/15 resolved result: `2X1121XXXX12XX2`. The
scheduler-owned package contained 166 unique coupons for 4,980 RUB. The exact
actual vector was not selected; the best realized coupon reached 8/15, with
hit13, hit14, and hit15 all zero. Missed positions for that best coupon were
1, 4, 6, 7, 9, 12, and 15. Every actual sign was present in the per-event
brief/union, so the result is a combinatorial package-selection miss, not a
source, cancellation, or result-completeness defect. The audit is recorded in
`reports/audits/yesterday-package-audit-20260821.md` and remains paper-only
evidence.

## Scheduler training archive binding (2026-08-21)

Scheduler-owned `TRAINING_PAPER` input resolution is bound to the canonical
morning-record `detail_sha256` and a verified `RawArchive` snapshot under the
plan's project-bound immutable archive. An absent, malformed, or mismatching
snapshot fails closed; the mutable `data/raw/drawing_<id>.json` cache is never
used as a fallback. Focused regression coverage verifies both the matching
archive path and a mutable-cache hash mismatch without running quality-v2.

## Morning discovery and drawing-4982 training package (2026-08-20)

The generated generic morning LaunchAgent now combines its fixed reviewed
times with an hourly drawing-neutral discovery trigger. This removes the
17:05/17:12/17:20-only assumption that missed drawing 4982 after drawing 4981's
variable 18:00 MSK deadline, while preserving the request coordinator,
provider cache/quota reserve, process lock, and exact-drawing idempotency. The
minimum accepted discovery interval is 900 seconds and the default is 3,600.

READY morning dispatch now ensures an immutable scheduler-bound
`TRAINING_PAPER` package using the production baseline brief/cover generator
and configured bank/stake/category. It is explicitly non-actionable and does
not modify scheduler state, release authorization, operator result, or marker
files. The supported local CLI generated drawing 4982's category-13 artifact
for plan `453829753fa55b5f`: 22 coupons, 660 RUB at stake 30 from the configured
4,980-RUB bank, category guarantee `PASS`. The result is
`reports/rehearsal/evening-4982-20260821T160000Z/training-package/training-package-result.json`;
its paper payload is under immutable checkpoint
`16e4b4659b28-e93b972d20c6/`. A second CLI run reused identical bytes. The
scheduler-state SHA-256 remained
`4f96018bf7f0925bad7ddf1be027b3af64352a4df18a1172dad6293d13147ab3`;
`operator-result.json`, `.bet-ready`, and `.no-bet` remain absent.
The never-installed `morning-dispatcher-v3` candidate later proved stale: its
wrapper retained the removed `--training-category` CLI option. It remains a
historical artifact and is superseded by the generated v4 compatibility
candidate documented above.

## Experimental manual release and drawing 4982 (2026-08-20)

The default quality-v2 release gate remains paper-only and profitability is not
proven. A separate explicit command now creates one immutable authorization for
an exact schema-v6 scheduler plan before T-10. Only a fresh `final`
`STRUCTURAL_PASS` may then reach the existing manual operator-export gateway;
warmup/LKG/degraded packages remain non-actionable and automatic wagering stays
disabled. Operator result schema v3 records the release mode, authorization
hash, risk acknowledgement and `profitability_proven=false`. Preflight status
exposes this state before evening execution.

Drawing 4982 is the active BaltBet drawing: internal ID 12054, deadline
2026-08-21 19:00 MSK, fingerprint
`581cdbbee88e75525f9b562e0bc43e8c450fd93fbed886ee592ae3bcb6be17d3`.
Identity/probabilities and kickoff times are now mapped 15/15. Exact schema-v6
plan `453829753fa55b5f` exists with its plan-bound experimental authorization;
the historical passive retries that resolved the drawing remain audit
evidence. Retry stdout contains a structured child-result record instead of
remaining empty.

Git cleanup is complete. PR #11 merged the 22 local post-PR commits plus the
missing drawing-4964 reviewed schedule fixture; PR #12 merged eleven historical
task-context directories. Local `main` equals `origin/main`, and the release
work continues from that exact base.

## Git integration boundary after drawing 4981 (2026-08-20)

The former remote branch `codex/operator-export-timing-escalation` was merged by
GitHub PR #10 at commit `1498ba6` and deleted remotely, but local development
continued for 22 commits. The local branch was rebased without conflicts onto
fresh `origin/main` (`3241d85`), so it now contains only those 22 subsequent
commits over main. Full verification exposed one omitted repository fixture:
the committed drawing-4964 scheduler regression referenced the reviewed
schedule catalog, but `data/reviewed-schedule/4964/` had remained untracked.
The exact catalog and its source evidence are now tracked; the catalog SHA-256
is `68e98c8f006ddca04e193a1d06d3f23def57e498f4c02c51d8a9e3c18062895a`.
The owner explicitly authorized publishing and merging the reconciled branch.
Eleven previously untracked `plans/` context directories from drawings
4963–4967, the data audit, free-source audit, and paper/post-draw work were
reviewed for credential-like content and committed as historical task
artifacts. They are not project-memory authority and do not override this
file, `DECISIONS.md`, or `ROADMAP.md`.

The first drawing-4981 evening LaunchAgent trigger ran at 16:00 MSK and
completed `tls_preflight` successfully at 16:02:47: exit code 0, empty stderr,
and hash-chained scheduler state marked the phase `complete`. The wrapper still
printed `Outcome: no-op / no due scheduler phase` because the CLI reports no
terminal package result after a successful non-terminal preflight. Treat the
state transition as authoritative for this run and fix this misleading
observability message only after the live T-10 cycle.
The second trigger ran at 16:30 MSK and completed `api_preflight` at 16:32:16
with exit code 0, empty stderr and no failure details. No `final-input.json` is
expected until the T-45 warmup; the next scheduled phase is
`freshness_preflight` at 17:00 MSK.

Drawing 4981 then completed its evening paper cycle. `freshness_preflight`
passed, T-45 warmup failed retryably on TotoBrief HTTP 429 plus a stale
60-second cache, and the independent T-30 refresh recovered: it froze a 15/15
input and produced a 166-coupon/4,980-RUB last-known-good package. Final started
at 17:40:10 and completed at 17:45:47 with exit code 0. The terminal operator
result is `NO BET / FINAL_FRESH`, reason
`quality_v2_real_money_release_gate_closed`; automatic wagering remains false.
The final package was fully calculated but is not actionable.

Before T-10, the exact final input was also used for a hash-bound prospective
equal-input comparison at
`reports/research/prospective-strategy-comparison-4981-20260820T144010Z/`.
Modeled P(13+) values were current EV/crowd 0.00100249, BK-only 0.02228851,
Cover-13 0.00616687 and Cover-14 0.01701016. Costs were respectively 4,980,
4,980, 660 and 2,700 RUB. This is one paper-only prospective observation, not
a winner or profitability verdict; settlement must wait for complete results.

## Legacy-100 diagnostic and official payout audit (2026-08-20)

The unchanged resumable legacy benchmark completed 100 drawings at bank/stake
4,980/30 in 1:50:22. It is explicitly
`LEGACY_RETROSPECTIVE / NOT RELEASE EVIDENCE / NOT ACTIONABLE`; current SQLite
probabilities do not prove pre-deadline chronology.

Average best hits were BK probability-only 8.700, current EV/crowd 7.050,
Cover-13 8.260 and Cover-14 8.960. Against BK-only, paired mean best-hit
differences and nominal 95% bootstrap intervals were EV/crowd -1.650
[-2.210, -1.120], Cover-13 -0.440 [-0.650, -0.230], and Cover-14 +0.260
[0.060, 0.460]. BK-only and Cover-14 each recorded three 13+ packages;
BK-only recorded the only 14+. Cover-14 used 2,757 RUB on average versus the
full 4,980 for BK/EV, so this is not an equal-cost winner verdict. Evidence:
`reports/research/legacy-strategy-benchmark-100-20260820/`.

The result confirms a measured defect in the current EV/crowd package for hit
probability: its modeled P(13+) is about 0.00108 versus 0.01888 for BK-only,
and every evaluated EV package omitted at least one actual-result outcome. It
does not prove EV is unprofitable because its monetary score depends on
unverified crowd-joint and prize-fund assumptions.

The current official BaltBet rules were audited against the EV code. The
published 8/18, 4/18, 2/18, 1/18, 1/18, 1/18+1/10 and 1/18+9/10 allocations
match `category_funds()`, and categories are cumulative. However, TotoBrief
stores no separate `Possible winnings` field, while TotoAI currently uses
`pool_sum * prize_fund_factor` as a disclosed proxy. All 420 stored result
snapshots have `payments = null`, so observed payout/ROI is unavailable and
must not be fabricated. Evidence:
`research/baltbet_official_payout_audit_20260820.md`.

The sealed BK-only hybrid experiment already ended with `STOP`, so the
Legacy-100 result must not reopen another BK-only optimizer on reused data.
Legacy-500 was resumed only to 116 checkpoints and then deliberately stopped:
the non-chronological rows and absent payout evidence cannot prove
profitability, while Legacy-100 already exposed the EV/crowd hit-probability
defect. The checkpoints remain resumable, but 500/1,000 are not the current
priority. The immediate next evidence step is automatic prospective archival
and settlement of the four existing strategies on newly arriving drawings.
Any later optimizer hypothesis requires a preregistered protocol and a new
untouched/prospective window.

The partial Legacy-500 resume exposed a reproducibility boundary: scheduler plan 4975
was correctly bound to schedule-evidence SHA-256 `43a61456...`, while the shared
production ledger had subsequently advanced. The exact historical ledger and
its referenced review documents were recovered from Git commit `9be3cdc` into
the non-release immutable bundle
`reports/research/legacy-strategy-input-4975-v2-20260820/`. A rebuilt research
plan passed strict loading and resumed the existing checkpoints without
changing strategy configuration. The live production ledger was not replaced
or modified. The partial run stopped cleanly at 116/500; no checkpoint was
discarded.

## Resume audit and drawings 4975-4980 (2026-08-20)

The pause audit found drawings 4975-4980 finished and drawing 4981 active.
Drawing 4980 was missing terminal rows locally; an explicit public TotoBrief
result sync created the complete hash-bound snapshot with actual
`1111XX112X2XX1X`. All six finished drawings now have 15/15 outcomes and a
genuine pre-deadline probability snapshot. The `backtest_probability` health
contract passes 6/6.

Drawing 4975 completed its real paper lifecycle: result sync, immutable
settlement, review request and reviewed postmortem are complete. The frozen
166-coupon / 4,980 package reached only 8/15. It exposed every actual outcome,
but eight actual signs had less than 10% coupon exposure and average actual
outcome exposure was 35.6%. Its old result snapshot has no
`raw_snapshot_sha256`, so strict inventory/settlement health remains 5/6 and
the strict strategy benchmark correctly excludes 4975. This is evidence debt,
not a missing result.

The five newly eligible strict counterfactual drawings 4976-4980 produced
average best hits BK-only 8.6, EV/crowd 6.6, Cover-13 7.4 and Cover-14 8.4;
all recorded zero 13+. Combining these five with the previous 13 immutable
drawings gives 18 unique strict rows: BK-only 8.889, EV/crowd 6.889,
Cover-13 8.167, Cover-14 8.889, with one Cover-14 13+ and no 14+/15. The
sample remains below the predeclared 30-drawing interpretation floor and does
not establish a winner or profitability. Evidence:
`reports/research/new-drawings-4975-4980-20260820/` and
`reports/research/strict-strategy-benchmark-20260820-new6/`.

The resumable legacy 100-drawing diagnostic completed with checkpoint schema
v3 and unchanged bank/stake 4,980/30. It remains
`LEGACY_RETROSPECTIVE / NOT RELEASE EVIDENCE`. A later 500-row resume was
stopped at 116 checkpoints because expanding non-chronological evidence cannot
establish profitability; prospective collection now has priority.

Active drawing 4981 is now READY and playable 15/15. Public official UEFA v5
match JSON and independent Sofascore event JSON agreed exactly on identity,
orientation and kickoff for user events 7 (Hearts - SK Rapid Wien,
18:45 UTC) and 9 (Hajduk Split - Rakow, 19:00 UTC). Their four pre-deadline
snapshots, SHA-256 values and two review documents were frozen under
`data/schedule-evidence/`; the reviewed ledger resolves both rows at high
confidence. The already installed passive retry ran automatically at 12:00
MSK with return code 0, changed coverage from 13/15 to 15/15 and activated
evening plan `5caf88df9bdfe566` for bank/stake 4,980/30. Launchd confirms the
production-scheduler paper job is loaded with eight triggers from 16:00 to
17:50 MSK. This is operational readiness only: quality-v2 remains paper-only,
no wager is authorized, and no package exists before a scheduler trigger.

The first reusable authoritative schedule adapter is now implemented locally.
For a deferred review queue it pages the public UEFA v5 date feed, requires an
exact TotoBrief-to-UEFA localized home/away alias match, re-fetches the official
match by ID, resolves Sofascore through the official English names, and promotes
only an identical orientation/kickoff consensus captured before kickoff. It
freezes both source snapshots plus a hash-bound deterministic review document;
ambiguity, late evidence, source/status drift and kickoff disagreement remain
unresolved. `morning-dispatch --activate` now runs this consensus path
independently of the existing non-promoting Sofascore discovery collector, so a
source failure on either side cannot suppress the other's diagnostics. A
network-free replay against the two frozen 4981 pairs promoted 2/2 into an
isolated empty ledger. A separate live public-source canary against the current
UEFA and Sofascore responses also promoted 2/2 into an isolated ledger without
touching production evidence. Verification: 73 focused schedule/morning tests
and the full default suite (`1904 passed, 13 deselected`) pass; Ruff and
`git diff --check` pass. Broader non-UEFA authoritative adapters remain
pending.

Pre-deadline shadow evidence was also frozen for drawing 4981. API-Sports
sports-stat collection made 12 requests and returned 0/15 complete venue rows,
10 partial and 5 missing; the resulting probability artifact is
`NOT_ACTIVATED / INSUFFICIENT_EVIDENCE`, uses BK fallback for all 15 events and
cannot change the package. The Odds API control checkpoint spent two credits
(492 remaining) and matched 3/15 events exactly; 12/15 remained fallback. This
confirms that neither current free feed is broad enough to replace BK for this
drawing, while preserving prospective evidence for later settled evaluation.

## BK-top control and paired benchmark intervals (2026-08-14)

Strict and legacy strategy reports now include an explicit deterministic
single-coupon `BK_TOP_SINGLE_CONTROL` plus paired per-drawing best-hit
comparisons. Intervals use a fixed-seed 10,000-replicate percentile bootstrap;
fewer than 30 drawings always sets `interpretation_allowed=false`. Legacy
checkpoint schema is v3 so old incomplete control rows cannot resume silently.

The full strict 13-drawing v2 run completed in 14:44 and all manifest/artifact
hashes verified. Average hits for the one-coupon BK-top control were 6.538.
Against the 166-coupon BK probability-only package, mean best-hit deltas were:

- EV/crowd: -2.000, nominal 95% CI [-3.462, -0.538];
- Cover-13: -0.538, nominal 95% CI [-1.077, 0.000];
- Cover-14: +0.077, nominal 95% CI [-0.692, 0.923].

All strict intervals remain non-interpretable at n=13. The run confirms the
current EV/crowd weakness is worth testing on the physically separate legacy
diagnostic, but it does not prove a winner, edge, or profitability. Evidence:
`reports/research/strict-strategy-benchmark-20260814-all13-v2/`; manifest
SHA-256 `5b08ec50ab9304ae253a97dd5ebca43036134f341e0fb8680153329e78986c5f`.
Verification for this slice: `1900 passed, 13 deselected in 123.05s`; Ruff and
`git diff --check` passed.

## Resumable legacy strategy diagnostic (2026-08-14)

The physically separate `legacy-strategy-benchmark` path is implemented for
the 1,672 probability-eligible rows that lack strict pre-deadline evidence. It
does not fabricate an `as_of`: every input/report is
`LEGACY_RETROSPECTIVE`, `chronology_verified=false`, `NOT RELEASE EVIDENCE`,
non-actionable, and excluded from strict/prospective metrics. Actual outcomes
are excluded from the source/input hash.

The command runs the same EV/crowd, BK-only, Cover-13 and Cover-14 engines with
the production quality-v2 objective and writes one atomic hash-bound checkpoint
per drawing. Exact source/config/input agreement is required to resume. A real
drawing-4974 canary completed in 1:04 and its immediate rerun resumed in zero
seconds. The legacy DB gave EV best 7/15 while the true pre-deadline strict input
gave 5/15, an observed warning that post-deadline/current-state rows can change
the apparent result. Verification: `1899 passed, 13 deselected in 114.91s`;
Ruff and `git diff --check` passed. The 100/500/1,000 legacy diagnostics remain
pending.

## Strict historical strategy benchmark (2026-08-14)

Phase 2 now has a leakage-safe strict runner and report bundle. The new
`historical-strategy-benchmark` command selects only immutable RAW evidence
captured at/before deadline, verifies archive bytes, reconstructs the exact
prediction input without raw result/score fields, loads actual outcomes from a
separate terminal snapshot, applies settlement-compatible VOID scoring, and
records input/config/package/raw/result hashes. It reports actual hit
distribution, 13+/14+/15, exposure, zero-exposure events, modeled category
probabilities, cost/unused bank, runtime/fallback and package overlap.

Canaries on one and three drawings completed first. The complete available
strict run then evaluated all 13 eligible drawings at bank/stake 4,980/30 in
15:08 with zero strategy timeouts. Average best hits were:

- EV/crowd current: 7.00;
- BK probability-only: 9.00;
- TotoBrief-style Cover-13: 8.46;
- TotoBrief-style Cover-14: 9.08.

Only Cover-14 reached 13+, once (drawing 4966); no strategy reached 14+ or 15.
EV and BK used the full 4,980; Cover-13 and Cover-14 used 660 and 2,700 on
average, so this is not an equal-cost strategy verdict. EV's large deficit to
BK is a measured diagnostic that must be investigated, not a license to tune on
13 rows. Artifacts are under
`reports/research/strict-strategy-benchmark-20260814-all13/`, with verified
artifact and manifest hashes. They are explicitly
`STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE / NOT RELEASE EVIDENCE`, non-actionable,
and cannot support a profitability claim. Next is the physically separate
legacy 100/500/1,000 diagnostic. Verification after this implementation:
`1895 passed, 13 deselected in 119.95s`; Ruff and `git diff --check` passed.

## Historical chronology gate correction (2026-08-14)

The previous data-health contract treated the presence of any raw TotoBrief
snapshot as frozen historical evidence. A direct audit of all 713 registered
raw rows found only 173 rows, across 17 drawings, captured at or before the
corresponding deadline. Of the 398 drawings previously labelled strict, only
13 also have a genuine pre-deadline raw snapshot. The other 385 had only
post-deadline raw evidence and cannot be used as strict historical inputs.

Data-health contract 1.2.0 now requires at least one existing, non-symlink raw
payload/metadata pair whose registered `captured_at` is at or before
`Drawing.ended_at`. It reports `predeadline_raw_snapshot_count` and
`latest_predeadline_raw_snapshot_at`, and `historical_inventory` fails closed
with `missing_predeadline_raw_snapshot`. The current full audit is 2,216
drawings: 13 strict chronological rows and 2,203 rejected rows. Evidence is in
`reports/research/data-health-chronology-20260814/`.

Verification after the chronology gate change: 1,888 default tests passed,
13 heavy tests were deselected, Ruff passed, and `git diff --check` passed.

Consequently, phase 2 will run a 3–5 drawing strict canary and then all 13
eligible rows only as pipeline-integrity evidence. Historical 100/500/1,000
runs are explicitly legacy diagnostics, never release evidence. The
prospective pre-deadline holdout is the primary path to a strategy verdict.

## Drawing 4975 equal-input strategy comparison (2026-08-14)

The first artifact-bound `compare-package-strategies` run completed on the
immutable final drawing-4975 input and schema-v6 scheduler plan. It wrote one
hash-bound manifest, JSON/CSV/Markdown summaries and four separate paper
package files under
`reports/research/strategy-comparison-4975-20260814/`. All strategies used
input SHA-256
`ee938dd3413e390a589c498a2295cf2736b9ff42965a3c94a274dadd52e72cd9`.
The EV adapter reproduced the actual 166-coupon final paper package exactly in
both order and set.

Modeled results for this one snapshot are:

- EV/crowd: 166 coupons, 4,980; P(13+) 0.00226572, P(14+) 0.00022230,
  P(15) 0.00000916;
- BK-only: 166 coupons, 4,980; P(13+) 0.01333865, P(14+) 0.00202121,
  P(15) 0.00014290;
- Cover-13: 22 coupons, 660; P(13+) 0.00319861, P(14+) 0.00031179,
  P(15) 0.00001273; exact guarantee passed;
- Cover-14: 90 coupons, 2,700; P(13+) 0.00925712, P(14+) 0.00107714,
  P(15) 0.00005283; exact guarantee passed.

This is diagnostic evidence that the current EV/crowd objective can materially
diverge from pure hit probability. It is not enough to declare BK-only the
winner: actual finished outcomes across the frozen historical benchmark are
required. The command remains `RESEARCH/PAPER`, non-actionable, and cannot
place a wager or open the release gate.

## Equal-input strategy contract and adapters (2026-08-14)

Phase 1 implementation has started after the drawing-4975 terminal state. New
module `optimizer.strategy_comparison` defines a frozen 15-event input contract
and validated strategy result contract. The input binds drawing identity,
fingerprint, source capture time, `as_of`, deadline, dynamic bank/stake,
pool/jackpot/winnings and ordered BK/crowd matrices. Future evidence, invalid
event order, non-divisible banks and malformed probabilities fail closed.

Thin adapters now expose the existing engines as `EV_CROWD_CURRENT`,
`BK_PROBABILITY_ONLY`, `TOTOBRIEF_STYLE_COVER_13`, and
`TOTOBRIEF_STYLE_COVER_14`. BK-only does not read crowd probabilities. The EV
adapter receives the same frozen BK/crowd matrices and caller-bound `EVConfig`.
Cover variants invoke the existing brief generator and require the independent
exact verifier to pass. Every result enforces unique 15-sign coupons, exact
cost, dynamic budget, input/config/package hashes and exact modeled P(13+),
P(14+) and P(15).

Verification: nine focused strategy/CLI/report tests pass; the full default
suite passes with 1,885 tests and 13 deselected; Ruff and diff-check pass.
Phase 1 is complete. Production scheduling and the closed real-money gate are
unchanged; the strict historical canary is next.

## Drawing 4975 terminal evening result (2026-08-14 16:52 Moscow)

The complete automatic evening sequence reached terminal state without a
runtime failure. Primary final attempt
`final-01-20260814T134016580964Z-c9c3e3ef` ran from
`2026-08-14T13:40:16.580964Z` through `13:44:01.046512Z` (224.47 seconds),
exit code 0 and zero failure details. It produced `FINAL_FRESH` paper evidence
with decision `NO BET` solely because
`quality_v2_real_money_release_gate_closed`; this is the current intentional
paper-only policy, not a package-computation failure.

The immutable final paper package contains 166 unique coupons, cost 4,980,
and 166 valid `30; outcome x 15` lines. Its path is
`reports/rehearsal/evening-4975-20260814T140000Z/paper-package/checkpoints/00e224fcfa88b102f27daa8e/paper-package.txt`
and its SHA-256 is
`ff1ad616140a9d4f94dd1f3e67475c67b17a8cfa6a67f742b6cc16fed2a4fbe6`.
The artifact is non-actionable and automatic wagering is false.

The 16:50 T-10 trigger raised LaunchAgent runs to seven, exit code 0. It
removed the operator-facing LKG pointer and coupon path as designed while
retaining immutable paper/audit evidence. Post-draw LaunchAgent
`com.toto-ai.post-draw-12033` is installed and loaded, with its first real
result-sync slot at 2026-08-15 12:00 Moscow and bounded three-hour retries
through 2026-08-16 03:00 Moscow. The evening half of phase 0 is complete;
result synchronization, settlement and postmortem remain pending.

## Drawing 4975 refresh evidence (2026-08-14 16:37 Moscow)

The fifth automatic evening trigger completed successfully. Launchd reports
five runs and exit code 0. Attempt
`refresh-01-20260814T133019452143Z-a3e476e3` ran from
`2026-08-14T13:30:19.452143Z` through `13:35:10.720875Z`, status `complete`,
with zero failure details. It created refreshed checkpoint
`refresh-01-20260814T133019452143Z-a3e476e3-ff1ad616140a`.

The refreshed checkpoint has 166 CSV rows and 166 unique coupons, selected
cost 4,980, effective bank 4,980, and 166 unique valid BaltBet upload lines.
The upload SHA-256 is
`ff1ad616140a9d4f94dd1f3e67475c67b17a8cfa6a67f742b6cc16fed2a4fbe6`.
The operator result remains non-actionable `NO BET` with status
`LAST_KNOWN_GOOD_DEGRADED` before final execution, as required by the closed
release gate. The next automatic trigger is primary final at 16:40 Moscow.

## Drawing 4975 warmup and LKG evidence (2026-08-14 16:23 Moscow)

The fourth automatic evening trigger completed successfully. Launchd reports
four runs and exit code 0. Attempt
`warmup-01-20260814T131523643983Z-f27c7ad1` ran from
`2026-08-14T13:15:23.643983Z` through `13:20:40.148532Z`, status `complete`,
with zero failure details. It created checkpoint
`warmup-01-20260814T131523643983Z-f27c7ad1-b13f8050c6ec` under the drawing-4975
last-known-good store.

The checkpoint has 166 CSV rows and 166 unique coupons, selected cost 4,980,
effective bank 4,980, and 166 unique `baltbet-upload.txt` lines. Every upload
line passed the exact `30; outcome x 15` format check. The package SHA-256 is
`fbc04911911af94b73d2c701e8708d4df51ff568b6a2f74680f8d1ad718694c5`; the
upload SHA-256 is
`b13f8050c6ec68da61ae1f5dfbcaa67bfa244d92654281bdad017b743ea26673`.
This is a non-actionable paper/LKG artifact: the quality-v2 real-money release
gate remains closed. The next automatic trigger is refresh at 16:30 Moscow.

## Drawing 4975 freshness evidence (2026-08-14 16:02 Moscow)

The third automatic evening trigger completed successfully. Launchd reports
three runs and exit code 0. Attempt
`freshness_preflight-01-20260814T130018316198Z-a3a97623` ran from
`2026-08-14T13:00:18.316198Z` through `13:01:28.412427Z`, status `complete`,
with zero failure details. Terminal remains null. The next trigger is warmup at
16:15 Moscow.

## Drawing 4975 API preflight evidence (2026-08-14 15:32 Moscow)

The second loaded evening trigger also completed automatically. Launchd now
reports two runs and exit code 0. Attempt
`api_preflight-01-20260814T123008095081Z-a9b7695e` ran from
`2026-08-14T12:30:08.095081Z` through `12:31:12.061655Z`, status `complete`,
with zero failure details and the validated target/data/config/catalog reason.
Terminal remains null as expected before final publication. The next trigger
is 16:00 Moscow (`freshness_preflight`).

## Drawing 4975 live trigger evidence (2026-08-14 15:02 Moscow)

The first loaded evening LaunchAgent trigger executed automatically. Launchd
reports one run and exit code 0. Scheduler state records attempt
`tls_preflight-01-20260814T120007817342Z-5651ee69` from
`2026-08-14T12:00:07.817342Z` through `12:01:16.900047Z`, status `complete`,
with zero failure details and reason `target, data access, configuration, and
override catalog validated`. The terminal field is still null, as expected at
T-120. The next planned trigger is 15:30 Moscow for API preflight. Evidence is
under `reports/rehearsal/evening-4975-20260814T140000Z/`.

## Active product-validation plan (2026-08-14)

The user approved a full staged plan at
`plans/TOTOAI-PRODUCT-VALIDATION-20260814/plan.md`; live progress is tracked in
the adjacent `progress.md`. The critical path is: close the complete live 4975
lifecycle, implement equal-input EV/BK-probability/TotoBrief-style strategies,
run historical benchmarks, correct only measured objective defects, evaluate a
leakage-safe sports residual model, and then run a predeclared prospective
paper holdout. Independent schedule/source and sports-data collection may grow
in parallel but cannot alter production packages before their gates pass.

An implementation stage is not complete merely because code exists. It needs
tests, frozen or live execution evidence, durable artifacts, memory updates and
an explicit exit-criteria check. Project status after every stage must list
completed work, current work, blockers and the next action. Automatic wagering
remains prohibited and no profitability claim is allowed before the release
gate.

## Free-source coverage baseline (2026-08-14)

A local, network-free audit now records the currently stored provider evidence
at `reports/research/free-source-audit-20260814/summary.md`. API-Sports external
odds cover 10 drawings / 150 events with 72.67% unique matching and 68.00%
usable consensus; 48 events use fallback. The Odds API has only one stored
drawing / 15 events, with 4/15 matching and 11 fallbacks. These are market
coverage figures, not sports-feature coverage.

The drawing-4975 API-Sports sports-statistics snapshot still has zero complete
venue-history events, ten partial rows and five missing rows; the sports branch
therefore falls back to BK for all 15 events. Sofascore found independent
schedule candidates for the five schedule gaps but cannot promote production
evidence without an official source. Phase 5 remains `PENDING`: neither the
30-drawing/450-event evidence minimum nor 70% valid sports-feature coverage has
been reached, and no predictive or profit improvement is claimed.

Official documentation was reviewed for the next free candidates. The first
shadow pilot should be football-data.org because its free tier exposes
current-season fixtures, team matches and TOTAL/HOME/AWAY tables for 12 top
competitions. Its narrow competition list means it cannot be the sole source.
TheSportsDB and OpenLigaDB are secondary identity/schedule candidates;
StatsBomb Open Data is suitable for offline feature research, not broad live
coverage. No adapter is activated by this review. The durable source notes are
in `knowledge/free_sports_sources.md`.

The phase-1 code inventory is also complete without changing live behavior.
Current EV/crowd, top-probability BK-only, and brief/Cover engines already
exist; the missing work is a shared immutable input/result contract, thin
adapters, exact equal-input validation, category-13/category-14 Cover variants,
and one comparison command. The implementation sequence and tests are frozen
in `plans/TOTOAI-PRODUCT-VALIDATION-20260814/phase1-inventory.md`. Coding starts
only after the drawing-4975 terminal result is recorded.

## Historical data eligibility finding — superseded (2026-08-14)

The first audit covered 2,215 drawings and reported 398 as
`historical_inventory`-healthy, but it did not validate raw-snapshot capture
time. This count is superseded by contract 1.2.0: only 13 rows have genuine
pre-deadline raw evidence plus complete strict inputs. A further 1,672 satisfy
the weaker `backtest_probability` contract.
There are no duplicate visible numbers. Numbers 3,843 and 3,844 are absent
locally, but TotoBrief's own public results listing also skips directly from
3,842 to 3,845; this is upstream numbering behavior rather than a local
ingestion loss. The health contract still needs hash-bound upstream-gap
evidence to suppress that false-positive metadata failure. The last 100
contain 78 strict-healthy and 79 probability-backtest-eligible drawings.

The plan no longer treats 500/1,000 old drawings as frozen release evidence.
Phase 2 must publish the current strict-13 benchmark separately from
100/500/1,000 legacy retrospective diagnostics. Thirteen drawings are not
enough to choose a winner; they validate the pipeline only. Legacy rows are
useful for finding large strategy defects but cannot support release or profit
claims. Missing historical pre-deadline snapshots cannot be reconstructed
honestly after the fact. Details are in
`plans/TOTOAI-PRODUCT-VALIDATION-20260814/phase2-data-eligibility.md`.

## Source collection, sports comparison, and 4974 review (2026-08-14)

The first safe automatic public schedule-source collector is implemented and
wired into deferred `morning-dispatch --activate`. It consumes the immutable
review queue, searches Sofascore with target names plus reviewed aliases,
stores raw hash-bound snapshots, and emits explicit candidate/conflict/missing
records. It never mutates the production schedule-evidence ledger: Sofascore
is independent evidence, so an official source and review are still required
before promotion. A real drawing-4975 probe found independent candidates for
all five previously missing events (5/5, zero unresolved) without changing the
bound ledger.

Mixed canonical pin sets no longer abort sports-stat collection. API-Sports
pins are collected normally; reviewed/schedule-only pins become explicit
per-event `preparation_not_ready` misses and fall back to BK. The drawing-4975
audit produced 10 partial API-Sports rows and five explicit misses, but zero
complete venue-history rows. Therefore the sports probability artifact has
0/15 sports coverage and 15/15 BK fallback.

An equal-bank preliminary comparison was run for drawing 4975 with 166 coupons
and RUB 4,980 in each branch. The BK-control and sports-shadow packages are
byte-identical (166/166 overlap) because sports coverage is zero. Their modeled
P(13+) is approximately `0.00084412`; modeled EV/ROI remain unvalidated model
diagnostics, not a profit forecast. Durable paper-only artifacts are under
`reports/research/package-comparison-4975/final/`.

Drawing 4974 is now complete 15/15 with actual row
`XX121122X1X2X12`. The retained 166-coupon, RUB-4,980 paper package failed:
best 6/15, mean 2.86, median 3, and zero coupons in categories 10-15. Every
actual sign existed somewhere in the package, but the joint combinations were
poor; the package's most frequent sign matched the actual sign in only 2/15
events. BK's top-ranked outcome itself occurred in only 5/15 events. This was
not a wager, so return and ROI are unavailable. The deterministic report is
`reports/rehearsal/evening-4974-recovery-20260813T1330Z/post-draw/paper-package-review-4974.md`.

Post-draw scheduling is now chained automatically only from a verified loaded
evening LaunchAgent. Manual/rehearsal schedulers remain candidate-only. The
installed post-draw job runs from 12:00 Moscow on the next day, retries on the
existing bounded cadence, and removes its exact LaunchAgent after a terminal
state. Drawing 4974 predates this activation behavior and was reconstructed
manually; future loaded evening runs use the automatic path.

Verification: `1876 passed, 13 deselected in 116.96s`; Ruff and
`git diff --check` passed. The drawing-4975 evening LaunchAgent remains loaded
with its first trigger at 15:00 Moscow and T-10 at 16:50 Moscow.

## Drawing 4975 morning recovery and retry activation fix (2026-08-14)

The installed morning LaunchAgent did run for drawing 4975, but preparation
stopped at `timing_unknown 5/15`: events 9, 11, 12, 13 and 15 had no usable
API-Sports kickoff. The persisted retry plan also ended at 12:00 Moscow even
though its hard stop was 16:00, and `morning-dispatch --activate` generated the
identity-bound retry plan without installing its LaunchAgent. Consequently no
automatic retry existed after the fixed 12:00 morning pass.

Both execution defects are fixed locally. Bootstrap/timing retries now add
hourly hard-stop-day attempts from 13:00 Moscow until, but never at or after,
the configured hard stop. A deferred `morning-dispatch --activate` now
generates and installs the exact passive retry LaunchAgent and reports its
verified status. The retry remains drawing/fingerprint/deadline bound and may
activate an evening scheduler only when the existing plan says
`activate_evening=true`.

For the current drawing, exact schedule evidence was reviewed from current
official and independent public sources and appended for Annecy-Rodez,
Dijon-Pau, Versailles-Le Puy, Villefranche-Paris 13, and QRM-Concarneau. The
real morning wrapper then reached READY 15/15 and activated schema-v6 evening
plan `c6a3a25a8459d0d2` for drawing 4975, deadline 17:00 Moscow, bank 4,980 and
stake 30. Its bound ledger content and semantic hashes revalidate. The loaded
LaunchAgent has future triggers at 15:00, 15:30, 16:00, 16:15, 16:30, 16:40,
16:44 and 16:50 Moscow. Scheduler readiness is not a profit claim; quality-v2
remains paper-only.

The automatic collector now removes the manual discovery step for independent
candidates. It does not remove the official-source requirement; previously
unseen events still remain fail-closed until authoritative evidence is
collected and reviewed.

Verification after the retry fixes: `1868 passed, 13 deselected`; Ruff and
`git diff --check` passed. The live read-only preflight status reports drawing
4975 READY 15/15, zero unresolved events, evening activation `activated`, and
package generation `enabled`.

## The Odds API current-drawing shadow probe completed (2026-08-13)

The provider-neutral transport, immutable raw captures, generic quota and
endpoint/request provenance, secure `.env` loader, and standalone
`collect-the-odds-api-shadow` command are implemented. JSON/CSV/Markdown
reports are hard-labelled `NOT_ACTIVATED`, non-actionable, and cannot feed the
scheduler or package selection.

The first live probe covered open drawing 4975. It spent 3 credits and left
497, matched 4/15 events, produced separate de-vigged 1xBet and Pinnacle rows
for those four events, and used explicit TotoBrief-BK fallback for the other
11 (`0 exact candidates`). Generated report/cache bytes contained zero API-key
occurrences. This 26.67% one-drawing identity/market coverage is diagnostic;
it is far below activation evidence and proves no forecasting or profit gain.

Full verification after the checkpoint implementation: 1866 tests passed, 13
were deselected, Ruff passed, both CLI help smokes passed, and
`git diff --check` passed.

An uninstalled prospective checkpoint command is now implemented for exactly
`morning`, `control`, and `t10`. Its immutable manifest binds the complete
target event/BK/pool rows, aliases, target fingerprint, quota reserve,
collection ID, report hashes, and `NOT_ACTIVATED` state. Repeating the same
checkpoint reuses it without constructing the provider or consuming credits;
input or evidence drift fails closed. A fresh zero-credit quota preflight
durably skips the whole checkpoint at the configured reserve. Provider-scoped
coverage audit is available with `--provider the-odds-api`, remains `PENDING`
at 1 drawing/15 events, cannot mix API-Sports collections, and deduplicates
morning/control/T-10 observations to the latest complete collection per
drawing.

## The Odds API provider transport implemented (2026-08-13)

The first implementation stage is complete locally. The new provider uses the
official zero-credit sports/events discovery endpoints, performs one paid EU
`h2h` request per matched sport key, preserves 1xBet and Pinnacle as distinct
bookmakers, reuses a bulk response for all same-league target events, and
tracks credit headers. Hockey two-way moneyline rows are rejected from the
regulation three-way consensus. The protected key is excluded from cache
bytes, request fingerprints, and sanitized errors. External collection loads
and audits can now be filtered by provider, and matcher version is explicitly
bound to `the-odds-api-v1` without changing the API-Sports default. Focused
verification passed 152 tests and Ruff.

## The Odds API implementation plan approved (2026-08-13)

The approved sports-analytics specification is now decomposed into a concrete
The Odds API shadow plan at
`docs/superpowers/plans/2026-08-13-the-odds-api-shadow-audit.md`. The first
delivery is a current-drawing, quota-aware, `NOT_ACTIVATED` market snapshot
that preserves separate 1xBet, Pinnacle, and EU-consensus views and cannot
affect the scheduler or a package. Implementation proceeds with local TDD and
no model-backed subagents.

## Absolute local-only model boundary enforced (2026-08-13)

TotoAI now permanently prohibits Claude, Anthropic APIs/SDKs/CLIs, Eliza,
external LLM proxies, external coding agents, and model-backed subagents. The
rule covers both direct calls and indirect routing through tools, skills,
plugins, MCP servers, connectors, wrappers, and model overrides. Repository
context may not be sent to an external LLM even for read-only work. A focused
policy regression protects the durable wording in `AGENTS.md` and
`memory-bank/TOOLING_POLICY.md`.

## Automatic post-draw review lifecycle completed (2026-08-13)

The scheduler creates a non-betting post-draw plan for every terminal outcome.
When and only when the parent evening LaunchAgent is verified loaded, the
exact bound post-draw LaunchAgent is installed automatically. Manual and
rehearsal parents remain uninstalled candidates. The first result check is
12:00 Europe/Moscow on the next Moscow calendar day after the drawing deadline;
incomplete drawings retry at three-hour intervals within the plan's bounded
attempt window.

The workflow reuses the existing authoritative result synchronization,
reviewed VOID handling, immutable package archive, and settlement algorithms.
It supports package-bound and package-free `NO BET` lifecycles, persists typed
pending/transport/integrity states, and creates a hash-bound
`review-request.json` after complete results. Review transitions are explicit:
`AWAITING_USER_REVIEW -> REVIEW_REQUESTED|REVIEW_SKIPPED -> REVIEW_COMPLETE`.

Post-draw preparation is advisory to the primary scheduler. Missing paper
state is normalized to a zero-cost package-free paper result when no validated
package exists; any post-draw generation failure is recorded separately and
cannot change the terminal scheduler status/marker or create a second
finalization failure. No wager is placed.

Verification after the fail-safe boundary repair passed `1830 passed, 13
deselected in 120.89s`; full Ruff and `git diff --check` passed.

## Exact durable PAPER package completed (2026-08-13)

Tasks 1-3 of the approved paper/post-draw plan are implemented. The scheduler
now has a strict renderer/validator for the exact BaltBet text-editor shape,
immutable scheduler-owned paper checkpoints, a hash-bound
`paper-package-result.json`, and `paper-package-show`. Payload bytes preserve
source coupon order and contain only `<stake>; <15 outcomes>` lines with final
LF. PAPER/NO BET warnings stay on stderr/status.

Computed terminal `NO BET` packages remain inspectable after T-10, while
package-free `NO BET` has no coupon payload. Actionable PLAY publication is
unchanged: paper artifacts are always `actionable=false`, cannot create
`.bet-ready`, and are rejected by `operator-export`. The historical 4974 paper
artifact is covered by a 166-unique-coupon / 4,980-cost safety regression; it
is not promoted or displayed as an operator package.

Verification after implementation: 52 focused tests and 247 relevant
scheduler/operator tests passed. Full verification passed
`1817 passed, 13 deselected in 113.58s`; full Ruff and `git diff --check`
passed.

## Next product focus: visible paper packages and sports analytics (2026-08-13)

The user approved two mandatory lifecycle changes. Every terminal calculation
must be shown, including a computed `NO BET` package clearly labelled
`PAPER / DO NOT WAGER`. At 12:00 Moscow time on the next calendar day, result
reconciliation must check for complete 15/15 terminal outcomes; incomplete
drawings retry every three hours. Once complete, the durable workflow asks the
user whether to review the package and records the answer before producing an
immutable postmortem.

The package presentation contract is exact: a clean text file with one coupon
per line in the form `30; 1; X; ...` (configured stake plus 15 outcomes).
Warnings and diagnostics are shown separately and never embedded in the
copyable package. The existing 4974 paper artifact validates as 166 unique
lines with implied cost 4,980, but remains expired/non-actionable evidence.

The next main research phase is sports-analytics probability improvement. BK
remains the production control. Existing API-Sports evidence and evaluated
free public fallbacks feed leakage-safe features; a regularized sports residual
model adjusts BK only in shadow mode. No sports model reaches package selection
until chronological event metrics, end-to-end package outcomes, prospective
coverage, and the predeclared activation gate all pass. Designs are recorded
in `docs/superpowers/specs/2026-08-13-paper-package-and-post-draw-review-design.md`
and `docs/superpowers/specs/2026-08-13-sports-analytics-probability-design.md`.

## Drawing 4974 evening run: warmup contract fix and terminal result (2026-08-13)

The 16:15 warmup failed closed because the child command correctly used the
T-45 `final_lead_minutes=45`, while strict runner-manifest validation still
expected the ordinary fallback value 30. A regression reproduced this exact
command/parser disagreement. Both paths now use one canonical
`_runner_final_lead_minutes()` function; the scheduler test suite passed 129
tests and Ruff passed.

The failed immutable plan was replaced through `scheduler-recover-plan`, which
preserved drawing 4974, bank 4,980, stake 30, probability configuration, and
all reviewed schedule-evidence bindings. The automatic 16:30 refresh completed,
the automatic 16:40 final completed at 16:46:59 MSK, and the 16:50 terminal
tick was a clean no-op. Final operator state is `NO BET`, `FINAL_FRESH`,
`actionable=false`, reason `quality_v2_real_money_release_gate_closed`. A
166-coupon paper package costing 4,980 was retained for audit, not authorized
for wagering.

## 2026-08-13: drawing 4974 timing evidence resolved

- The repeated `timing_unknown` retry defect was caused by the report refresh
  allowlist accepting `unresolved` and `totobrief_pool_not_ready`, but not the
  already generated `ACTION REQUIRED: timing unknown` report. The refresh is
  now idempotent for that status and a two-dispatch regression covers attempt
  count plus `Last seen` replacement.
- Drawing 4974 events 8 (`Ригас Футбола Скола — Яблонец`) and 15
  (`Абха — Аль Хазм`) were reviewed against two current HTTPS sources each,
  including one official and one independent source. Immutable source
  snapshots and hash-checked review records are stored under
  `data/schedule-evidence/`; the reusable ledger resolves both events exactly.
- Canonical kickoffs are event 8 at `2026-08-13T16:30:00Z` (19:30 MSK) and
  event 15 at `2026-08-13T16:15:00Z` (19:15 MSK). No guessed kickoff, fuzzy
  identity, or single-source fallback was accepted.
- The identity-bound morning dispatch for drawing id 12031 / visible 4974 was
  rerun through the secure `.env` prelude. It is now READY with 15/15 pins,
  zero unresolved events, and evening plan `3551ef6898d8f474` activated for a
  RUB 4,980 bank / RUB 30 stake. The plan binds ledger content SHA-256
  `af200ed9e83dff74036ee896deef74e90a945b96165e7c333011c436c1909490`
  and semantic hash
  `831aad0476f4d51e68c7ff1b7d6767e2fb836fe6df8a030f3631200ccc632d7e`.
- Current preflight status is `preparation_status=ready`, `mapped_count=15`,
  `pin_count=15`, `unresolved_count=0`, evening activation `activated` and
  package generation `enabled`. This is scheduler readiness only; it is not a
  profit claim or permission to wager. Quality-v2 remains paper-only unless a
  future scheduler publication itself passes the existing `PLAY` boundary.
- Verification: focused timing/evidence suite `28 passed`; full pytest
  `1798 passed, 13 deselected in 115.71s`; full Ruff and `git diff --check`
  passed.

## 2026-08-13: operator export boundary and missing-kickoff escalation

- The installed 12:00 morning run for drawing 4974 exposed one production
  shape omitted by the first timing regression: eligibility can be `unknown`
  while the 13 already timed events still yield a partial `span_days=1`.
  `MorningPreparedDrawing` now accepts that partial span only under the
  existing strict `timing_unknown`/baseline-only/unknown-eligibility
  invariants. The exact `span_days=1` regression passes. The failed 12:00 job
  made three attempts and installed no evening plan. No manual dispatch was
  run. A separate calendar job was moved from 13:00 to 12:30 MSK without a
  manual kickstart. Its first attempt correctly materialized
  `ACTION REQUIRED: timing unknown 2/15` for events 8 and 15, wrote the
  attention/review/retry artifacts, installed no evening plan, and returned
  deferred. The wrapper then made its two configured retries, which exposed a
  separate idempotency defect: rewriting `ACTION_REQUIRED.md` conflicted with
  the existing text artifact. That defect and the two missing kickoff records
  are resolved by the newer drawing-4974 state above.
- A scheduler-owned `bet-ready / PLAY` publication now creates a run-scoped
  `baltbet-upload.txt` and hash-bound actionable `operator-result.json` before
  writing `.bet-ready`. The public `operator-export --plan ... --output ...`
  command revalidates the schema-v6 plan, exact run/status/marker, source CSV,
  upload bytes, archive manifest, SQLite archive row, bank/stake/count/cost,
  and T-10 expiry before copying bytes. `NO BET`, LKG/research, expired,
  tampered, foreign, or unarchived files cannot be exported.
- `scheduler-execute` no longer labels an internal/audit package path as an
  operator package. At T-10 the operator upload is removed and
  `operator-result.json` becomes non-actionable while the audit archive and
  historical `.bet-ready` marker remain.
- A READY 15/15 preparation with baseline-only events that still lack kickoff
  times is no longer silently reported as generic `drawing_not_playable`.
  Missing kickoffs become explicit `timing_unknown` items, ACTION_REQUIRED
  attention, reviewed-schedule queue records, and exact-identity retries that
  stop before T-60. Such retries may request evening activation only if a
  later pass becomes fully playable.
- Drawing 4973 is frozen as failure evidence. The unbound 166-coupon file was
  created after T-10, had no scheduler/archive/settlement identity, scored at
  most 7/15, and is permanently non-actionable. The canonical quality-v2 paper
  candidate scored at most 8/15. Neither produced a 10+ result or any evidence
  of profitability.
- Release verification passed: `1797 passed, 13 deselected in 112.49s`; full
  Ruff passed. No push, PR, live scheduler change, network call, package
  recommendation, or wager was made.

## 2026-08-11: scheduler last-known-good remediation

The drawing-4972 failure mode is covered by local deterministic regressions.
Warmup and refresh may now persist an immutable validated candidate package
and a separate BaltBet upload-text operator artifact. The first final attempt
has a phase deadline before the retry trigger, and retry is bounded by the
actionable publication cutoff. Operator availability does not depend on retry:
a failed final/429/timeout keeps the warmup checkpoint intact and exposes one
operator result:
`FINAL_FRESH`, `LAST_KNOWN_GOOD_DEGRADED`, or `NO_BET`. Degraded packages carry
their actual staleness and absolute coupon path, remain `NO BET`, and never
create `.bet-ready` or place a wager.

Verification is local and in-process, not an exact launchd-overlap test. The
LKG/dynamic-bank/production-like CLI regressions passed `7 passed`; the focused
scheduler/runner CLI suite passed `209 passed`. No network, wager, commit,
push, or PR action was performed.

## Authoritative snapshot (2026-08-11)

- PR #4 (quality-v2) and PR #5 (systematic matcher) are merged. Commit
  `c3b273f` implemented the drawing-4971 postmortem; PR #6 is merged as
  `17a6bb4f`.
- Drawing 4967 had three 166-coupon packages. The best coupon reached only
  6/15; no category 9-15 was won.
- Drawing 4971 finished `X2111X111X121X2`. Old and safety-v1 packages reached
  only 7/15. Quality-v2 improved exposure structure and recoverable mean hit
  count, but its frozen artifact lacks coupon strings, so no predictive edge
  or profitability is proven.
- Drawing 4972 has a paper package of 166 coupons for RUB 4,980. It is
  `STRUCTURAL_PASS` but top-level `NO BET`; model-only unvalidated estimates
  are P13+ 0.2197%, P14+ 0.01985%, and P15 0.000807%.
- A schema-v6 scheduler snapshot exists for 4972. Its recorded
  loaded/runs=0/paper-only state is historical and does not prove current
  launchd state.
- Production outcome probabilities remain exclusively normalized TotoBrief BK.
  Pool is crowd/EV input. The sports probability provider, machine-readable
  artifact, chronological evaluator, and CLI are implemented, but are strictly
  shadow-only `NOT_ACTIVATED`; they cannot change EV, coupon ranking, packages,
  scheduler decisions, or betting state. Injuries, lineups, xG, and Elo remain
  absent.
- Quality-v2 is fail-closed `NO BET / TRAINING-PAPER`; it cannot create an
  actionable wager-ready artifact.
- Next: collect prospective immutable pre-match sports snapshots and evaluate
  BK, sports-shadow, and the candidate blend chronologically on at least 30
  drawings / 450 events. Activation remains prohibited unless strict log-loss
  and Brier improvements, calibration tolerance, coverage, fingerprint, and
  leakage gates all pass and a separate reviewed architecture change follows.
- Reviewed fail-closed semantics bind OOS BK rows to the hash-bound frozen
  authoritative drawing snapshot captured no later than `as_of`; mutable
  current `Quote` rows are excluded. Missing/late authority, fingerprint or
  integrity drift, future sources, and absent/mismatched orientation block the
  gate. Ordinary missing sports history remains a BK coverage fallback. The
  30-drawing / 450-event / 70%-coverage minima and 0.02 maximum calibration
  tolerance cannot be weakened by CLI/config.

## Implemented: shadow sports probability provider (2026-08-11)

- `sports-probability-shadow` emits a content-bound JSON artifact containing
  BK, sports-shadow, candidate-blend probabilities, feature values,
  provenance, fallback reasons, and status `NOT_ACTIVATED`.
- Sports-shadow is an explicitly untrained, experimental, Jeffreys-smoothed
  venue-only W-D-L projection. It uses only the home team's home record and the
  away team's away record. Missing venue history causes explicit BK fallback;
  aggregate W-D-L is diagnostic only and is never substituted or counted as
  venue-model coverage. The candidate blend weight uses only matched venue
  observations versus the requested-history prior; no trained coefficients
  are claimed or invented.
- Exact snapshot hash/as-of/deadline, target fingerprint, event identity,
  provider orientation, fixture/team pins, source chronology, and pre-match
  boundaries are validated. Any event that cannot prove them uses normalized
  BK unchanged.
- `evaluate-sports-probability-shadow` performs chronological OOS comparison
  of BK, sports-shadow, and candidate blend using multiclass log loss, Brier,
  confidence ECE, counts, sports coverage, fallback, and validation failures.
- The activation gate is fail-closed and cannot activate production. It needs
  at least 30 drawings / 450 events, at least 70% sports coverage, strict blend
  improvement over BK in log loss and Brier, calibration within tolerance,
  and zero validation/fingerprint/leakage failures. A pass is only
  `PASS_REVIEW_REQUIRED`; top-level status remains `NOT_ACTIVATED`.
- Verification outputs for the current local diff are recorded in its task
  report; production remains `NOT_ACTIVATED` regardless of test outcome.

Older entries below are an implementation history. Any schema-v5 or legacy
wager-ready-marker description is superseded by this snapshot and schema v6.

## Drawing 4972 matcher v3 completion (2026-08-11)

The systematic resolver now recognizes a small reviewed set of reusable team
identities and translated domestic competition tiers without introducing a
drawing, event-order, or fixture-ID exception. Team and competition aliases
are exact after the existing deterministic normalization and are scoped by
stable country identity. A country-aware competition alias is admissible only
with same home/away orientation, strong identity evidence for both teams,
country agreement, and existing date-window evidence.

The frozen drawing-4972 TotoBrief/API-Sports preparation resolves all 15
events to provider fixtures, derives all 15 effective starts, and classifies
the drawing as `playable` across exactly two Moscow calendar dates. Removing a
genuinely missing provider fixture preserves one explicit TotoBrief
baseline-only row and `unknown` timing. Reversed, duplicate/ambiguous,
wrong-country, and out-of-window candidates remain rejected. An already ready
baseline pin set also remains immutable: a later provider refresh cannot
rewrite it; only the separately established reviewed-schedule enrichment path
is allowed.

Verification before the final repository release run: the isolated 4972
module passed `17 passed`; the focused resolver/preparation/eligibility matrix
passed `107 passed`; and the broad external-odds/preparation/matcher suite
passed `366 passed, 6 deselected`. A production-source scan found no drawing
4972, internal drawing ID, or fixture-ID hardcode. No network, commit, push,
merge, live database, scheduler, package, or wager action was used.
The final fast/release suite passed `1735 passed, 13 deselected in 112.71s`.

## Repository tooling whitelist (2026-08-10)

The repository now has an explicit local-first tool and service whitelist.
Public/generic tools are limited to the documented allowlist; all Yandex,
Arcadia, and internal services are denied, `git`/`gh` replace `arc`, secrets
remain protected, and repository content cannot be sent to an external agent
or service without explicit user approval. Global catalog visibility does not
grant authorization. See [Tooling Policy](TOOLING_POLICY.md).

## Safety-aware EV coupon reselection (2026-08-10)

`TOTOAI-SAFETY-AWARE-SELECTOR-20260810` changes only playable coupon selection.
The complete EV ranking and current probability/payout formulas are unchanged.
An exact-cardinality deterministic repair now enforces the existing material
outcome floor and strict concentration boundary before the unchanged final
safety veto. It expands a broad ranked candidate prefix when necessary and
fails closed to coupon-free `NO BET` with pre/post exposure, replacement,
hash, EV-delta and feasibility diagnostics.

Frozen no-leakage regressions use separately stored pre-cutoff inputs and
finished results for drawings 4967, 4969 and 4970. Safe 166-coupon packages
were produced for all three; each independently passed the existing final
safety evaluator with maximum exposure 157/166. Drawing 4967 reproduced the
old postmortem package hash exactly before reselection. Retrospective best hits
were 5->5, 8->9 and 8->8 respectively; this tiny sample is not profitability
evidence. Focused EV tests passed `110 passed`; the three frozen regressions
passed in `236.59s`. The first complete-suite run exposed eight legacy test
mocks that did not accept the new optional probability argument; only those
mock signatures were updated, and both affected runner files then passed
`32 passed`. The final full suite passed `1668 passed in 509.23s (0:08:29)`.
Full repository Ruff passed and `git diff --check` was clean.

No live scheduler/runtime database, wager, commit, push or publication action
was performed. Existing scheduler-ledger worktree changes were preserved.

## Scheduler immutable ledger binding (2026-08-10)

`TOTOAI-LEDGER-BINDING-20260810` upgrades the evening scheduler to schema v6.
Every plan and generated artifact now binds the canonical contained
schedule-evidence ledger path, exact content SHA-256 and semantic hash into
the plan identity. Schema-v5 plans are rejected clearly because they lack this
binding; older inspection schemas remain non-actionable and production
execution stays fail-closed.

All scheduler stages revalidate the same bound ledger before phase work.
`prepare-drawing` and `run-drawing` receive the exact plan path and both hashes,
validate before provider/package work, and final prospective collection
revalidates before every pass. Missing, malformed or changed ledgers and
schedule-evidence pin identity conflicts are typed terminal integrity failures
using child exit code 78; transport/TLS/quota/refresh failures remain
retryable. Drawing-4967 regressions preserve the atomic four-pin monotonic
upgrade, reversed schedule-only orientation and original BK `1/X/2` order.

No live scheduler, runtime database, package, wager, network, commit, push or
PR operation was performed.

Verification covered 60 scheduler operational/atomic/preflight tests, four
drawing-4967 and exact-command regressions, and the two final synchronized
cache fixture corrections. The full suite checkpoint reached `1654 passed`
with two fixture-only failures caused by the new pre-provider ledger check;
both fixtures were supplied a valid local ledger and their targeted rerun
passed `2 passed`. Per the operator's checkpoint instruction, the complete
suite was not started again. Repository Ruff passed and `git diff --check` was
clean after the final corrections.

## Scheduler canonical-ledger forwarding (2026-08-06)

`URGENT-4967-PINSET` closes the scheduler preparation-entrypoint gap.
Every schema-v5 preparation command now passes the canonical contained
`data/schedule-evidence/ledger.json` beneath its validated project root.
The real `prepare-drawing` CLI resolves that option beneath its current
project directory and forwards the resolved path to `prepare_drawing()`.

No scheduler plan schema or identity changes. Strict provider pins, reviewed
hash binding, reversed schedule-only semantics, BK ordering, atomic upgrades,
and contradictory-identity fail-closed behavior remain unchanged.

Regression verification covered the scheduler argv and real CLI forwarding;
the focused preparation/safety set passed `32 passed in 5.38s`. The first full
run exposed two temporary-project fixtures without the newly required canonical
ledger; adding empty schema-v1 ledgers to those fixtures preserved production
behavior and the final full run passed `1648 passed in 274.96s (0:04:34)`.
Full Ruff passed and `git diff --check` was clean.

The live non-betting check started at `2026-08-06T17:54:21+03:00` against
drawing 4967 with the production database, raw/provider caches and canonical
ledger. `prepare-drawing` returned `ready`, `15/15`, `playable`, with 15 external
pins and no baseline-only or unresolved orders. The plan deadline was 18:00 MSK
and its publication cutoff was already 17:50 MSK, so package generation was not
invoked: `NO BET`, no PLAY/TXT, upload, launchd change or bet.

## Drawing 4967 monotonic canonical pin upgrade (2026-08-06)

`local-totoai-4967-pin-upgrade-fix` closes the production rejection of an
existing ready pin-set containing 11 strict provider pins and four
`totobrief-baseline` rows. A later preparation may now atomically replace only
those baseline rows with validated reviewed/schedule-evidence rows while
preserving every existing strict pin byte-for-byte.

The transition requires the same drawing fingerprint, drawing number, all 15
target event IDs/orders and canonical target team orientation. A reversed
schedule-only observation keeps the TotoBrief target orientation, carries no
provider fixture/team identity and does not alter the `1/X/2` probability
order. Selected reviewed rows must all bind to the exact supplied ledger or
catalog hash. Downgrades, ambiguous evidence, kickoff conflicts, fixture/team
identity drift and unrelated hash changes fail closed without replacing the
persisted pin-set.

Verification: focused preparation/registry suite `30 passed`; full suite
`1648 passed in 277.95s`. No network, live activation, scheduler mutation,
package, bet, Git or publication action was performed.

## TotoBrief TLS resilience and new drawing preflight (2026-08-05)

- TotoBrief failures now retain redacted original transport diagnostics,
  structural exception chains, categories, status codes, safe endpoints, and
  real attempt counts without headers or credentials.
- TLS certificate verification remains mandatory for default and injected
  sessions; no request path uses `verify=False`.
- Scheduler schema-v5 plans now include T−120 TLS, T−90 API, and T−60
  freshness diagnostics before the existing T−45/T−30/T−20/T−16/T−10 stages.
  Each stage is persistent, deduplicated, and rate-limit coordinated.
- Every failed stage persists and logs its safe structured failure detail.
- Diagnostic success and stale cache never authorize a coupon. Final PLAY still
  requires one fresh verified-network TotoBrief detail snapshot; otherwise the
  scheduler reaches coupon-free `NO BET`.

## Canonical ledger morning-dispatch integration (2026-08-04)

`local-totoai-ledger-morning-dispatch-fix` closes the production gap exposed by
drawing 4966. `morning-dispatch` now resolves the canonical
`data/schedule-evidence/ledger.json` beneath `project_root` by default, accepts
an explicit contained `--schedule-evidence-ledger` override, and carries that
exact path into passive retry commands. The obsolete
`--reviewed-schedule-catalog` remains a separate schema and is not used as a
ledger substitute.

Preparation no longer short-circuits when an existing ready pin set contains
`totobrief-baseline` rows and newly available exact ledger evidence can supply
their kickoffs. Such rows may be replaced atomically only by strict
`reviewed-schedule`/`schedule-evidence` rows for the same target event/order;
all other canonical pin changes remain fail-closed. Invalid schema/hash,
ambiguous/conflicting evidence and paths outside the project root remain
rejected.

Verification: RED reproduced both the stale baseline-only reuse and missing
CLI override; focused integration/regression suite `93 passed`; full suite
`1621 passed in 259.46s`; repository Ruff and final diff check passed after
this documentation update. No live rehearsal, scheduler activation, package,
wager, Git publication or network operation was performed.

## Morning dispatch idempotency fix (2026-08-04)

Repeated production morning-dispatch retries now reuse the persisted exact-drawing state instead of conflicting with an earlier notification; three retries completed at 13/15 without a notify conflict. Verification: 12 focused tests passed, with Ruff and diff checks green.

## Evening stale-detail refresh fix (2026-08-03)

The drawing-4964 warmup and refresh ticks exposed that the scheduler invoked
`prepare-drawing` against the local operational detail cache without first
requesting a TotoBrief refresh. Both ticks therefore failed on the unchanged
60-second freshness limit. Scheduler preflight commands now explicitly use
`--refresh-totobrief`: a stale cache is re-fetched before freshness is
enforced, while refresh transport failure remains retryable and refreshed
target identity/deadline drift remains fail-closed. Atomic final execution
continues to capture its own immutable fresh TotoBrief detail and retains the
existing fingerprint checks. No freshness limit, package rule, or validation
was weakened. Focused verification: 21 scheduler operational tests passed;
Ruff and `git diff --check` passed. No package, wager, commit, push, or
LaunchAgent mutation was performed by this change.

## Scheduler LaunchAgent schema-v5 label fix (2026-08-03)

`TOTO-4964-SCHEDULER-LABEL-FIX` closes the production activation failure found
after drawing 4964 reached READY 15/15. Scheduler artifact generation emitted
`com.totoai.production-scheduler.v5.<plan_id>`, while morning activation and
installation still expected the obsolete unversioned label.

One canonical `scheduler_launch_agent_label()` function now derives the exact
label from a fully validated schema-v5 `SchedulerPlan`. Generation, morning
dispatch/reuse, installer validation, launchctl invocation records, preflight
status, and CLI output use that same value. Installation verifies the adjacent
plan and exact artifact set before any LaunchAgent mutation. Legacy schema v4,
tampered plan IDs, drawing/deadline drift, arbitrary labels, and conflicting
persisted labels fail closed.

The drawing-4964 regression is self-contained and reproduces production plan
identity `9e4df82511c1e52a` without reading ignored rehearsal artifacts.
Verification: focused scheduler suite `192 passed`; full suite `1584 passed`;
repository Ruff and `git diff --check` passed before final documentation
update. No LaunchAgent was installed, no production database was mutated, and
no package or wager was generated by this fix.

## Nightly captured-selection drift fix (2026-08-02)

`TOTO-NIGHTLY-CAPTURED-SELECTION-DRIFT-V1` fixes the failed scheduled run
`20260802T002643498108Z-7927-4f7b04`. The run captured eight eligible drawings
at `00:26:43Z`, but a second dry-run used a later wall clock after cooldowns
expired and incorrectly classified the changed eligibility view as
`captured_selection_drift`, performing zero network work.

One nightly run now captures a single timezone-aware eligibility reference
instant after acquiring the maintenance lock. Initial selection,
reconfirmation, and per-drawing reconciliation eligibility/cooldown checks all
use that same instant. The selected candidate tuple is immutable, and its
local drawing/event/result identity is hashed before and after the optional
pre-apply boundary. Wall-clock cooldown expiry alone no longer changes the
captured run, while drawing status and result fingerprint mutations still fail
closed before backup or network access.

Deterministic regression coverage advances the clock across a cooldown expiry
and proves only the originally captured drawing is processed. Negative controls
prove real drawing-status and same-cardinality result changes still produce
`captured_selection_drift` with zero network attempts and no backup.

## Scheduler schema v5 and T−10 contract (2026-07-31)

`TOTO-SCHEDULER-SCHEMA-V5-TMINUS10` completes the earlier timezone/T−10 WIP
without installing automation or touching the main database:

- `morning-dispatch --expected-deadline` accepts timezone-aware ISO-8601
  values with `Z` or explicit offsets and normalizes the exact instant to UTC;
- naive and malformed deadline values fail closed before dispatch;
- identity comparison remains exact after UTC normalization;
- the evening publication deadline is uniformly T−10, represented by
  `t_minus_10` in plans/status and by an 18:50 Moscow launchd trigger for a
  19:00 Moscow drawing deadline;
- generated launchd calendar fields are rendered explicitly in
  `Europe/Moscow`, independent of the caller's local timezone;
- every new plan and status is schema v5; the LaunchAgent label is versioned
  v5;
- the plan ID binds schema v5, `publication_lead_minutes = 10`, and the exact
  `45/30/20/16/10` trigger vector, so idempotent reuse cannot confuse T−12 and
  T−10 artifacts;
- schema-v4/T−12 plans fail closed with an explicit `regenerate schema v5`
  diagnostic before execution or artifact reuse; they are never silently
  migrated;
- automatic betting remains absent and the passive retry hard stop remains
  T−60.

Drawing 4961 regression identity is `2026-07-31T16:00:00Z`; equivalent
`+00:00` and `+03:00` representations resolve to that same UTC instant.
Verification: the expanded relevant scheduler/CLI/operational set is
`183 passed`; repository-wide Ruff and `git diff --check` pass. No main
database, launchd, package, or bet path was exercised.

## Drawing-4961 preflight retry remediation (2026-07-31)

The non-deployed passive retry slice is complete and has a stable
`preflight-retry-rehearsal` CLI. The rehearsal creates an online SQLite backup
copy, copies the strict reviewed evidence into an isolated project root, and
uses only isolated runtime/LaunchAgent roots. It never installs production
launchd state, mutates the main database, or emits package/bet artifacts.

The final drawing-4961 rehearsal proved:

- initial systematic preparation: ACTION REQUIRED 13/15 and zero pins;
- checked-in reviewed evidence: READY 15/15 and exactly 15 mixed-source pins;
- due retry, idempotency, READY cleanup, hard-stop cleanup, drawing drift and
  fingerprint drift: PASS;
- real generated-wrapper missing-key failure: exit 78 before dispatch;
- bounded API-Sports transport failure: two attempts and sanitized failure;
- evening output remained generation-only;
- no package, coupon, `.bet-ready`, or `.no-bet` artifact;
- main DB SHA-256 remained
  `9ca6e7404d6259e2856c0eed505eb936f2329b6bf0d2520a1f9df4ba839d2860`;
- production retry plist is absent and the exact launchd label is not loaded.

Final evidence is under
`reports/rehearsal/TOTO-4961-RETRY-E2E-FINAL-20260731/`. Focused verification
is `24 passed`; repository Ruff and `git diff --check` pass. Production
activation remains explicitly unauthorized.

## Passive nightly reconciliation v1 (2026-07-30)

`TOTO-NIGHTLY-RECONCILIATION-V1` is implemented, installed, and enabled as the
user LaunchAgent `com.totoai.nightly-reconciliation.v1`.

- CLI: `nightly-reconciliation-run` and
  `nightly-reconciliation-plan`;
- installed schedule: daily 03:20 machine-local time, currently Moscow time;
- scope: latest 30 finished drawings, maximum eight eligible attempts;
- exact two-pass read-only selection with fail-closed drift detection;
- shared morning/nightly global maintenance lock with stale metadata recovery;
- mode-`0600` online SQLite backup and manifest before apply;
- retention of seven known-good backups, never deleting the only/newest good
  copy;
- Data Health before/after and SQLite quick/FK checks;
- timestamped report/state/JSONL log;
- `SUCCESS`, `PARTIAL`, `DEFERRED`, and `FAILED` classifications;
- no package generation, betting scheduler activation, upload, or bet path.

The installed plist is
`/Users/turshevr/Library/LaunchAgents/com.totoai.nightly-reconciliation.v1.plist`
with mode `0600` and SHA-256
`4a7302736e75e3eb3820acddb51223388ea3a5f518a9ac40d84225cb12907003`.
It is loaded in `gui/501`, has `RunAtLoad=false`, and points to the generated
repository-local wrapper. Runtime state, logs, backups, RAW and the installed
home plist remain outside Git.

The explicit smoke run completed as controlled `PARTIAL`:

- captured finished drawings 4930 through 4937;
- eight requests, zero retries, timeouts, TLS or transport errors;
- seven drawings restored to 15/15;
- drawing 4931 remained 14/15 and entered cooldown;
- selected-scope Data Health improved from zero to six healthy drawings;
- SQLite `quick_check=ok`, zero foreign-key violations;
- no package, marker, upload, scheduler activation, or bet artifact.

Launchd currently reports the job loaded and not running, with one completed
run and `last exit code = 2`; exit 2 is the CLI contract for the recorded
`PARTIAL` source-incomplete outcome, not a process crash. The next scheduled
calendar trigger is daily at 03:20 local time.

Runtime limitations:

- only the latest 30 finished drawings are considered per run;
- no more than eight eligible network attempts are made;
- stable incomplete source payloads remain incomplete and are cooled down or
  quarantined rather than synthesized;
- the job repairs result/history evidence only and cannot generate packages or
  place bets;
- the installed schedule assumes the host timezone remains Europe/Moscow;
- unrestricted full-history backfill remains forbidden.

Publication verification for the combined wave2/wave3/nightly change set:

- focused lifecycle/reconciliation/morning suite: 104 passed;
- full pytest: 1536 passed in 244.28 seconds;
- repository Ruff and `git diff --check`: passed;
- installed plist and generated candidate SHA-256 match;
- launchd status: loaded, not running, one completed `PARTIAL` smoke,
  `last exit code = 2`.

## Offline repair classification idempotency v1 (2026-07-30)

`TOTO-OFFLINE-REPAIR-CLASSIFICATION-IDEMPOTENCY-V1` fixes the wave-2 defect
where a second canonical repair with `logical_changes=0` changed snapshot
classification from local importer recovery to network
`source_incomplete`.

Offline repair now uses stable classifications:

- `offline_repair_recoverable` in read-only preview when changes are pending;
- `offline_repair_recovered` after a proven local recovery;
- `offline_repair_no_changes` when local RAW supplies no new data.

No-change reapplication preserves classification and performs no SQLite,
reconciliation-state, timestamp, attempt, RAW, or archive mutation. Network
cooldown state remains keyed and isolated by its existing
drawing/provider/source identity.

The one-time historical normalization from an erroneous `source_incomplete`
fails closed unless exact RAW provenance and a hash-verified complete result
snapshot prove the current terminal facts. This specifically protects a
separately reviewed VOID from an older canonical payload that contains an
empty result.

A network-free replay used a SQLite backup copy of the current drawing-4954
state:

- before: `source_incomplete`;
- correction: `offline_repair_recovered`, `logical_changes=1`;
- second apply: `offline_repair_recovered`, `logical_changes=0`;
- second-run SQLite SHA and logical state were identical to post-correction;
- RAW/archive hashes, network reconciliation rows, and VOID facts were
  unchanged;
- primary `data/toto.db` SHA remained
  `a98eeeb8ec2a7c8121589edace4c7a72c144893f330175277cf205bae995650e`.

The full wave-2 idempotency protocol and bounded wave 3 subsequently passed,
so this bugfix is now part of the installed nightly reconciliation boundary.

## Canary and controlled production backfill v1 (2026-07-30)

`TOTO-CANARY-AND-CONTROLLED-BACKFILL-V1` completed the first bounded
end-to-end use of the lifecycle reconciliation path.

The network canary ran only on a copied database for drawings
4946/4955/4956/4958. It restored 4955 and 4956 identity/quotes plus
RAW-linked result snapshots, restored all 15 results for 4958, and proved that
4946 remains genuinely source-incomplete at 14/15. Data Health for the
4946–4958 interval improved from zero to three fully healthy drawings.

After the canary exposed repeated fetching of unchanged 14/15 source data,
durable cooldown/quarantine was implemented. A subsequent attempted
production dry-run exposed an empty-schema mutation at CLI startup; that run
was stopped before network access. The dry-run boundary was then corrected to
physical SQLite read-only mode and verified against a fresh backup.

The controlled production rerun used:

- an online SQLite backup with mode `0600`, `quick_check=ok`, and zero
  foreign-key violations;
- strict allowlist `4946, 4955, 4956, 4958`;
- a physically and logically immutable dry-run;
- exactly four TotoBrief detail requests on first apply;
- a second non-force apply with zero requests and zero database/RAW changes.

Production runtime outcome:

- 4946: remains 14/15, no synthetic VOID, persisted cooldown;
- 4955/4956: restored 15 names/championships, 15 quote rows, RAW evidence, and
  complete linked result snapshots;
- 4958: restored 15 terminal results/scores/statuses and a linked snapshot;
- no drawing outside the allowlist changed;
- scheduler, packages, settlements, markers, uploads, and betting were not
  touched;
- final SQLite integrity and foreign-key checks passed.

For drawings 4946–4958, healthy historical-inventory and settlement drawings
improved `0 -> 3`, probability-backtest eligibility improved `3 -> 6`,
prospective-generation eligibility improved `10 -> 12`, and missing terminal
results fell `92 -> 77`.

Controlled wave 2 and its idempotency rerun then completed. Wave 2 restored
4940, 4951 and 4952 to 15/15; 4945, 4949, 4950 and 4957 remained 14/15 and
entered cooldown; 4954 identity/quotes were recovered locally while its
reviewed VOID remained intact. The first repeated local repair exposed the
classification defect documented above; after the fix, replay changed only
the erroneous classification once and the second apply was a byte/logical
no-op.

Controlled wave 3 used allowlist
`4939,4499,3643,3351,3341,3292,2763,2762`. Drawing 4939 was restored to
15/15. TotoBrief still returned 0/15 for the other seven, so they were
preserved as source-incomplete with cooldown and no invented result or VOID.
The repeat apply made zero HTTP requests and no changes. This acceptance
authorized the bounded latest-30/eight-attempt nightly job, not unrestricted
backfill of all 2,199 drawings.

The production SQLite database, backups, append-only RAW payloads, and
reconciliation runtime state intentionally remain local and ignored by Git.
Published repository artifacts contain code, tests, summaries, hashes, and
audit evidence only.

Sports statistics remain `AUDIT ONLY`: the implementation can persist
provider-neutral, as-of feature evidence, but current data coverage is
insufficient and no OOS-tested model is permitted to influence probabilities
or coupons.

Next:

1. observe the first scheduled 03:20 run and review its report/integrity delta;
2. continue small backed-up historical waves for gaps outside the latest-30
   nightly scope;
3. close package settlement and mandatory post-draw reporting;
4. evaluate a lawful free sports-data source and run chronological OOS tests
   before any probability blend.

## Reconciliation dry-run physical read-only fix v1 (2026-07-30)

`TOTO-RECONCILE-DRY-RUN-READONLY-FIX-V1` closes the controlled-backfill
incident where CLI startup called `init_db()` and created an empty
`drawing_reconciliation_states` table before a dry-run.

- `reconcile-finished --dry-run` and `repair-canonical-raw --dry-run` now open
  SQLite with `mode=ro`;
- dry-run never calls `create_all`, migrations, or schema setup;
- a missing reconciliation-state table is interpreted as no persisted state;
- canonical RAW repair previews importer changes without creating RAW archive
  files or result snapshots;
- explicit apply mode still performs idempotent schema setup before mutation.

Regression coverage uses real temporary SQLite files with both missing and
existing reconciliation-state tables. It compares physical SHA-256,
`sqlite_master`, every table row count, and WAL/SHM state before and after.
A network-free smoke on a fresh copy of
`toto-before-controlled-backfill-20260730T092227Z.db` preserved SHA-256
`a117f28fe1d9e61f862191f179f3fcb8b05421e65b808fe9027ead71459ccc94`,
all 76 schema objects, all 19 table counts, and absent WAL/SHM. Reconciliation
selected 4946 without network or files; canonical repair previewed 171 changes
for 4954 without creating an archive. The production database was not used.
Focused verification passed 33 tests; the final full suite passed 1518 tests
in 248.00 seconds. Ruff and `git diff --check` passed.

The controlled production backfill was subsequently repeated from a fresh
backup and passed under the strict allowlist protocol documented above.

## Reconciliation cooldown/quarantine v1 (2026-07-30)

`TOTO-RECONCILE-SOURCE-INCOMPLETE-COOLDOWN-V1` closes the canary defect where
drawing 4946 (stable 14/15) was fetched and archived on every reconcile run.

- additive `drawing_reconciliation_states` persists state per
  drawing/provider/source;
- unchanged source-incomplete payload fingerprints receive bounded
  exponential cooldown and, after five observations, a 30-day expiring
  quarantine;
- transport, HTTP 429, and HTTP 5xx errors use a separate short retry policy;
- changed fingerprints and improved terminal counts reset stagnation;
- `--force` is explicit and off by default;
- dry-run performs no network, RAW, JSON-state, or SQLite-state mutation;
- blocked drawings do not consume `--batch-size`, preventing range starvation;
- complete 15/15 observations mark state complete and remain network-skipped;
- Data Health contract/report schema now exposes reconciliation inventory and
  per-drawing state.

The task was implemented and verified without network access or mutation of
`data/toto.db`. The network-free 4946 replay on a SQLite backup used the exact
saved canary payload hash
`c44c81ad8f19812c4a7a1caf95a1809ac3fd544e46653fd14f832c42f082fbff`.
Five eligible identical 14/15 observations produced cooldowns of 6/12/24/48
hours and then quarantine through `2026-09-02T06:00:00+00:00`. A cooldown
tick, quarantine tick, and dry-run each made zero fake-source calls and wrote
zero RAW rows. Copy `quick_check` passed with zero foreign-key violations.
Replay artifacts are under
`reports/rehearsal/reconciliation-cooldown-4946-v1-20260730T120000Z/`.
Acceptance verification: 86 focused lifecycle/reconciliation/data-health
tests passed; full suite is 1514 passed in 267.40 seconds; Ruff and the
network-free whitespace/diff-equivalent check passed. The primary database
SHA-256 remained
`5242945ace687adc59f2a6472bcf3c836075dbc88f47496a45756de6fe4f41fb`.

## Collector lifecycle freshness v1 (2026-07-30)

Implemented on the current feature branch:

- finished freshness requires terminal 15/15 plus a complete result snapshot
  linked to immutable RAW;
- active cache cannot satisfy a finished lifecycle;
- content-addressed RAW-first archive with capture/source/status/hash metadata;
- one non-destructive full-detail importer for identity, names,
  championship/sport, pool/BK/pin/norm quotes, results, scores, and result
  status;
- explicit VOID evidence, terminal conflict rejection, and zero-pool
  protection;
- bounded range/recent reconciliation with dry-run, retry/backoff, pacing,
  batch limit, resume state, and explicit outcomes;
- evidence-only canonical RAW repair command;
- additive SQLite `drawing_raw_snapshots`, Event `result_status`, and result
  snapshot `raw_snapshot_sha256`.

Network-free copy-database drill:

- range 4940–4959 selected 20/20 for reconciliation because legacy snapshots
  are not RAW-linked;
- canonical RAW dry-run: 4954 has 171 provable importer-loss changes; 4955 and
  4956 have no valid canonical local evidence;
- copy-only apply restored 4954 to 15 names and 15 quote rows; terminal result
  evidence remains 14/15, so no result snapshot was invented;
- second 4954 import produced zero logical changes;
- SQLite quick-check passed.

Focused lifecycle/data-health/finished suite: 71 passed. Final full suite:
1499 passed in 246.95s. Repository Ruff and `git diff --check` passed.

Operational observation: the already-installed passive morning dispatcher ran
at 10:30 Moscow while this working tree was under development and synchronized
active drawing 4960, creating three RAW observations in the main database.
This task did not install or activate that job, but future schema development
must account for already-loaded automation before claiming the production DB
was untouched.

Sports statistics remain AUDIT ONLY. Collection contracts, immutable feature
snapshots, as-of filtering, form/home-away/rest/standings fields, and
`collect-sports-stats` exist, but current free API-Sports access does not
provide the required 2026 history. No complete event snapshot corpus, trained
model, OOS improvement, probability blend, package influence, or scheduler
integration exists. The next sports-stat step is a lawful free source canary
under the existing provider-neutral contract, after lifecycle data canary
backfill is stable.

The canary and first bounded primary-database repair are now complete. The
remaining lifecycle work is another controlled allowlist wave, eventual
nightly reconciliation, and package settlement/post-draw reporting.

## 2026-07-29: Full-history forensic audit invalidated the completeness claim

Task `TOTO-FULL-HISTORY-DATA-AUDIT` audited every locally stored
`baltbet-main` drawing in read-only mode. The database passes SQLite
`quick_check` and contains 2,199 drawings from visible number 2759 through
4959, with 32,985 events and exactly 15 ordered event rows per stored drawing.
Visible numbers 3843 and 3844 are absent.

Structural row coverage is not historical data completeness. Of 2,197
finished drawings, 369 have incomplete results and 754 event outcomes are
missing. Nineteen finished drawings have no result signs at all. In addition,
215 drawings contain 15 unusable `0/0/0` pool triples, three drawings have
blank event names and no quote rows, immutable result snapshots exist for only
four drawings, locally discoverable RAW/detail evidence exists for only 15
drawings, and no package settlement exists.

The retained `reports/validation_4938.md` proves only that drawing 4938 matched
one supplied RAW payload. The former 2,179-drawing/32,685-event count proved
only `2,179 × 15` event-row structure. It did not prove complete results,
usable pool data, RAW retention, snapshots, or settlements. The previous broad
claim that the full API history and all fields had been validated was
incorrect.

Confirmed local causes are: collector freshness does not require results after
a drawing becomes finished; the finished-result importer updates outcomes but
does not restore names or quotes; zero pool triples passed the old non-null
audit; most historical RAW evidence was never retained; and the package
lifecycle has no completed settlement evidence.

Authoritative audit artifacts and the staged remediation plan are under
`plans/TOTO-FULL-HISTORY-DATA-AUDIT/`. The only next implementation task is
`TOTO-DATA-HEALTH-CONTRACT-V1`: a versioned read-only health contract and CLI.
Until its eligibility gates exist, the full local history must not be treated
as one trusted backtest corpus, and optimizer work is paused.

## 2026-07-29: Drawing coverage audit 4940–4959

Read-only audit task `TOTO-DRAWING-COVERAGE-AUDIT-4940-4959` verified the
current `data/toto.db` (`PRAGMA quick_check = ok`). All visible drawing numbers
4940–4959 are present exactly once and each has 15 ordered events, so drawing
headers are not being lost in this interval.

Historical content is incomplete: eight finished drawings have no result
signs, drawing 4946 has one missing result, drawings 4954–4956 have blank event
names and no quote rows, and immutable result snapshots exist only for
4953–4956. No package settlement exists for any drawing in the interval.
Drawing 4954 event 15 is correctly stored as explicit `VOID`.

The main database still records 4959 as unresolved; its successful
mixed-provider 15/15 drill was intentionally performed on a copied database.
The archived two-coupon/60 RUB 4959 package is a rehearsal artifact and must
not be treated as a placed bet or production outcome.

Reproducible audit and project-status reports:

- `plans/TOTO-DRAWING-COVERAGE-AUDIT-4940-4959/context.md`;
- `plans/TOTO-DRAWING-COVERAGE-AUDIT-4940-4959/status.md`.

Next P0 action: restore result/quote/name completeness, add an explicit
data-health gate, and require the full post-draw result snapshot and settlement
cycle before further optimizer work.

## 2026-07-29: Reviewed schedule fallback implemented and live-drilled

Task `TOTO-REVIEWED-SCHEDULE-FALLBACK` is implemented in the current branch.
A strict provider-neutral reviewed catalog now requires
snapshot-backed official plus independent claims, exact target
ID/number/fingerprint/event-order/event-ID binding, UTC agreement, freshness,
scheduled status, and deterministic hashes. Reviewed pins never receive an
API-Sports fixture/team ID and have schedule-only capability.

Mixed preparations use one atomic canonical pin set: exactly 15 orders or no
authoritative set. Existing API-Sports-only preparations retain the legacy
loader path. Final collection groups pins by real source, revalidates every
pin, never sends reviewed evidence to the market endpoint, and records
`totobrief_bk_fallback` for reviewed schedule-only events. Readiness and
probability evidence are rechecked when loading mixed pins. Catalog and source
snapshot bytes are checked again immediately before actionable publication;
mutation becomes `NO BET`.

The activation-disabled live drill for drawing 11988/4959 used a copied
database and fresh public snapshots for event order 8 / visible event 9. The
evidence is generic catalog data bound to fingerprint
`bed25208171b25e39a3fab84fb18b12e741af9b52f9863810d0a7a1d2d8e0c15`
and target event 178931; there is no resolver hardcode. Result:
`READY 15/15`, playable, provider distribution `14 api-sports + 1
reviewed-schedule`, no fake reviewed fixture ID, final source revalidation
`15/15`, and explicit TotoBrief BK fallback for the reviewed event. Activation
was false; no scheduler, package, marker, upload, or bet was created.

The first drill with the existing five-day expansion requested unsupported
API-Sports dates and correctly failed closed at `0/15`. Repeating with the
supported two-day playable horizon fetched 2026-07-28 through 2026-07-30 and
passed. This is operational evidence, not authorization to activate evening
automation.

An additive legacy-schema smoke initialized the new tables twice on a copied
database, preserved 2199 drawings, 32985 events, 30 legacy pins, and five
preparations exactly, and loaded an existing legacy ready set as 15 pins.
Canonical tables remained empty until a mixed set was explicitly published.

Verification after the final reviewed-pin identity invariant: focused
fallback/runner suite `301 passed`; full suite
`1475 passed in 245.16s`; repository-wide Ruff and `git diff --check` passed.

Latest implementation commits:

- `1d5736b Harden atomic scheduler and dynamic preparation`;
- `51f12ef Make morning automation passive by default`.

## 2026-07-29: Passive morning dispatcher installed and exercised

`com.totoai.morning-dispatcher.v1` is installed in the current user's launchd
domain with exact daily triggers at 08:00 and 10:30 Moscow time. The installed
plist bytes match the generated candidate, are owned by the user with mode
0600, use `/Users/turshevr/toto-ai` as the working directory, and invoke the
project wrapper. The wrapper contains no drawing number and no `--activate`.

A manual `launchctl kickstart` exercised the installed path. It completed all
three bounded attempts against drawing 4959, each returned the same explicit
`preparation_not_ready`/`deferred` result, and launchd finished with exit code
2. The persisted record binds drawing 11988/4959 and records
`activation_status=not_requested`, `plan_id=null`, and `plan_path=null`.
There is no evening LaunchAgent, package, marker, or bet. The recurring job
remains loaded for the next calendar trigger.

## 2026-07-29: Morning installation split into passive and actionable modes

`morning-preanalysis-plan` now omits evening activation by default. Its
generated recurring wrapper runs drawing-neutral synchronization and
preparation and may generate an exact evening plan, but cannot install that
plan. `--activate-evening` is an explicit opt-in reserved for after a live
activation-disabled 15/15 drill. This closes the mismatch where a command
described as non-betting always embedded `morning-dispatch --activate`.
Verification: `64 passed` for morning/CLI/artifact tests, `1444 passed` for
the full suite, repository-wide Ruff and `git diff --check` passed.

## 2026-07-29: Drawing 4959 live activation-disabled drill

A fresh network-backed `morning-dispatch` drill selected visible drawing 4959,
internal ID 11988, with deadline `2026-07-29T14:00:00Z`. The updated resolver
found 14 safe event candidates, including fixture 1493023 for event order 3
through reviewed provider team IDs 434/435. Event order 8 remained
`source_missing_competition`: API-Sports did not provide Iceland 3. Deild.

Preparation therefore remained atomically `unresolved`: no partial pin set was
published, `mapped_count` remained 0 at the readiness boundary, no evening
plan was generated, activation was not requested, and no package or bet marker
was created. The event-level readiness evidence retains all 14 matched
candidates plus the explicit source-missing event for diagnosis.

A historical network-free schema-v4 simulation verified all five generated
launchd triggers (T−45/T−30/T−20/T−16/T−10), package/archive/status/marker
publication through hard T−10, bank 4980 and stake 30. This is deterministic
scheduler evidence, not a real PLAY result and not a 15/15 live drill. Schema
v4 is now explicitly stale; these artifacts must be regenerated as v5 and
cannot be reused or executed.

Direct verification after combining scheduler and resolver changes:
`172 passed` for the critical scheduler/resolver set, `1443 passed` for the
full suite, repository-wide Ruff passed, and staged/unstaged diff checks
passed. No LaunchAgent is installed.

## 2026-07-29: Drawing 4959 resolver quality

Drawing 4959 event 4 now resolves systematically through reviewed,
competition-scoped API-Sports team identities: Gimnasia L.P. team 434 and
River Plate team 435. The fixture ID is not stored or hardcoded. Reviewed alias
catalog schema v2 adds contextual identities while preserving schema-v1 input.
The compatibility matcher validates either exact catalog schema and consumes
only the normalized flat alias view; contextual identities remain exclusive to
the systematic registry.

Domestic targets reject provider candidates classified as global competition,
preventing an unrelated friendly from bypassing country context. A successfully
observed domestic schedule may report `source_missing_competition` when the
target has an explicit numbered competition level and same-country provider
coverage contains no compatible competition. This remains a non-match: drawing
4959 event 9 (Iceland 3. Deild, absent from API-Sports) receives no pin and
preparation remains fail-closed.

## 2026-07-29: Atomic-final scheduler timing/recovery defects fixed locally

Four deterministic scheduler defects from the 2026-07-29 context reproduction
are closed in the uncommitted working tree. Morning dispatch reacquires UTC
after network preparation and refuses new evening scheduling at or after
T−45. Production preflight target validation also receives the fresh
post-preparation time rather than the phase start.

`FinalInputSnapshot.captured_at` is now sampled immediately after the direct
detail response returns. Final subprocess timeouts are recomputed from the
current clock on every attempt and end at
`T−10 − publication_reserve_seconds`. Final calculation completion and every
retry admission use that same actionable cutoff. Package writing,
archive-manifest writing, durable archive, recovery, status, and `.bet-ready`
marker creation may use the reserved interval and enforce the hard T−10
boundary instead. Recovery at or before hard T−10 may finish publication;
publication/recovery after hard T−10 removes `package.csv` and
`package-archive.json` and produces terminal zero-cost `NO BET`. The durable
audit row and immutable final input may remain non-actionable evidence.

Regression-first verification: the five requested reserve-boundary tests
passed (`5 passed in 0.68s`); the scheduler/morning/final-input/state/CLI suite
passed (`175 passed in 6.11s`); full pytest passed
(`1443 passed in 221.96s`); repository-wide Ruff and `git diff --check`
passed. No scheduler was installed, no bet was placed, and no automatic bet
path was added.

## 2026-07-28: Scheduler/morning review findings closed locally

The remaining atomic-scheduler review findings are fixed in the uncommitted
working tree. Morning dispatch now writes a hash-bound `scheduled/generated`
record before LaunchAgent activation, so a temporary bootstrap failure can
retry without regenerating or overwriting artifacts. Exact existing plan,
wrapper, and plist bytes are independently verified and reused. Dispatch
records are keyed by immutable drawing ID/deadline rather than the morning
calendar date, so the same allowed two-day drawing reuses one plan on the next
morning.

Final retry classification no longer examines exception text. Typed transient,
permanent, and integrity errors plus structured TotoBrief HTTP status determine
retryability. Unknown failures remain bounded/retryable; HTTP 503, timeouts,
and temporary configuration-service failures cannot become terminal merely
because their text contains `path` or `config`. Typed final-input, manifest,
package, identity, and hash integrity errors terminate final fail-closed.

Production `scheduler-execute --run-id` is now explicitly rejected for
schema-v5; `--run-id` remains available for simulation only. Legacy schema-v3
loading preserves its declared `project_root`. Operator-facing scheduler
messages consistently name the real T−10 cutoff. Generated `reports/` is
blanket-ignored by Git. The IL/UZ country mappings, reviewed Uzbek aliases, and
hard women/male/reserve/youth identity guard remain unchanged.

Final P1 review reproductions now enforce that persistent `bet_ready` and
`publish=complete` are written only after the exclusive `.bet-ready` marker
succeeds. Marker failure removes package bytes, records terminal `failed`, and
later ticks remain fail-closed. Archive recovery rejects a changed current
timing-override hash before publication. Morning activation retry calls the
exact plan/wrapper/plist verifier before invoking activation and rejects
tampered bytes.

Verification after these fixes: exact P1 reproductions `5 passed`; focused
scheduler/morning/final-input/CLI suite `186 passed`; full suite
`1433 passed in 237.71s`; repository-wide Ruff and `git diff --check` passed.
The earlier fixture rehearsal passed `42 passed in 99.09s`. No scheduler was
installed, no package or betting marker was generated, and no bet was placed.

## 2026-07-28: Atomic-final scheduler protocol complete

Drawing 4957 is the incident that motivated this redesign. Its one-shot
LaunchAgent failed during T−45 preparation and therefore never reached later
phases; a manual restart then compared normal live-pool changes across
different phases and failed again at final calculation. The outcome was
correctly fail-closed—zero approved coupons and no bet—but demonstrated that
the old lifecycle could not recover operationally.

Canonical computed `NO BET` output now has no coupons, cost, or derived-brief
placeholders. Immutable exact final-input snapshots bind the actual normalized
final probabilities and source payload/provenance and reject post-capture
tampering. Captured payloads can be persisted without a second detail fetch.
Scheduler plan schema v5 and generated launchd candidates use T−45, T−30,
T−20, T−16, and T−10, with explicit bounded runtime/retry budgets. Normal
execution is a locked short-lived tick over hash-chained persistent state;
warmup failure does not block final, transient final work has bounded backoff,
orphan attempts are abandoned, duplicate/concurrent ticks are idempotent, and
deadline misses become zero-cost `NO BET`.

The final tick captures exactly one direct detail snapshot and passes its
payload through preparation evidence refresh and EV without a second detail
fetch. Runner manifest v5 and pre-bet archive manifest v2 bind snapshot,
detail, and probability provenance; legacy archive rows remain readable but
cannot acquire atomic provenance. Fixture-only acceptance covers one-fetch
snapshot/tamper, warmup recovery, bounded transient retry, restart,
deadline miss, and overlapping ticks. No LaunchAgent was installed and no
upload or bet path was added.

Verification: focused scheduler/final-input/archive/orchestration tests
`278 passed`; final full suite `1407 passed`; repository-wide Ruff and
`git diff --check` passed. The deterministic atomic-final/research/offline
fixture rehearsal passed twice with the same `40 passed` result. No package,
upload, or bet was produced by those verification runs.

## 2026-07-28: Dynamic morning dispatcher implemented; live drill deferred

The recurring morning candidate is now drawing-neutral. `morning-dispatch`
selects one fresh current drawing, pins its exact number/internal ID/deadline/
fingerprint, runs 15/15 preparation, and idempotently creates a schema-v5
evening plan only while the full T−45/T−30/T−20/T−16/T−10 schedule remains
possible. A fixed `--expected-drawing-number` is no longer embedded in the
cross-day recurring job. Locks, persistent state, deferred retries, ambiguity
rejection, timing-span policy, and late-dispatch rejection are covered.

The five obsolete LaunchAgents for drawings 4947, 4950, 4952, 4953, and 4957
were booted out and their plist files removed. Follow-up inspection found zero
installed and zero loaded TotoAI LaunchAgents. The new generic morning
dispatcher and evening atomic scheduler remain uninstalled. The
activation-disabled 4958 drill selected the exact active drawing but deferred
at preparation: API-Sports resolved 14/15 after the country/alias patch and
does not contain the women fixture Huracán Women — River Plate Women. No plan,
package, marker, or scheduler was created. Installation remains blocked until
provider-neutral schedule evidence can resolve all 15 events safely.

## 2026-07-27: Active preparation rejects stale probability detail

The operational `sync-prepare`/`prepare-drawing` path no longer treats the
general 12-hour raw-detail cache lifetime as acceptable probability evidence.
Active preparation has a separate fail-closed cache-age ceiling of 60 seconds.
An older exact drawing cache is refreshed from `/drawing-info/{id}` before
READY evidence is written; if that refresh fails, the old cache is diagnostic
only and preparation is deferred. The historical collector keeps its existing
general cache policy.

This fixes the drawing-4957 failure where `sync-prepare` accepted a cache about
1618 seconds old and `run-drawing` immediately observed a different fresh BK
hash. Regression coverage reproduces that stale-cache/fresh-run lifecycle,
proves the fresh hash authorizes the unchanged ready pins, and proves a real
subsequent probability change still raises
`preparation_fail:probability_input_changed_or_missing`. The existing
monotonic/CAS refresh rules and unrelated readiness fields remain unchanged.
Current combined verification: focused operational/probability tests
`42 passed`; full suite `1356 passed in 237.33s`; repository-wide Ruff and
`git diff --check` passed.

## 2026-07-27: Reviewed VOID result lifecycle

Finished drawings may now record a cancelled/postponed event only through an
explicit reviewed override: one or more public 1-based `--void-event` values
and a required valid HTTP(S) `--void-source` evidence URL. An unresolved empty
TotoBrief result still fails closed without that evidence, and an override is
rejected when TotoBrief already supplies a result or score. Current immutable
result snapshots use hash schema v3 and store `*`, `result_status = "void"`,
an empty score, and the exact reviewed source. Legacy schema-v1 and timed
schema-v2 snapshots remain independently verifiable.

Settlement treats every coupon selection at a VOID event as correct and omits
that event from fixed-miss and zero-exposure-miss diagnostics. Existing
non-VOID settlement identities remain byte-compatible because an empty VOID
list is not added to their hash payload. CLI pass-through, immutable evidence,
inconsistent override rejection, schema-v2 compatibility, and settlement
semantics are covered. Verification for the complete uncommitted lifecycle and
probability-evidence patch: focused `65 passed`; full `1354 passed in 220.83s`;
repository-wide Ruff and `git diff --check` passed.

## 2026-07-27: Reused-pin probability evidence refresh

`prepare_drawing()` now reuses an already validated exact 15-pin set while
atomically refreshing only `probability_input_sha256`, `target_fetched_at`, and
the preparation row update time. All event, confidence, margin, eligibility,
and schedule diagnostics remain unchanged. A compare-and-swap retry makes the
evidence monotonic under concurrent refreshes: older timestamps are rejected,
equal timestamp/hash input is idempotent, and an equal timestamp with a
different hash fails closed. Drawing identity, fingerprint, and pin content
remain unchanged. Missing, malformed, non-finite, non-positive, or
non-normalized probability rows fail before the readiness transaction, leaving
the prior evidence and pins untouched.

## 2026-07-23: Finished-drawing lifecycle recovery

Explicit `sync-finished-results`, `settle-drawing`, `post-draw-run`, and
`post-draw-plan` commands implement the non-betting post-draw lifecycle.
Result, package, and settlement records are append-only and hash-bound;
identical reruns are idempotent and corrected results append. Drawing 4952
settles 166 coupons/4980 RUB at best 5. Because API payments/rules evidence is
null, category entitlement, return, and ROI remain null with
`unknown_until_payouts`; no category threshold is inferred.

This file is the project-local state note for TotoAI only. Do not mix it with
local skills, personal knowledge bases, team knowledge bases, or unrelated
memory stores.

## Emergency Pre-Bet Safety Slice Complete (2026-07-23)

Production-playable EV packages now pass an explicit fail-closed safety gate
before publication. The gate reuses package-audit exposure semantics and
serialized thresholds for near-fixed concentration, fixed low-probability
outcomes, and zero exposure to materially modeled outcomes. Valid unsafe
packages become coupon-free `NO BET`; malformed safety evidence is an
operational failure and cannot be accepted as `PLAY`. The archived drawing
4952 package/probability fixture is rejected with explicit concentration and
material-outcome reason codes.

Morning preparation is usable only with a ready 15/15 mapping, no unresolved
orders, playable eligibility, and matching fresh probability-input evidence.
The drawing-4953 zero-mapped/all-unresolved regression terminates as `FAILED`
through the production resource preflight and scheduler, with no package or
`.bet-ready`. Runner schema-v4 ingestion does not trust declared
`package_safety`: it canonically validates thresholds and recomputes the gate
from serialized original evaluated coupons and probabilities before any PLAY
or NO BET return. Safety evidence separately hash-binds the original package
SHA-256 and the approved uploadable coupons; rejected packages retain their
original audit evidence while publication remains coupon-free. Tampered
current manifests and legacy manifests without complete evidence fail closed.
For terminal `NO BET`, canonically recomputed safety may itself reject the
package or may pass when another audited gate (for example timing or
self-dilution) is the actual rejection. The terminal reason preserves that
machine-readable gate, and publication remains coupon-free in both cases.
Package-safety thresholds are now trusted scheduler-plan inputs, serialized in
the plan and forwarded explicitly to `run-drawing`. Manifest ingestion requires
its canonical safety config to equal the approved plan config and recomputes
with the plan config, so a self-consistent manifest with relaxed thresholds
cannot authorize `PLAY`.
Actionable schema-v3 scheduler plans require the exact internal drawing ID.
Systematic preparation/preflight persists or verifies that ID together with
the visible number and authoritative `ended_at`. Before `.bet-ready`, the
scheduler imports and verifies the package in the durable archive, then
rechecks the authoritative clock both immediately after that import and
immediately before marker creation. Crossing T-10 removes publication
artifacts and fails closed while retaining the database archive for audit.
Cover Engine mathematics are unchanged. Finished result synchronization,
settlement, payout/ROI persistence, and post-draw retries remain pending.

## Unified Package Audit/Metadata Foundation Complete (2026-07-23)

Hybrid Package Program Milestone 1, the first vertical slice, is complete.
Independent acceptance is `READY`: focused tests passed (`88 passed`), the
full suite passed (`1269 passed`), repository-wide Ruff passed,
`git diff --check` passed, the real drawing-4952 audit was verified, and all
P1/P2 review findings are closed. The implementation does not change package
selection, EV ranking, Cover generation, scheduler behavior, or publication.
The common `PackageStrategy` contract has exactly `cover`, `ev`, and `hybrid`.
`package-audit` accepts canonical 15-outcome CSV/text packages, a positive
stake-multiple requested/effective bank, optional event probabilities, and
emits deterministic schema-v1 JSON/CSV/Markdown.

The audit reports ordered canonical coupons and SHA-256, requested/effective/
used bank, coupon count, 1/X/2 event counts and shares, fixed/near-fixed
events, union brief and Cartesian size, exact union-brief minimum-distance
distribution, derived guaranteed category, and exact coverage shares for
categories 15 through 9. It uses an independent exact streaming distance
calculation. Cover target categories fail closed when they do not verify.
Probability-aware audits add conditional union-brief category probabilities
and explicit fixed-low-probability warnings; concentration never modifies a
coupon.

Immutable report bundle paths include the full package and audit SHA-256.
Existing bundles are reused only after deterministic JSON/CSV/Markdown bytes
and the exact file set verify. JSON persists the exact JSON-compatible audit
hash payload and configuration for independent recomputation. Complete-report
recomputation fails closed unless every duplicated hash-bound displayed field
is canonically equal to that payload and the stored audit hash verifies; direct
payload recomputation remains supported. Report publication reconstructs and
verifies that complete report before creating any filesystem output, so
post-construction mutation of nested audit mappings fails with no partial
bundle. CLI package CSV loading is streaming and bounded by
`effective_bank // stake`.

The real drawing-4952 EV CSV independently reproduces 166 coupons, fixed events
1/5/8/14/15, event-12 counts 163/2/1, 5184 union variants, category 15/14/13
coverage 166/992/2600, no 13/14/15 guarantee, and worst distance 6. The package
is labelled `ev`; its derived category 9 is descriptive union-brief coverage,
not a Cover declaration.

The target product explicitly generates and compares three strategies under
one user-supplied bank that is a positive stake multiple:

- **Cover**: explicit brief, target category, compact package, and exact
  conditional Hamming guarantee verification;
- **EV**: the existing exact monetary-EV ranking, separately labelled and
  audited for concentration;
- **Hybrid**: calibrated final probabilities, modeled category-hit
  probabilities, Hamming/cover evidence, EV, and frozen
  diversity/concentration constraints.

The program also makes official/reputable sports statistics and the full
post-draw lifecycle first-class work. Market probability remains the
prior/fallback; sports data is collected in the morning, cached, backfilled,
time-valid, calibrated, and audit-only until prospective gates pass. Every
morning/fallback/final package will eventually be archived before results,
force-refreshed after completion, settled for hits/categories/cost and—only
when actual payout evidence exists—payout/profit/ROI.

The following milestones remain future and are not implemented by this slice:

- actual Hybrid package selection/optimization;
- an official/reputable sports-statistics probability model and its calibrated
  integration;
- mandatory post-draw result refresh, settlement, and payout/profit/ROI ledger;
- morning/evening/post-draw scheduler integration for the unified
  Cover/EV/Hybrid lifecycle.

True probability-aware Cover generation and common EV/Cover comparison also
remain future work. This milestone establishes audit and metadata foundations
only; it is not evidence of profitability or a proven winning strategy.

## Evening Scheduler Launchd Root Fix (2026-07-22)

The drawing-4952 incident exposed two launchd-only gaps: the evening wrapper
started without a project working directory, and preflight used a new empty
run cache instead of the warmed preparation cache. Scheduler plan schema v2
now carries an absolute `project_root`; schema-v1 plans remain loadable through
strict common-root inference and their original plan-ID validation.

Generated evening wrappers `cd` to `project_root`, LaunchAgent candidates set
`WorkingDirectory`, and every production subprocess receives the same explicit
`cwd`. Preflight now passes absolute project `data/raw` and
`data/external-cache/api-sports` paths. Fallback and final package phases keep
their isolated run-scoped caches unchanged. A real subprocess regression runs
preflight from launchd-like `cwd=/`, blocks HTTP, consumes warmed local caches,
and proves atomic 15/15 pin preparation.

The project-root boundary rejects `/`, missing/non-directory roots, symlinked
roots or operational path components, and any database/aliases/output escape
after resolution. Safe existing schema-v1 and schema-v2 plans remain covered.

## Scheduler Operational Contracts (2026-07-22)

The generated evening scheduler command and `run-drawing` now share the exact
`--min-gross-ev` CLI contract. The configured finite threshold reaches the
existing EV decision configuration, while the default remains `1.0`.

`scheduler-plan --env-file` generates a `umask 077` wrapper that validates a
current-user-owned regular non-symlink env file with mode no broader than
`0600` both before publication and at execution. It requires a non-empty
`API_SPORTS_KEY` without printing its value. The LaunchAgent plist contains
only the wrapper path; no key is embedded in the plan, plist, or logs.

`sync-prepare --open --expected-drawing-number N` now checks the fresh
page-one-selected visible drawing before any detail fetch, provider
preparation, or pin write. A mismatch fails closed. The separate
`morning-preanalysis-plan` command generates, but does not install, a
non-betting launchd candidate beneath `reports/rehearsal`; it supports multiple
morning times and bounded retries, uses the same secure env contract, and
creates no betting markers.

Final verification: the affected scheduler/synchronization suite passed
`180 passed in 17.92s`; the full suite passed
`1199 passed in 203.22s (0:03:23)`. The exact scheduler-generated
`run-drawing` argv contract smoke passed `1 passed in 0.57s`. Repository-wide
Ruff reported `All checks passed!`; all six affected CLI help smokes and
`git diff --check` passed. No network, `.env`, launchd installation, commit, or
push was used.

## Country Identity and Progressive Preparation (2026-07-22)

Country context comparison now uses shared stable identities for Russian,
English, ISO alpha-2/alpha-3, and common provider forms. This includes
`США`/`USA`/`US`/`United States` equivalence while preserving fail-closed
country mismatches. The same identity comparison is used by conservative event
resolution and the persistent reviewed team registry; it is not a team or
drawing alias mechanism.

Missing-start preparation now resolves the accumulated provider schedule after
each successfully loaded date without publishing preparation or pins. It stops
requesting later dates only after unique 15/15 resolution and normal playable
two-Moscow-date timing. If readiness is not reached, it continues through the
configured horizon. Any attempted date failure before readiness remains
fail-closed, and final ready pin publication remains atomic. The self-contained
drawing-4952-style reviewed-provider-ID regression reaches 15/15 on dates
July 21-23 without requesting July 24-26; its unresolved counterpart continues
and fails closed on a later required date.

Verification: country/preparation focused tests passed `32 passed in 5.22s`;
the synchronization/systematic-resolution integration set passed `17 passed in
79.14s`; the full suite passed `1184 passed in 200.39s`. Repository-wide Ruff
and `git diff --check` passed. No network, `.env`, commit, or push was used.

The authorized live diagnostic preparation for drawing 4952 (internal ID
11970) synchronized exactly 15 events and 15 quote sets, then reached atomic
`ready` preparation with 15/15 pins. Its final cache-first preparation made
zero additional TotoBrief detail requests and zero provider requests. It
generated no package, scheduler marker, or bet; this is operational readiness
evidence only, not profitability evidence.

## Coordinated TotoBrief Synchronization (2026-07-22)

The TotoBrief transport now has one request coordinator shared by normal
client and CLI paths. It enforces a configurable two-second minimum interval,
persists server-authoritative `Retry-After` even after the final exhausted 429,
and applies capped exponential backoff with jitter for 429, temporary 5xx,
timeout, connection, chunked-transfer, and content-decoding failures. A locked,
fsynced project-local state file coordinates separate CLI processes; explicit
schema/`written_at`/plausibility policy distinguishes stale or corrupt state
without shortening a valid long block. Diagnostics strip query strings and
secrets. Clock, sleep, and randomness remain injectable for deterministic
tests.

Drawing summaries and detail are now separate synchronization stages. Page-one
metadata/status changes commit before detail fetch, so a deferred current
detail cannot leave earlier drawing statuses stale. Detail persistence is
idempotent and resumable. Exact schema-validated raw detail caches require a
hash/provenance sidecar commit marker, accept a configurable 12-hour freshness
window, and reject wrong drawing IDs, malformed or torn payloads, missing
sidecars, non-contiguous/duplicate orders, partial quotes, stale data, future
timestamps, and symlink/escape paths. Exactly 15 complete events are required
before cache or SQLite persistence. A valid cache may populate a locally
missing drawing without another detail request, while a partial legacy SQLite
detail remains eligible for retry.

`sync-prepare --open` is the single morning operational path: one page-one
request, page-one-only open selection, cache-first exact detail
synchronization, then the existing
API-Sports preparation. It exposes request waits/retries and cache provenance,
commits partial summary progress, and exits fail-closed when detail is
unavailable. `prepare-drawing` consumes the synchronized exact local
drawing/cache by default and only performs remote TotoBrief work with explicit
`--refresh-totobrief`. Null `start_at` remains supported without fabricated
timestamps; existing bounded schedule-date expansion remains authoritative.
`sync-prepare --open --sync-only` performs the strict synchronization path but
does not call API-Sports or write preparation/pins. Full synchronization writes
pins only after all detail identity/status/deadline and 15-event gates pass.

No live network or `.env` was used during implementation or tests. No
profitability claim follows from synchronization reliability work.

Final verification for this hardening pass: the explicit adversarial/focused
suite passed `51 passed in 25.25s`; the full suite passed `1173 passed in
199.65s`. Repository-wide Ruff and `git diff --check` passed. CLI help smoke
passed for `sync-prepare`, `prepare-drawing`, `collect`, `inspect-api`, `info`,
and `drawings`. No live request or `.env` was used.

## Deterministic Offline Runner Replay (2026-07-21)

`run-drawing` now has an explicit `--offline-replay` path for one exact internal
drawing ID, strict TotoBrief target cache, strict API-Sports schedule cache, and
timezone-aware `--replay-as-of`. The command validates cache schemas and
payload hashes, provider, drawing ID/number/deadline/fingerprint, target event
count/IDs/order, and provider fixture/team identity before running. It never
reads `API_SPORTS_KEY` or constructs live clients.

An explicit `--replay-root` is mandatory. The replay database, report
directory, provider cache, and temporary artifacts are derived below that
root, rather than inheriting `data/toto.db`, `reports/`, or the live cache.
Explicit output overrides are accepted only when they resolve strictly below
the same root. Repository root, project `data/`/`reports/`/cache/marker state,
ancestor overlap, and any symlink traversal are rejected before the first
write; the boundary is revalidated immediately after root creation.

Replay uses the injected timestamp for runner and schedule-freshness gates,
runs the real atomic preparation, 15 pins, cached schedule revalidation,
runner, diagnostic EV, and manifest-v4 path, and records cache paths, whole-file
hashes, payload hashes, provider, and replay time in the manifest. It is always
`RESEARCH ONLY` and non-actionable: it directly publishes only the JSON and
Markdown runner report, never a production package or scheduler marker.
Scheduler ingestion classifies manifests with replay provenance as an explicit
non-production `ignored` execution and creates no terminal marker at all.
Malformed live production manifests retain the existing `.failed` semantics.

The self-contained drawing-4951 target fixture now mirrors DB identity 11968,
deadline `2026-07-21T16:00:00Z`, event IDs 32851-32865, championships, and saved
quotes. Together with the saved API-Sports schedule it resolves 15/15 and
reaches provider fixtures 1492290, 1548164, and 1547777 through the generic
resolver; none of these values is present in production source or aliases.

## Systematic Team Resolution Phase 2 (2026-07-21)

The production drawing workflow now defaults to prepared systematic identity
pins. `prepare-drawing` resolves all 15 target events against provider schedule
fixtures and publishes a `ready` preparation and all 15 fixture/team/start
pins in one transaction. Unresolved runs publish zero authoritative pins while
retaining machine-readable diagnostics and review-queue records. Identical
ready runs are idempotent; changed provider identity or drawing fingerprints
fail closed.

Resolution prioritizes reviewed registry and provider-team IDs. Otherwise it
requires an oriented unique fixture, date and competition/country/league
context, one exact or high-confidence side, a sufficiently strong pair, and a
deterministic margin. Transliteration and normalization are evidence only;
sport/date and shared tokens cannot auto-accept two weak team names. Alias
identity is scoped by country and competition, with an additive migration for
the Phase-1 global alias table. Existing reviewed alias configuration and only
already accepted exact/reviewed history remain valid seed sources.

The scheduler preflight now runs `prepare-drawing --open`. The final runner
requires an exact `ready` preparation and 15 valid pins. It fetches recent
schedule data to revalidate provider, fixture, team IDs, and start time without
rematching display names. Missing, failed, stale, or changed revalidation data
cannot produce a bet-ready package. Legacy name matching is available only by
explicit direct-run opt-in and is removed from scheduler environments.

Preparation derives sport, country, competition, and league context from each
TotoBrief event/championship. Stable geographic exonyms are normalized locally;
there is no network translation and no team-specific production mapping. An
exact-looking pair from a conflicting competition level (for example Serie B
for a Serie A target), country, sport, or date is rejected in the normal
service/CLI path. Every required date in the bounded eligible search window
must fetch successfully before READY or pin publication; successful dates and
per-date failure diagnostics are retained for retry.

Collection persistence and runner manifest schema v4 contain an authoritative
`pinned_revalidation` summary: expected/matched counts, ordered missing,
provider-failure, stale, date-failure, identity-failure, and start-time-failure
events, failed dates, schedule age/freshness, identity-check booleans, and
per-event reasons. Playable execution gates before timing, audit, or EV unless
the summary proves fresh exact 15/15 provider/fixture/team/orientation/start
identity. TotoBrief BK fallback remains diagnostic and cannot authorize PLAY.
The scheduler validates the same summary and emits `.no-bet`, never
`.bet-ready`, for any valid but non-ready result; absent legacy summaries fail
closed.

The drawing-4951 regression is an offline replay with the actual
2026-07-21T16:00:00Z deadline, target event/championship metadata, and saved
provider fixture/team IDs. It resolves 15/15 without adding the six
current-drawing aliases. Prior 4945/4947/4950 behavior remains covered, and an
unseen-team regression guards against drawing-specific production logic.

Final pre-commit verification including isolation hardening is
`1140 passed in 196.14s`.
The replay/scheduler/CLI/report focused suite was `151 passed in 92.20s`, and
the isolated 4951 E2E alone was `1 passed in 78.34s`. Repository-wide Ruff,
whitespace, and production-hardcoding results are recorded in the completion
response.
Focused systematic resolver/runner/scheduler verification was `194 passed in
83.51s`; the post-failure regression rerun was `15 passed in 7.37s`.
Repository-wide Ruff reported `All checks passed!`; `git diff --check` exited
zero; and the production scan found none of drawing 4951, its drawing ID, the
three asserted fixture IDs, or the six current-draw team aliases in `src/` or
the production alias file. No profitability claim follows from this work.

## Current Important Commits

The two completed sections above are included in the same local commit as this
state update. Its hash is intentionally not embedded in the commit itself.

- `f771bbe` Initial TotoBrief API client and CLI
- `bdcf776` Add historical data collector
- `d368704` Add historical research analytics
- `c962613` Add API inspector
- `4112362` Improve inspect-api with drawing number support
- `8ceda4b` Fix playable drawing selection
- `68cabb9` Add Cover Engine
- `0f92ee5` Add exact Cover Package verifier
- `7e95f24` Add baseline brief generator
- `8b3ed6d` Add persistent project memory bank
- `2bd484a` Fix final safe runner review findings
- `e9a23d0` Fix real null-start event matching
- `f655ce2` Initially captured the incident-4950 readiness patch; full
  verification was `1090` full tests and `151` targeted QA. Historical
  untracked `reports/` artifacts are excluded from this capture.

Note: the current PR branch was rebased onto an empty remote base for the first
GitHub pull request, so local branch commit hashes may differ from the original
task commits listed above.


## Drawing 4950 No-Bet Assessment (2026-07-20)

Current boundary statement for the latest reviewed output:

- Root causes are recorded as:
  - `7/15` raw matching before aliases in the first matching pass.
  - `2` provider-absent events remain unresolved after reviewed-alias constraints.
  - `start_at = null` in TotoBrief event payloads for this draw, so effective event timing is reconstructed only when a reviewed timing override is accepted.
  - Exact self-dilution gating: effective budget is `min(requested_bank, floor(pool_sum × 1% / stake) × stake)`.
- `drawing-4950`: with `pool_sum = 81_445`, `requested_bank = 4_980`, `stake = 30`, the exact cap is `810`.
- Matcher behavior on reviewed data is now `13/15`; unresolved pairs stay fail-closed and retain `NO BET` timing semantics.
- Reviewed timing overrides are strict: schema-vetted override catalog + provenance match + overlay validation. If any preflight/audit/package audit is missing or changed, timing remains `unknown` and no EV package is built.
- Reporting baseline for that incident was runner manifest `schema_version = 3`:
  raw/effective timing and budget provenance were explicit. Current production
  output is schema v4 with the additive mandatory pinned-revalidation summary.
- Runner outputs now record immutable run-scoped hashes for inputs and package artifacts.
- Old `drawing 4947` and legacy `drawing 4950` `schema_version = 2` report files are historical pre-fix artifacts and are not treated as current output evidence.

Current verification (requested pack):

- Full pytest: `1090 passed`.
- Targeted QA pass set: `151 passed`.
- Ruff and `git diff --check`: both passed.
- Final targeted verdict: `SAFE TO PROCEED` for documented boundaries.

Open items remain:
- Live platform install and prospective live production run are still pending; no profitability claim is made from this evidence.

## Drawing 4950 Early-Run Check

An early production-style collection for drawing 4950 exposed an immutable
identity bug before the final window. A base retry reused nine cached schedule
responses and repeated one failed date request. Match content and timestamps
were unchanged, so the two passes shared a `collection_id`, while their
request/cache/quota provenance differed; storage correctly rejected the second
snapshot as conflicting content.

Collection identity now binds request/cache counters and observed quota state.
A regression proves that operationally different passes with identical match
content persist under distinct identities. The repeated live command completed
three passes without conflict.

The early 2026-07-19 check matched 7/15 events and remained timing `unknown`
because the API-Sports free plan allowed fixture dates only from 2026-07-18
through 2026-07-20 and rejected 2026-07-21. Eight dispositions therefore used
explicit `partial schedule` fallback. This is an early-window provider limit,
not a matcher-v4 failure; the final 2026-07-20 run must fetch 2026-07-21 after
the free-plan date window advances. External probabilities remain audit-only.
Full verification after the identity correction: `936 passed`; repository-wide
Ruff and `git diff --check` passed.

The protected final run for drawing 4950 is installed as macOS LaunchAgent
`com.totoai.run-drawing-4950`. It is pinned to drawing ID 11964, number 4950,
and deadline 2026-07-20T14:30:00Z. Launch attempts begin at 16:40 Moscow time;
the runner starts final work at T-20 (17:10), stops new provider work at T-5
(17:25), uses bank 4980 RUB and stake 30 RUB, and never places a bet. Logs are
`data/external-cache/scheduled-runner/4950.stdout.log` and
`data/external-cache/scheduled-runner/4950.stderr.log`.

## Historical Sync Audit

The core SQLite collector is currently manual rather than continuously
scheduled. This caused the local open-drawing lookup to be stale until
`collect` was run; the safe runner itself resolves its pinned target directly
from TotoBrief API. A full sync backfills all available pages, so this is a
freshness gap rather than permanent loss, but automatic incremental sync is a
remaining production task.

After the 2026-07-19 sync, SQLite contains 2190 drawings from 2759 through 4950.
Every stored drawing has exactly 15 events and 15 quote rows. The only numeric
gaps are 3843 and 3844, and TotoBrief API page 23 also omits those numbers.
Drawing 4948 is finished with 15 results; drawing 4949 is still `expected` in
TotoBrief with no results; drawing 4950 is active. Some older finished events
have missing source results (360 drawings are not result-complete); existing
standard backtests exclude incomplete/void results rather than inventing them.

## Drawing 4947 Incident and Matcher v4 Correction

The first scheduled production-style run completed normally but returned
zero-cost `NO BET`: TotoBrief supplied neither event starts nor English names,
and matcher v3 resolved 0/15 provider events. This was a product-readiness
failure, not a provider outage. The saved API-Sports responses contained 1096
fixtures and all 15 target pairs. Earlier null-start work had only made times
optional and expanded schedule dates; drawing-specific aliases from 4945 had
incorrectly been treated as a general solution.

Matcher v4 preserves exact/reviewed aliases first and adds a constrained
transliterated fallback for Cyrillic targets with no English alternatives. It
requires pair score >= 0.74, each team score >= 0.55, and runner-up margin >=
0.15; all weaker cases remain fail-closed. The complete saved drawing-4947
schedule now resolves the exact expected 15 provider IDs and collection replay
returns `eligibility=playable` with 15 provider-derived times. Drawing-4945
replay retains 13 correct matches and its two previous safe misses.

The regression uses sanitized real provider schedules, not synthetic equal-name
fixtures. Incident record:
`docs/incidents/2026-07-17-drawing-4947-no-bet.md`.

## Verification

- Matcher-v4 production regression: drawing 4947 resolves 15/15 and collection
  timing is `playable`; drawing 4945 remains 13 matches plus two safe misses.
- Matcher/collection/runner focused pytest: `105 passed`.
- Full matcher-v4 pytest: `935 passed in 12.38s`.
- Repository-wide Ruff and `git diff --check`: passed.
- Focused final safe-runner pytest: `200 passed in 2.81s`.
- Full pytest: `930 passed in 10.81s`; final repeat after documentation and
  memory updates: `930 passed in 11.92s`.
- Publication regressions: `6 passed`.
- Runner CLI regressions: `21 passed`.
- Path-safety regressions: `5 passed`.
- Repository-wide Ruff: `All checks passed!`.
- `run-drawing`, `collect-external-odds`, and `ev-package` help smokes exited
  zero.
- `git diff --check` passed.
- Corrective RED/GREEN evidence: `.superpowers/sdd/final-safe-runner-fix-report.md`.

## Safe Drawing Runner: Final Review Approved

All Important and Minor findings in the final safe-runner review are implemented
and locally verified. Independent whole-feature review approved the range
`b54490db..2bd484ad` with no remaining Critical, Important, or Minor findings.

The T-5 UTC boundary now reaches every schedule date/page, market request/page,
and API-Sports transport retry. Once closed, the active immutable pass makes no
later provider call, fills unresolved dispositions with `safety stop reached`,
persists all 15 events, and returns `stop_reason="safety_stop"`.

Publication is a final deadline-aware phase. The clock is rechecked after the
`complete` callback and before actionable child/runner artifacts. Coverage, EV,
and runner artifacts share one outer transaction: every pre-commit
`BaseException` restores/removes them, while an interruption after commit is
treated as successful publication. Every runner `NO BET` skips the EV child;
real CLI threshold acceptance recursively proves diagnostic top-coupon strings
are absent from every linked artifact.

The package boundary receives the expected `PinnedDrawing`, fetches one fresh
payload, and compares drawing ID, number, deadline, and fingerprint before
timing or heavy EV work. Expected second-fetch mutation is a valid zero-cost,
coupon-free target-mismatch `NO BET` with `ev_run=None`; corrupt structural
results remain failures.

After target pinning and before waiting, preflight computes all possible report
paths, rejects lexical/symlink collisions with the database, aliases, cache
root, and sibling outputs, probes report/cache writability, and constructs the
provider. The same guard repeats immediately before publication, every writer
receives protected inputs, and coverage reports have the equivalent collision
guard. Regressions cover unwritable roots, lexical and symlink aliases,
input/output collisions, and publication TOCTOU without replacing inputs.

The safe-runner design example uses bank 4980 for stake 30. All implementation,
verification, and independent review steps are complete.
Probability, EV, category, bank, stake, consensus, timing, and coverage-gate
definitions are unchanged.

The prospective external-odds gate remains `PENDING`; no 30-drawing/450-event
gate is marked complete and external probabilities remain audit-only.

## Latest Review Fix: Production `run-drawing` CLI

Task 5 review hardening now rejects a `drawing-info` payload whose parsed
internal drawing ID differs from the page-one reference before target pinning.
Controlled provider failures build a sanitized `BadParameter` inside the
handler and raise it only after leaving the secret-bearing exception context,
so the reachable `__cause__`/`__context__` graph contains no API key.

The CLI regression suite now directly covers the target and exact stored-timing
bridges, corrupt stored state, the exact approved option/default surface,
PLAY/RESEARCH output, Rich phase and countdown descriptions, recursive secret
graph traversal, and interruption during real runner-pair publication with no
successful manifest left behind. Tests use no network or real sleep.

Review RED was `3 failed, 12 passed in 0.71s`. Final focused pytest passed
(`15 passed in 0.53s`), `run-drawing --help` exited zero with only the approved
controls, focused Ruff passed, full pytest passed (`885 passed in 7.55s`), and
repository-wide Ruff reported `All checks passed!`.

## Latest Completed Task: Production `run-drawing` CLI Wiring

The `run-drawing --open --bank <RUB>` command now wires the existing safe
runner into production dependencies without changing runner, collection, audit,
or EV algorithms. It validates the runner configuration before provider access,
requires `API_SPORTS_KEY`, permits only `api-sports`, uses fresh per-invocation
collection caches, pins and revalidates the exact TotoBrief target, resolves
stored timing through the existing read-only exact lookup, and keeps the latest
30-drawing coverage audit diagnostic-only.

The command exposes only the approved operational controls. It writes coverage
reports only when an audit completed, EV reports only when EV ran, then writes
the runner JSON/Markdown pair with those paths as associated links. Valid
`NO BET` exits zero without coupon output; interruptions publish no final
runner manifest. Provider failures sanitize the API key through recursive
exception chains. No automatic betting was added.

Verification: required RED was `7 failed in 3.07s` before registration. Final
focused pytest passed (`7 passed in 0.41s`), command help succeeded with the
approved controls, focused Ruff passed, full pytest passed (`877 passed in
8.08s`), and repository-wide Ruff reported `All checks passed!`.

## Latest Completed Task: Deterministic Runner Reports

The safe drawing runner now publishes one deterministic canonical JSON manifest
and operator-readable Markdown report as a rollback-safe pair. A 12-character
lowercase SHA-256 run ID binds the canonical target, preflight timestamp,
runner configuration, and the literal supported provider `api-sports`, so
distinct invocations do not silently overwrite one another.

The manifest is assembled from an explicit serializable payload and never uses
`asdict(result)`. NumPy surfaces, probability matrices, cache paths, and
diagnostic `top_coupons` remain outside the report boundary. `NO BET` never
serializes coupons; `PLAY` and `RESEARCH ONLY` serialize only selected package
coupons. JSON is sorted, compact, and ASCII. JSON/Markdown output collisions
with declared inputs are rejected before writing.

Task 4 review hardening adds explicit final-target provenance to the terminal
result. `final_fingerprint` is `None` when final resolution never completed,
records the actually observed fingerprint on a mismatch, and equals the pinned
preflight fingerprint before collection, timing, audit, or EV may follow.
Constructor invariants reject missing, malformed, unstarted, or later-phase
inconsistent observations. Runner manifests serialize this value verbatim,
including JSON `null`; mismatch and early-cutoff reports have regressions.

Both artifacts are fully rendered to same-directory temporary files and backed
up before atomic replacement. Any `BaseException` after publication starts
restores the previous pair byte-for-byte, or removes both newly installed
artifacts. One transaction token now determines every temp and backup path for
both finals before any write; each path is created exclusively and every known
transaction path is cleaned even if rendering or backup creation is interrupted.
Lexical and symlink input aliases are rejected before writes. External coverage
remains diagnostic, external probabilities remain audit-only, and no EV,
category, bank, or probability definition changed.

Initial verification: the required RED import failure, focused GREEN twice
(`12 passed` in `0.34s` and `0.37s`), focused Ruff, full pytest (`860 passed in
67.20s`), and repository-wide Ruff. Review-fix RED was `13 failed, 50 passed`,
with an additional isolated timing-provenance RED. Final focused GREEN was
`115 passed in 0.34s`; full pytest passed (`870 passed in 169.32s`) and focused
and repository-wide Ruff both reported `All checks passed!`.

## Latest Completed Task: Provider-Neutral Runner Orchestration

`run_drawing()` now implements the pure dependency-injected runner state
machine in the fixed preflight, wait, final resolve, collect, timing, audit,
and EV order. It compares final targets by drawing ID, visible number,
deadline, and canonical fingerprint; rechecks the injected UTC wall clock at
every safety-bound phase; keeps coverage gate output diagnostic; skips EV for
non-playable timing in Playable mode; and discards every package that finishes
at or after T-5. Research mode obeys the same cutoff.

`DrawingRunnerResult` lives in `runner/models.py` and validates immutable
terminal decisions, exact collection/timing/EV target identity, UTC and
contiguous chronological phase timestamps, matching EV configuration, and
zero-cost coupon-free attached packages for `NO BET`. Ordinary EV-threshold
`NO BET` may retain its diagnostic run and top-coupon diagnostics, while a
late package is removed with `ev_run=None`.

Task 3 review hardening now rechecks the injected clock immediately after
every final/collection/timing/audit/EV progress notification, so a synchronous
callback cannot advance to T-5 and start bound work. It constructs and
validates every success or fail-closed result before emitting `complete`, and
requires an attached `PLAY` EV run to have its own exact `playable` timing.
Coverage `GO`, `PENDING`, and `STOP` remain audit-only. Regression tests cover
all five callback race boundaries, invalid terminal construction, early-exit
progress, and coverage non-interference.

Verification: the required RED import failure, focused runner GREEN (`83
passed`), focused Ruff, full pytest (`838 passed`), and repository-wide Ruff
(`All checks passed!`). Review-fix RED was `8 failed, 34 passed`; focused
review GREEN was `93 passed in 0.28s`, followed by full pytest (`848 passed`)
and repository-wide Ruff (`All checks passed!`). Tests use only injected
clocks, sleepers, resolvers, collectors, auditors, and package builders; no
real network, filesystem, or sleep is used. No category, cover, bank,
probability, coverage-gate, timing, or EV definition changed.

## Latest Completed Task: Pinned Prospective Collection and Safety Stop

`collect_fresh_open_external_odds()` now accepts an optional already-pinned
`TargetDrawing` and UTC `stop_at` boundary. With neither argument, standalone
collection keeps resolving exactly one open target and retains its previous
retry behavior. At or after the supplied cutoff, it refuses the first pass or
stops after an immutable completed pass with `safety_stop`; it never starts a
later base or expansion pass and caps retry sleeps to the remaining safe time.

Verification: prospective RED/GREEN tests, focused prospective/CLI/end-to-end
regression tests, focused Ruff, full pytest (`806 passed`), and repository-wide
Ruff (`All checks passed!`). No external probability, category, cover, budget,
EV, or probability definition changed.

## Latest Completed Feature: Fresh Prospective Collection

`collect-external-odds` now defaults to a unique per-invocation cache session
instead of silently reusing unexpired historical payloads. It pins one open
TotoBrief target, creates a new API-Sports client for each pass, reuses only the
successful responses from that invocation, and retries quota, schedule, or odds
provider failures up to three passes with a 65-second default delay.

The legacy shared cache remains available only through explicit
`--reuse-cache`. The CLI reports pass count, aggregate HTTP attempts/cache hits,
elapsed time, and stop reason. Every pass remains an immutable complete
15-disposition snapshot, and external probabilities remain audit-only.

The first live dry run of the new command on drawing 4945 finished in two
passes and 68.66 seconds. The final T-15 run resolved the target once at
17:45:01 MSK and finished its second pass at 17:46:09 MSK, 13 minutes 50
seconds before the 18:00 deadline. It completed in 69.04 seconds with 15 HTTP
attempts and ten cache hits across the invocation; the final pass produced
13/15 consensuses, two explicit missing-provider fallbacks, two reversed exact
matches, and zero ambiguous matches. The prospective gate remains `PENDING`
only because the sample is below 30 drawings and 450 events.

## Completed Task: Provider-Neutral Drawing Eligibility Classifier

Task 1 of the multi-day drawing eligibility plan is complete. The new
provider-neutral classifier validates immutable effective starts for all 15
ordered events, applies the inclusive `Europe/Moscow` calendar span, returns
fail-closed `playable`, `multi_day`, or `unknown` results with source counts,
and creates deterministic target fingerprints that exclude fetch time.
Constructor invariants cover status, span, missing orders, source counts, and
earliest/latest consistency. Focused verification passed with 20 eligibility
tests and Ruff. Progressive schedule expansion, persistence, audit/report
changes, and the playable timing gate remain future work under the approved
multi-day design below.

## Approved Next Design: Multi-Day Drawing Eligibility

Rare holiday and off-season drawings can span four or five days. The approved
follow-up preserves the normal two-day API request cost, progressively expands
missing-start searches through day five only when needed, isolates failures by
sport/date, and persists provider-derived effective start times. Playable mode
will require all 15 effective starts within an inclusive two-day Moscow
calendar span; `multi_day` and `unknown` are mandatory `NO BET`. Historical
TotoBrief collection and research output remain unchanged, and external
probabilities remain audit-only.

Design specification:
- `docs/superpowers/specs/2026-07-15-multiday-drawing-eligibility-design.md`

## Completed Task: Per-Date Schedule Collection and Provenance

Task 2 of the multi-day drawing eligibility plan now requests schedules one
sport/date at a time in deterministic order, covers the selected Moscow
calendar horizon with all required UTC dates, and isolates sanitized failures
by date. A schedule quota cutoff marks the current and remaining date outcomes
and prevents every subsequent market request, including for events matched by
earlier successful schedule responses.

Fresh immutable snapshots carry target fingerprints, horizon and per-date
schedule provenance, provider/effective start times, and Task 1 eligibility.
Those fields participate in equality, `asdict`, and full canonical identity.
Pre-Task-3 SQLite persistence keeps its explicit legacy projection because the
current schema has no columns for the new data; Task 3 must persist and reload
the full provenance before it can be considered a storage round trip.

Verification: Task 2 collection/storage/end-to-end/matching/consensus tests
passed (`61 passed`), full pytest passed (`696 passed`), and repository Ruff
passed. The external coverage CSV/Markdown frozen hashes were regenerated only
after two separate byte-deterministic integrity runs.

## Latest Completed Feature: Explicit Reversed Event Orientation

Matcher v3 accepts a reversed home/away provider pair only when it is the sole
exact same-or-reversed candidate under the existing sport, alias, schedule-date,
and known-time rules. It records `same` or `reversed` orientation, fails closed
when both orientations or duplicate candidates exist, and never promotes fuzzy
similarity suggestions.

For a reversed match, collection swaps only the consensus `1` and `2`
probabilities into TotoBrief orientation. Raw provider home/draw/away prices
remain unchanged. Orientation is bound into immutable collection identity,
persisted in SQLite with a legacy-row backfill, and exported in coverage CSV
and CLI diagnostics.

The live re-collection of drawing 4945 produced 13/15 external consensuses
(86.67%), two reversed exact matches, two explicit missing-provider fallbacks,
and zero ambiguous matches. The gate is `PENDING` solely because the prospective
sample is below 30 drawings and 450 events. External consensus still has no
`PLAY` impact.

## Latest Completed Fix: API-Sports Mixed-Market Parsing

Fixed the remaining final-review blocker where exact `Home`/`Draw`/`Away`
validation was incorrectly applied to every API-Sports bookmaker market. A
payload containing valid full-time football or regulation-time hockey `1/X/2`
alongside totals, double chance, or two-way moneyline no longer aborts the
event. Exact outcome validation now runs only after the market name matches the
existing semantic allow-list, without adding any eligible market names.

Unrelated markets remain provider-neutral records and consensus assessments.
They are ineligible, contribute no probabilities, and remain available to the
existing quote diagnostics/persistence path. Allow-listed candidates still
fail closed on duplicate, unknown, or missing `Home`/`Draw`/`Away` labels.
No EV/PLAY, category, bank, probability, consensus, or gate definition changed.

Verification completed with the mixed-market RED/GREEN regression, focused
external-odds pytest (`117 passed`), full pytest (`643 passed`), Ruff (`All
checks passed!`), and zero-exit CLI help smokes for `collect-external-odds`,
`audit-external-coverage`, and `ev-package`.

## Latest Completed Task: API-Sports Coverage Audit Final Review Fixes

Fixed all final whole-branch review findings for the API-Sports coverage audit.
Consensus now uses an explicit external observation clock that is at least as
late as all consumed provider market fetch timestamps, while the original
TotoBrief drawing-info fetch time remains stored as `target_fetched_at`.
Fresh markets fetched after the TotoBrief target snapshot remain eligible;
genuinely future and stale market updates still fail closed.

API-Sports parsing now supports official-shaped odds items whose `update` is
on the response item rather than each bookmaker, while preserving valid
bookmaker-level overrides. Football and hockey schedules/odds are fetched
deterministically across every reported page with explicit `page` queries;
invalid or inconsistent `paging.current`/`paging.total` fails closed. Market
outcome labels are validated before `ProviderMarket` construction: each market
must contain exactly one `Home`, `Draw`, and `Away`, with no duplicate or
unknown extra outcomes.

Request accounting now distinguishes actual HTTP attempts from cache hits and
logical fetch calls. Retries and additional pages increment actual requests;
cache hits are persisted and reported separately. Collection reports, CSV, and
Markdown expose actual request attempts, cache hits, quota counters, target
fetch provenance, provider schedule provenance, and market fetch/update/hash
provenance. EV/PLAY behavior, gate thresholds, exact 15-event fallback
behavior, consensus thresholds, and probability definitions are unchanged.

Verification completed with focused external-odds pytest (`115 passed`), full
pytest (`641 passed`), Ruff (`All checks passed!`), required CLI help smokes
for `collect-external-odds`, `audit-external-coverage`, and `ev-package`
(all exited zero), and `git diff --check` (zero).

## Latest Completed Task: API-Sports Coverage Audit End-to-End Acceptance

Task 7 of the API-Sports coverage audit is implemented. Added an end-to-end
acceptance suite that runs the open collection pipeline through target parsing,
provider matching, consensus/fallback disposition, append-only SQLite storage,
latest-complete loading, read-only coverage audit, deterministic report
publication, and CLI sanitization boundaries.

Acceptance covers mixed success/fallback collections, provider schedule
failure, quota exhaustion after five successful market events, interruption
rollback with no complete run published, deterministic report hashes and
ordered 15-event evidence, provider timestamps, quota counters, consensus gate
settings, and EV non-interference. The same suite proves the API key is absent
from stored SQLite text, API-Sports cache files, CLI output, exception chains,
coverage CSV, and coverage Markdown.

Review hardening now raises sanitized API-Sports transport and
`collect-external-odds` CLI exceptions outside the secret-bearing handler
context. Recursive acceptance walks both `__cause__` and `__context__` and
proves the key is absent from `str()` and `repr()` of every reachable exception.

Coverage CSV dispositions now export stored provider schedule fetch/hash and
aligned market fetch/update/hash provenance, requests made, daily limit and
remaining quota, and minute remaining quota. CSV and Markdown also disclose
the fixed three-bookmaker/36-hour collection consensus configuration and all
six ordered gate predicates with actual values, operators, thresholds, and
observed pass results. Exact acceptance hashes bind both report artifacts.
Collection, matching, consensus, gate, report, and EV probability
definitions are unchanged.

The implementation is complete, but the operational external-odds gate remains
`PENDING` until an operator prospectively collects at least 30 future drawings
and 450 events. External consensus still has no `PLAY` impact.

Verification completed with focused acceptance pytest (`6 passed`), full pytest
(`628 passed`), Ruff (`All checks passed!`), and the required CLI help smokes
for `collect-external-odds`, `audit-external-coverage`, and `ev-package`
(all exited zero).

## Previous Completed Task: Append-Only External Odds Storage and Collection

Task 5 of the API-Sports coverage audit is complete. Added append-only
SQLAlchemy tables for external collection runs, event dispositions, and
bookmaker quote provenance. `save_collection()` writes one complete immutable
15-event snapshot in a single transaction, is idempotent for identical canonical
content, and rejects conflicting content under the same deterministic
collection ID.

Added deterministic external odds orchestration that fetches required
sport/date schedules before any odds request, matches all 15 TotoBrief targets,
fetches odds once per unique matched provider event, builds strict consensus
where possible, and otherwise preserves the TotoBrief BK triplet with an
explicit event-level fallback reason. Unknown sports, missing/ambiguous matches,
provider failures, quota exhaustion, stale/partial market paths, and
minimum-bookmaker failures do not drop events. Run rows persist provider quota
and request counts; event and quote rows persist matching, probability source,
fallback, market eligibility, and rejection provenance.

`collect_open_external_odds()` now resolves the nearest open TotoBrief drawing,
fetches exactly that drawing-info snapshot, parses the 15-event target, builds
and saves the external collection only after all dispositions exist, and returns
the immutable snapshot. This remains audit-only and does not change playable EV
package decisions.

Verification completed with focused external-odds storage/collection tests
(`11 passed`), full pytest (`591 passed`), and Ruff (`All checks passed!`).

## Task 5 Review Hardening: Provenance and Canonical Quotes

Matched event dispositions now persist the provider schedule event payload hash
and fetch time together with candidate IDs and the match reason. Bookmaker quote
rows persist provider market payload hash and fetch time. The deterministic
collection ID explicitly binds those fields, the fresh TotoBrief target
timestamp, matching decisions, and consensus configuration; changing either
schedule-event or market provenance changes the immutable identity.

Quote records are sorted canonically before collection construction and
identity, append-only stored-content comparison, insertion, and load. Identical
provider content therefore remains equal and idempotent regardless of response
or assessment order.

Consensus continues to reject duplicate bookmaker/market assessments. Multiple
assessments with the exact database quote key are now coalesced into one
ineligible row with the explicit `duplicate bookmaker market` reason, source
count, deterministic aggregate hash, and canonical source provenance retaining
every source hash, fetch/update time, and price triplet. The mandated unique key
is unchanged, and the anomaly no longer aborts the one-transaction 15-event
snapshot.

Review-fix verification: focused external storage/collection tests (`14
passed`), full pytest (`594 passed`), and repository-wide Ruff (`All checks
passed!`).

## Previous Completed Task: Strict Market Semantics and Consensus

Added `toto_ai.external_odds.consensus` for Task 4 of the API-Sports coverage
audit. The new module accepts only explicit full-time football `1/X/2` market
names and explicit regulation-time hockey `1/X/2` market names from small
allow-lists. It rejects unknown market names, missing outcomes, prices `<= 1`,
future timestamps, stale prices older than 36 hours, and duplicate bookmaker
records for the same accepted market semantics.

Eligible bookmaker prices are de-vigged multiplicatively per book, then the
component-wise median probabilities are renormalized into one provider-neutral
consensus triplet. Consensus requires at least three eligible bookmakers;
otherwise the result is an explicit fallback with per-book rejection reasons.
This prospective consensus remains an audit-only input and does not change
playable package decisions.

Task 4 verification completed with focused consensus tests, full pytest
(`578 passed`), and Ruff (`All checks passed!`).

## Task 4 Review Coverage

Added a deliberately asymmetric overround regression that proves each
bookmaker is de-vigged before component-wise medians are calculated. A
raw-inverse-median mutation produces a detectably different consensus and is
rejected by the test. Added positive coverage for an allow-listed hockey
regulation-time three-way market producing a three-bookmaker consensus. No
production behavior or probability definition changed.

Review verification completed with focused consensus tests (`10 passed`), full
pytest (`580 passed`), and Ruff (`All checks passed!`).

## Latest Completed Task: Deterministic External Event Matching

Added `toto_ai.external_odds.matching` for Task 3 of the API-Sports coverage
audit. Exact matching is fail-closed and accepts only a single candidate with
the same sport, the same home/away orientation, both team names matched after
Unicode normalization and reviewed alias resolution, and a UTC start-time
difference no greater than three hours. Target-side exact names may come from
the primary TotoBrief team names or the optional `name_en` alternatives.

Added `data/external-odds/team-aliases.json` as the versioned reviewed-alias
source. `load_aliases()` now enforces the exact schema, normalizes keys and
values deterministically, rejects normalized-key and normalized canonical-value
collisions, and rejects alias cycles before a mapping can be used.
`suggest_matches()` uses fuzzy similarity only after sport/time filtering,
returns at most five diagnostics in deterministic score/ID order, and cannot
authorize a match.

Task 3 verification completed with focused matcher tests, full pytest
(`570 passed`), and Ruff (`All checks passed!`).

## Latest Completed Task: API-Sports Transport, Parsing, Cache, and Quota

Added `toto_ai.external_odds.api_sports.APISportsClient` for the approved
coverage audit with separate football and hockey hosts, injected
`requests.Session`, sanitized API-key-only header authentication, deterministic
SHA-256 cache files, quota tracking from response headers, bounded retry for
connection failures and HTTP `408/429/5xx`, and fail-closed sanitized
`APISportsError` / `QuotaExhausted` exceptions.

The adapter now parses football fixture responses and hockey game responses
into provider-neutral `ProviderEvent` records, parses bookmaker odds snapshots
into `ProviderMarket` records without deciding semantic eligibility, and
rejects invalid top-level provider errors, paging, timestamps, prices, and
identifier shapes. Repository tests remain synthetic and deterministic with no
live network dependency, and raw external cache files are ignored by Git.

Recovery hardening added focused regressions for hockey `/games` schedules,
hockey odds `game` queries, rejection of football fixture-shaped hockey
payloads, sanitized non-retry HTTP failures, finite timestamp validation, and
provider-owned price validation before domain object construction.

Review hardening now applies quota headers from every HTTP response before
retry or failure handling and rechecks the reserve before a retry. Cache reads
strictly validate the stored envelope, quota fields, and top-level provider
payload and fail closed with sanitized errors instead of consuming malformed
or partial files. Cache writes use same-directory temporary files plus atomic
replacement, clean up failed temporary writes, and retain no secret-bearing
low-level exception context.

## Approved Next Design: Expected-Value Package Engine

The sealed BK-only hybrid experiment is final with `STOP`. The next direction
does not continue tuning hit-count heuristics. It ranks the complete
`3^15 = 14,348,907` coupon space by modeled monetary expected value.

Approved requirements:

- dynamic bank: any positive multiple of the configurable stake;
- no candidate truncation for speed;
- official cumulative BaltBet category allocation model;
- explicit prize-fund proxy/override and sensitivity reporting;
- explicit independent crowd-ticket model from pool marginals;
- Research mode that always shows top coupons;
- Playable mode with configurable EV threshold and honest `NO BET`;
- no automatic threshold reduction to force bank utilization;
- provider-neutral external probabilities with event-level TotoBrief BK
  fallback; direct Pinnacle scraping is excluded;
- modeled ROI is not profitability evidence without prospective payout data.

Design specification:
- `docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md`

Approved implementation plan:
- `docs/superpowers/plans/2026-07-14-expected-value-package-engine.md`
- Seven TDD tasks: domain/prize math, brute-force oracle, exact ternary engine,
  dynamic-bank selection, fresh drawing CLI/reports, chronological modeled-EV
  backtest, and full-space acceptance.

Next action:
- execute the implementation plan task by task with independent review gates.

## Latest Completed Task: External Odds Domain and TotoBrief Targets

Added the provider-neutral `toto_ai.external_odds` package for the approved
API-Sports coverage audit. The new domain layer defines immutable
`TargetDrawing`, `TargetEvent`, `ProviderEvent`, `ProviderMarket`,
`QuotaState`, and `ExternalOddsProvider` records with strict validation for
UTC-aware datetimes, event order, required identifiers, TotoBrief BK
probability triplets, and optional decimal prices.

Added `parse_target_drawing()` to convert a fresh TotoBrief `drawing-info`
payload into a strict 15-event fallback target set and `classify_sport()` to
honor explicit football/hockey values, detect hockey championship tokens, and
default every other non-empty championship to football. Only an empty
championship classifies as unknown. Target parsing sorts TotoBrief events by
order, splits localized and optional English team names, and preserves normalized
BK probabilities for later fallback provenance.

Task 1 verification completed with focused `external_odds` tests, full pytest,
and Ruff. The added regression accepts any zero-offset UTC-aware datetimes in
the provider-neutral domain instead of requiring the `timezone.utc` singleton.

## Active Design: Hybrid Direct Package Experiment

Approved design:
- Preserve an exact top-probability core of 50%, 75%, or 90% of the package.
- Fill remaining capacity by marginal weighted coverage after accounting for
  scenarios already covered by the core.
- Evaluate only the 350 frozen development drawings in five chronological
  folds; never reopen the old holdout for selection.
- Return GO only for at least two additional 13+ hits, non-loss in at least
  four folds, no lower average best hits, and zero operational failures.
- Return STOP and end optimizer tuning when no candidate passes.

Design specification:
- `docs/superpowers/specs/2026-07-13-hybrid-direct-package-experiment-design.md`

Implementation plan:
- `docs/superpowers/plans/2026-07-13-hybrid-direct-package-experiment.md`
- Five TDD tasks: selector, decision model, fail-closed evaluator, atomic
  reports/CLI, and the frozen development GO/STOP run. Tasks 1-5 are complete.

## Latest Review Fix: Hybrid Development Seal

Added `seal-hybrid-development` to derive a development-only CSV and augmented
manifest from the frozen manifest, the bounded development prefix of the full
backtest CSV, and a read-only SQLite database. The deterministic seal stores
separate SHA-256 hashes for canonical development CSV rows, pre-drawing inputs,
development results, and the fixed hybrid protocol. The seal also records the
clean Git code version. Input/output path collisions are rejected before any
source is loaded, and the manifest/CSV pair is published with rollback-safe
same-directory temporary files.

`evaluate-hybrid` now requires these sealed artifacts. It rejects missing or
mismatched CSV, protocol, and pre-drawing input hashes before result access,
rejects any non-development CSV drawing ID, accumulates result hashes only
after each drawing's top package hash passes, and verifies the final result hash
before summary, decision, or report return. Strategy definitions, fractions,
folds, bank, stake, category, and GO/STOP criteria are unchanged.

The shared package-generation deadline is now checked after every major stage,
including top enumeration, candidate generation, both scenario samples, hybrid
selection, and validation coverage. A timed-out selector returns without a
post-deadline exact coverage pass. Deadline overruns therefore fail closed
instead of being reported as successful zero-timeout drawings.

Both sealing and evaluation reject resolved input/output path collisions before
loading inputs or opening the database, so generated seal/report artifacts
cannot replace a manifest, development CSV, or database.

## Latest Completed Task: Sealed Frozen Hybrid Development Experiment

The approved hybrid direct-package experiment completed on all 350 frozen
development drawings without accessing the 150-drawing holdout during
selection. The final run used the development-only data/code seal at Git
revision `530e1021328bb8436671a273e9ab96b4be03ac06`.

Protocol:
- Bank 5000 RUB, stake 30 RUB, category 13.
- Five chronological development folds of 70 drawings each.
- Compared `top_probability` with hybrid top-core fractions 0.50, 0.75, and
  0.90.
- All four strategies produced 166-coupon packages costing 4980 RUB.
- Operational failures and timeouts: 0.

Development results:
- `top_probability`: 13+ 6, 14+ 1, 15 0, average best hits 8.691429.
- `hybrid_0.50`: 13+ 4, 14+ 1, 15 0, average best hits 9.491429.
- `hybrid_0.75`: 13+ 5, 14+ 1, 15 0, average best hits 9.288571.
- `hybrid_0.90`: 13+ 6, 14+ 1, 15 0, average best hits 9.060000.

Per-fold 13+ counts in strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, `hybrid_0.90`:
- Fold 1: 0, 0, 0, 0.
- Fold 2: 0, 0, 0, 0.
- Fold 3: 1, 0, 0, 1.
- Fold 4: 1, 1, 1, 1.
- Fold 5: 4, 3, 4, 4.

GO predicates by hybrid core fraction:
- 0.50: additional 13+ -2, non-losing folds 3, average best-hit delta
  +0.800000, operational failures 0; fail.
- 0.75: additional 13+ -1, non-losing folds 4, average best-hit delta
  +0.597143, operational failures 0; fail.
- 0.90: additional 13+ 0, non-losing folds 5, average best-hit delta
  +0.368571, operational failures 0; fail.

Final decision: `STOP`.

No hybrid fraction met every pre-registered GO predicate. All hybrids improved
average best hits, but none produced the required two additional 13+ hits over
`top_probability`. Direct optimizer tuning is closed under the current
BK-only protocol. The old holdout remains excluded and unopened for hybrid
selection. This development-only result is not profitability evidence.

The final sealed rerun completed in approximately 25 minutes and exactly
reproduced the original strategy hit counts, fold counts, average best-hit
metrics, and STOP decision. It processed 1400 evaluation rows with zero
timeouts, exactly 350 development IDs, and zero holdout-ID overlap. This
result remains evidence for the sealed evaluator revision above; subsequent
documentation-only commits do not alter or rerun the experiment.

Reports:
- `reports/hybrid_evaluation_development_last_500_bank_5000.csv`
- `reports/hybrid_evaluation_development_last_500_bank_5000.md`
- `reports/hybrid_development_manifest_last_500.json`
- `reports/hybrid_development_rows_last_500.csv`

The CSV was independently checked: 1400 rows, 350 rows per strategy, and 280
rows per fold.

## Completed Task: Hybrid Evaluation Reports and CLI

Added `write_hybrid_evaluation_reports()` and the fixed `evaluate-hybrid`
command for the approved hybrid experiment. CSV rows use manifest drawing order
and the stable strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, and `hybrid_0.90`. CSV and Markdown are fully rendered in
same-directory temporary files and closed before either final report is
replaced. Existing final reports are copied to same-directory backups before
publication. If either final replacement fails, both previous reports are
restored byte-for-byte, or both newly published reports are removed when no
previous pair existed; all temporary and backup files are then removed.

The Markdown report records the frozen configuration, five development folds,
total and structural metrics, operational failures, every GO predicate, and
the exact GO/STOP decision. It explicitly labels the result development-only
and as no profitability evidence. Generated reports are ignored by Git.

`evaluate-hybrid` accepts only the database, manifest, frozen backtest CSV, and
report directory paths. It uses `open_readonly_db()` and Rich progress, does
not initialize or migrate the database, and converts controlled failures to
`typer.BadParameter`, including `SQLAlchemyError` database failures.

No evaluation run has been interpreted as profitability evidence. The frozen
holdout remains excluded from hybrid selection.

The worktree CLI help shows only the four path options. Current test and Ruff
verification is recorded once above.

## Latest Completed Task: Development Strategy Diagnostics

Added the fail-closed `diagnose-strategies` command and completed the frozen
development-only diagnostic for the Direct Package Optimizer experiment.
The command opens the existing SQLite database in enforced read-only mode and
cannot create tables or run migrations.

Command:
- `python -m toto_ai.cli diagnose-strategies --db data/toto.db --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv`

Run evidence:
- 350 development drawings processed; the 150 holdout drawings were excluded.
- All regenerated package hashes and recomputed frozen result fields matched.
- Bank 5000 RUB, stake 30 RUB, category 13.
- Weighted vs top best hits: 260 wins, 74 ties, 16 losses.
- Weighted minus top best hits: mean +1.394, median +1.
- Paired 13+ transitions: neither 343, both 3, top-only 3,
  weighted-only 1.
- Average best hits: baseline 8.380, top 8.691, weighted 10.086.
- Observed 13+ frequency: baseline 0.286%, top 1.714%, weighted 1.143%.
- Top vs weighted mean pairwise Hamming distance: 3.491 vs 7.496.
- Top vs weighted mean coupon log probability: -13.682 vs -14.729.
- Average top/weighted package intersection: 11.36 coupons; average Jaccard
  overlap 0.0356.

Interpretation:
- Weighted coverage usually improves the nearest coupon, but its much broader
  and lower-probability package does not improve the observed 13+ threshold.
- No strategy was selected. These are development-only diagnostic findings,
  not holdout evidence and not evidence of profitability.
- The next optimizer experiment should test a development-selected hybrid that
  preserves a high-probability core or probability floor while adding measured
  diversity. It must use a new untouched evaluation window.

Reports:
- `reports/strategy_diagnostics_development_last_500_bank_5000.csv`
- `reports/strategy_diagnostics_development_last_500_bank_5000.md`

Important commits:
- `ec97679` Add development strategy diagnostics command

## Completed Task: Hybrid Package Selector

Added `select_hybrid_package()` for the approved direct-package experiment.
It keeps an exact, unique top-probability core sized with `ceil`, fills only
core-uncovered sampled scenarios through the existing weighted selector, and
uses a deterministic unique probability fallback when time remains. Timeout
paths return only work completed so far. Existing top-probability and weighted
coverage behavior remains unchanged.

Verification at completion: pytest and Ruff passed.

Review follow-up: the hybrid probability fallback now checks the deadline before
each coupon log-probability ranking computation, after sorting, and while
appending. On expiry it returns the unique partial package with `timed_out=True`.
Verification at completion: pytest and Ruff passed.

## Completed Task: Hybrid Fold Metrics and GO/STOP Decision Model

Added the pure `hybrid_evaluation` model for the approved hybrid experiment.
It defines immutable evaluation rows/results, assigns exactly five contiguous
chronological folds, aggregates stable top and hybrid fold metrics, and applies
the fixed GO predicate and deterministic fraction ranking. A STOP selects no
core fraction. This task does not load the database, generate reports, or add
CLI behavior.

Review follow-up: `summarize_hybrid_evaluation()` now fail-closes before
aggregation on invalid folds, duplicate or unpaired rows, unequal or empty
folds, non-chronological fold assignments, and mismatched strategy fractions.
Verification at completion: pytest and Ruff passed.

## Completed Task: Fail-Closed Hybrid Development Evaluator

Added `run_hybrid_evaluation()` for the approved fixed-protocol hybrid
experiment. It validates the 5000 RUB / 30 RUB / category 13 configuration and
five equal development folds before database access, then evaluates only the
manifest development IDs. Per drawing it regenerates and validates the exact
top package plus all three hybrids, reuses candidate and scenario inputs across
fractions, verifies the frozen top hash before loading a result, recomputes the
frozen top fields, and produces four scored rows for the GO/STOP model.

The evaluator fails closed on duplicate/non-divisible development manifests,
protocol mismatches, malformed/incomplete/over-budget/timed-out packages,
frozen hash/result mismatches, and invalid package strategy identities. It does
not add reports or CLI wiring, and never loads the frozen holdout during
selection.

Review follow-up: integrity-boundary coverage now tags every development drawing,
captures real result-bearing Event SQL, and proves a later top-hash mismatch
stops before that drawing's result load or any holdout access.

Verification at completion: focused and full pytest suites plus Ruff passed.

## Previous Completed Task: Package Structure Metrics

Added deterministic package diagnostics for coupon log-probability summaries,
pairwise Hamming diversity, package intersection, Jaccard overlap, and mean
log probability of coupons unique to each package. Empty unique coupon sets
are represented as unavailable (`None`).

## Latest Completed Task: Direct Package Optimizer Experiment

Implemented the approved Direct Package Optimizer and its reproducible
evaluation protocol.

Important commits:
- `e5c4823` Add coupon probability utilities
- `c760515` Add deterministic coupon candidates
- `fd71046` Add weighted direct package optimizer
- `c82b135` Add comparable package strategies
- `4cc8987` Add direct strategy backtest
- `baefa34` Add paired strategy evaluation reports
- `e5b4953` Add frozen direct package experiment
- `5beaeae` Ignore generated strategy experiment reports

Frozen retrospective experiment:
- Code version: `5beaeae4d7801748e82a4ae9a0003be4e0796d81`
- Manifest: `reports/strategy_experiment_manifest_last_500_exclude_10.json`
- 500 eligible drawings, 350 development and 150 holdout
- Latest 10 previously exposed drawings excluded
- Bank 5000 RUB, stake 30 RUB, category 13, seed 42
- 500/500 drawings evaluated; no skips, generation errors, invalid packages,
  or timeouts

Holdout results:
- `baseline_brief`: hit13 2, hit14 1, hit15 0, average best hits 8.59,
  average cost 663 RUB
- `top_probability`: hit13 6, hit14 1, hit15 0, average best hits 8.86,
  average cost 4980 RUB
- `weighted_coverage`: hit13 5, hit14 0, hit15 0, average best hits 10.23,
  average cost 4980 RUB
- Paired weighted-vs-baseline hit13 difference: +2.00 percentage points
- 95% paired bootstrap interval: [-0.6667, 5.3333]
- Status: preliminary; the interval includes zero

Interpretation:
- Direct strategies outperform the low-cost baseline on raw holdout hit13
  counts, but superiority is not statistically established.
- `top_probability` currently has the highest holdout hit13 count.
- `weighted_coverage` has substantially higher average best hits, but that
  improvement has not yet converted into more 13+ hits.
- This is a retrospective benchmark, not independent prospective evidence and
  not evidence of profitability.

## Exact Cover Example

- 144 full brief variants
- 8 coupons
- Category 13
- 100% exact verified coverage
- Worst minimum Hamming distance 2

## Previous Completed Task

Fixed unsafe Budget Oracle pruning.

- Disabled dominance pruning because it changed oracle best-hit metrics.
- Disabled pruning based on full-cover coupon-cost bounds because Budget Oracle
  evaluates useful partial packages under budget.
- Restricted incumbent pruning to candidates whose maximum possible hit count
  is strictly below the incumbent's actual hit count.
- Added regression coverage comparing optimized and exhaustive selection.
- Removed the unused unsafe pruning helpers.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 3 --bank 10000 --stake 30 --category 13 --no-progress --profile-workload`
  found 15 hits for all three processed drawings.
- All pruning counters were zero; two drawings reached the configured timeout,
  so these rows are partial oracle evidence rather than exhaustive optima.

## Previous Completed Task

Profiled Budget Oracle candidate workload.

The `budget-oracle` command now supports:
- `--profile-workload` to print aggregate candidate workload diagnostics.
- Per-drawing generated candidate count.
- Per-drawing unique candidate count.
- Cover Engine call count.
- Cache hit/miss counts, where duplicate candidate briefs avoided by
  deduplication are counted as hits and actual Cover Engine evaluations are
  counted as misses.
- Average and maximum brief variant counts.
- Average Cover Engine call duration.
- Slowest 10 candidate briefs across the run.

This does not change oracle search logic, candidate scoring, or default search
space.

## Previous Completed Task

Optimized Cover Engine performance without changing mathematical results.

The Cover Engine now:
- Caches expanded brief variants.
- Caches coverage bitsets by `(brief, category)`.
- Builds coverage via bounded outcome mutation instead of rebuilding all
  coupon/variant Hamming comparisons.
- Uses integer bitsets for greedy uncovered coverage tracking.
- Keeps the same selected coupons, coverage rate, worst minimum distance, and
  guarantee result on the representative regression case.

Benchmark evidence:
- Pre-optimization representative cover runtime: about 1.70s for 1024 variants.
- Post-optimization representative cover runtime: about 0.04-0.05s.
- Speedup: about 35x on the representative benchmark.
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --no-progress`
  completed in about 0.5 seconds without `--max-candidates`.

New command:
- `python -m toto_ai.cli benchmark-cover`

## Previous Completed Task

Improved Budget-Constrained Brief Oracle observability and diagnostics.

The `budget-oracle` command now supports:
- Rich progress updates with drawing number, drawing index, candidate index,
  elapsed time, average drawing time, ETA, current best hits/cost, and
  processed/skipped/timed-out counts.
- `--timeout-per-drawing` to keep the best candidate found so far and mark the
  row as timed out.
- `--max-candidates` as an explicit optional candidate limit. Omitted means full
  search.
- `--progress/--no-progress`.
- Partial CSV writes every 10 drawings.
- Per-drawing profiling timings for candidate generation, cover generation,
  verification, and total time.
- Final timing summary.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --max-candidates 3 --no-progress`
  completed in about 5 seconds.

## Earlier Completed Task: Budget-Constrained Brief Oracle

Implemented Budget-Constrained Brief Oracle.

The `budget-oracle` command uses actual results only as an oracle benchmark. It
searches BK-ranked candidate briefs that include the actual outcome, runs the
Cover Engine under the same budget/stake/category constraints, and compares the
best oracle package hits against the baseline brief generator.

Command:
- `python -m toto_ai.cli budget-oracle --db data/toto.db --last 500 --bank 10000 --stake 30 --category 13`

Exports:
- `reports/budget_oracle_last_<N>.csv`
- `reports/budget_oracle_last_<N>.md`

Metrics:
- Oracle average best hits
- Oracle hit13/hit14/hit15
- Average singles, doubles, triples
- Average oracle package size and cost
- Baseline generator average best hits
- Oracle vs baseline gap

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13` completed in
  about 9 seconds.

## Earlier Completed Task: Project Knowledge Base

Created the persistent project knowledge base.

New repository-local project knowledge areas:
- `memory-bank/`: current state, roadmap, architecture, philosophy, decisions.
- `knowledge/`: concise domain notes for TotoBrief, bookmaker calibration,
  crowd bias, closing line, and Pinnacle integration status.
- `skills/`: project-local workflow checklists for algorithm review, research,
  and backtesting.
- `prompts/`: reusable project prompt templates for feature, research, and
  backtest tasks.

The project rule is now explicit: after every completed feature, update the
project knowledge base first.

## Earlier Completed Task: Brief Oracle Research

Implemented Brief Oracle Research.

The `brief-oracle` command finds the smallest oracle brief that contains the
actual 15-outcome result for completed drawings using BK probabilities only.

Exports:
- `reports/brief_oracle.csv`
- `reports/brief_oracle.md`
- `reports/brief_oracle_by_event.csv`

Per drawing it records:
- singles, doubles, triples
- full brief variant count
- log brief probability
- actual result string
- oracle brief string
- BK rank counts for actual outcomes
- average BK rank and actual-result BK probability
- pool/BK top disagreement diagnostics

Aggregate metrics include:
- average singles, doubles, triples
- p25/p50/p75/p90 full variant counts
- doubles and triples distributions
- BK rank frequency for actual outcomes
- entropy by required cover size

## Earlier Completed Task

Implemented bookmaker calibration research.

The `calibration` command measures:
- Bookmaker reliability by 5 percentage-point bins for outcomes 1/X/2
- Pool reliability by the same bins
- Overall Brier score
- Log loss
- Expected Calibration Error
- Pool vs bookmaker bias
- Draw calibration
- Favorite calibration for BK >= 60%
- Underdog calibration for BK <= 25%

Exports:
- `reports/calibration.md`
- `reports/calibration.csv`
- `reports/reliability.csv`

## Earlier Completed Task: Backtest Optimization

Optimized the Baseline Brief Generator backtest.

The `backtest-brief` command now includes:
- Rich progress for drawing number, candidate index, elapsed time, and best
  score.
- Cover Engine cache keyed by brief tuple, category, and max coupon count.
- Candidate brief deduplication.
- Cheap candidate scoring before exact cover.
- Exact cover/verifier only for top candidates.
- Per-drawing timeout fallback.
- Per-drawing timing metrics.
- `--top-candidates`, `--max-candidate-briefs`, and
  `--timeout-per-drawing` options.

Exports:
- `reports/backtest_brief_last_<N>.csv`
- `reports/backtest_brief_last_<N>.md`

Local smoke results on `data/toto.db`:
- `backtest-brief --last 1 --bank 10000 --stake 30 --category 13` completed
  in about 4.7 seconds.
- `backtest-brief --last 10 --bank 10000 --stake 30 --category 13` showed
  progress and completed in about 41 seconds, testing 9 drawings with one
  skipped due to missing pre-match BK/pool probabilities.

## Latest Completed Task: Expected-Value Domain Math

Task 1 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev` package exposes immutable `EVConfig`, `EVInput`, `EVComponents`,
`EVSurface`, `RankedCoupon`, and `EVPackage` models, plus bank validation,
official cumulative category-fund allocation, triplet normalization, and
Jeffreys-smoothed crowd marginals. `EVConfig` validates positive integer banks
and stakes, including divisibility, during construction; its
`max_coupons` result is always an integer without forcing full bank
utilization. `EVComponents` and `EVSurface` defensively copy and freeze their
NumPy arrays. The exported `CROWD_JOINT_MODEL` contract is
`independent_event_marginals`: later joint coupon probabilities are modeled as
products of the smoothed event marginals.

## Latest Task 1 Fix Wave: Hardened EV Immutability

The second Task 1 fix wave enforces the same positive-integer stake contract in
`smooth_crowd_matrix()` as `validate_bank()`, including rejection of booleans,
floats, zero, and negative values. `EVInput` now deep-normalizes probability
matrices and probability sources to tuples and rejects probability rows that do
not contain three outcomes. `EVPackage` deep-normalizes coupons and derived
brief values to tuples. EV arrays are defensive copies exposed through owned
immutable byte buffers, so their shapes and dtypes are preserved and callers
cannot re-enable writes with `setflags(write=True)`.

Verification for this fix wave: focused EV tests `48 passed`, full pytest
`336 passed`, focused Ruff passed, and full Ruff passed. NumPy remains
intentionally undeclared in `pyproject.toml` until Task 3.

## Latest Completed Task: Independent Brute-Force EV Oracle

Task 2 of the Expected-Value Package Engine is complete. The reference oracle
enumerates actual results and coupons with `itertools.product(range(3),
repeat=event_count)`, preserving deterministic C-order base-three indexing.
It exposes independent joint distributions, Hamming hit counts, crowd
qualifying stakes, coupon payouts, and exhaustive gross EV for event counts up
to eight. Zero-valued outcome probabilities are accepted when the modeled
category denominators remain finite and positive; invalid category denominators
fail closed before payout division.

Verification: focused reference tests `11 passed`; full pytest `347 passed`;
focused Ruff passed; full Ruff passed.

## Latest Task 2 Review Fix: Hardened Reference Validation

The brute-force EV reference now requires every probability row to contain
exactly three finite non-negative values whose sum is one within
`rtol=1e-12` and `atol=1e-12`, while preserving valid zero probabilities.
`coupon_payout()` validates category ranges against the event hit count,
non-negative finite category funds, positive finite qualifying stakes for
every funded category, and strict positive integer stakes. Brute-force EV
rejects out-of-range categories before enumeration, and all public integer
contracts reject booleans.

Verification: focused reference tests `36 passed`; full pytest `372 passed`;
focused Ruff passed; full Ruff passed.

## Latest Completed Task: Exact Ternary Full-Space EV Engine

Task 3 of the Expected-Value Package Engine is complete. Flat arrays and coupon
strings preserve C-order base-three indexing with outcome order `1`, `X`, `2`.
The exact engine builds product probability arrays with repeated Kronecker
products. It computes each crowd qualifying probability over every actual-result
state with a chunked independent-marginal Poisson-binomial DP, then processes
the coupon-side Hamming-ball category sequentially through ternary FFT
convolution. Category denominators must remain finite and positive, and an
interruption propagates without returning a partial EV surface.

`compute_ev_components(EVInput, progress_callback=None)` uses only the official
9..15 regular-prize and jackpot coefficients and returns separate immutable
unit arrays so prize sensitivity can reuse the heavy calculation.
`materialize_ev_surface()` performs the light regular-prize/jackpot scaling.
For small-space oracle work, the explicit convenience signature is
`compute_ev_surface(true_probabilities, crowd_probabilities, pool_sum,
category_funds_by_hits, stake, minimum_category, progress_callback=None)`;
this preserves arbitrary category-fund mappings rather than weakening oracle
equivalence.

The deterministic `benchmark-ev` command records elapsed time, peak resident
memory when available, probability masses, minimum denominator, exact error,
fixed sample diagnostics, and normalized SHA-256 array hashes. Event counts up
to eight compare the complete surface to the independent brute-force oracle;
larger spaces independently verify sampled crowd tails with scalar
Poisson-binomial arithmetic and fixed coupon EVs with direct vectorized hit
comparisons over every actual-result state. Official benchmark expectations are
literal and do not share the production category-fund map. Array hashes are
diagnostic fingerprints only and do not affect PASS/FAIL.

Verification: focused Task 3 tests `35 passed`; full pytest `407 passed`; focused
and full Ruff passed. The five-event CLI benchmark verified all 243 coupons
against the oracle with maximum absolute error `1.897e-19` and status `PASS`.
The mandatory 15-event acceptance benchmark remains deferred to Task 7 and was
not run for Task 3.

## Latest Task 3 Mathematical Review Fix

Removed the absolute FFT cutoff that could erase legitimate positive values.
`ternary_convolve()` now copies the real inverse result away from its complex
buffer, preserves every positive value, clips only negative values within a
scale-aware roundoff tolerance, and raises on material negative output.

Crowd category denominators no longer use FFT recovery. For each category, a
bounded-memory Poisson-binomial DP evaluates `P(matches >= k | actual result)`
for all `3^n` actual-result states without state truncation. Regressions cover
all-positive five-event full spaces and a selected 15-event state with
`(0.999998, 0.000001, 0.000001)` marginals; the latter remains positive at
approximately `1e-90` without allocating the full 15-event state space.

The larger-space benchmark verifier no longer reuses production denominators,
Hamming kernels, or coupon convolution. It compares sampled production tails
to a scalar independent recurrence and recomputes sampled coupon components by
direct vectorized hit comparisons over every actual-result state in chunks.

Verification for this fix: focused Task 3 tests `45 passed`; full pytest
`417 passed`; focused and full Ruff passed. `benchmark-ev --events 5 --samples
10` verified all 243 coupons against the brute-force oracle in `0.116300 s`,
with `62.84 MiB` peak resident memory, minimum denominator `1828.14404892`,
maximum EV error `1.626e-19`, zero sampled crowd-tail error, and status `PASS`.
The full 15-event benchmark was not run, as instructed; its runtime and peak
memory remain Task 7 acceptance concerns.

## Final Task 3 Formula Fix: Exact Crowd Mass Handling

The production accumulation now materializes both C-order Kronecker product
arrays `Q` and `R`. It validates finite unit mass from `R.sum()` within `1e-12`,
records that value as `crowd_mass`, and releases `R` before category work. The
Poisson-binomial denominator DP remains the only denominator path and does not
consume or truncate `R` states.

For tolerance-accepted rows that are not bit-exact unit mass, production and
both independent benchmark recurrences now compute non-match probability from
the supplied row (`row_sum - selected match`) rather than `1 - selected
match`. This preserves the accepted row mass and agrees with the independent
brute-force joint reference. Regressions cover production tails, scalar tails,
direct coupon sums, full EV surfaces, C-order `R` auditing/release, and existing
tiny-positive behavior.

Verification: focused Task 3 tests `48 passed`; full pytest `420 passed`.
The five-event benchmark (`243` coupons) passed in `0.121526 s` with `62.00
MiB` peak resident memory, maximum EV error `1.626e-19`, and zero sampled
crowd-tail error. The 15-event benchmark was not run.

## Latest Completed Task: Dynamic-Bank EV Package Selection

Task 4 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.package` module ranks every validated `3**event_count` EV value
with a complete deterministic NumPy order: descending gross EV, then ascending
base-three coupon index for values tied under `rtol=1e-12` and `atol=1e-15`.
It does not truncate candidates or create a Python object per coupon; only the
selected package rows become `RankedCoupon` values.

Research mode fills the dynamic bank capacity even where gross EV is below one
and labels the result `RESEARCH ONLY`. Playable mode selects only coupons at or
above its configured threshold, can leave bank unused, and returns `NO BET`
with zero cost when none qualify. Packages report cost, unused bank, expected
payout, modeled ROI, and an outcome-union brief in `1`, `X`, `2` order.
Modeled ROI remains a model output, not evidence of profitability.

Verification: focused package tests `19 passed`; full pytest `439 passed`;
focused and repository-wide Ruff passed. Playable threshold tests cover
0.90/0.95/1.00/1.05 with monotonic selected-count assertions.

## Task 4 Review Hardening: Full-Surface Ranking

The full-surface ranker now handles every accepted real numeric dtype without
negating unsigned arrays. It creates one complete ascending index order with
NumPy quicksort, reverses that order in bounded chunks, and then scans adjacent
EV values in fixed-size chunks. Only actual tolerance-tie candidate blocks are
processed; common no-tie surfaces do not enter Python once per coupon. Each
candidate block is split by the specified run-first `rtol=1e-12`,
`atol=1e-15` rule and its tie runs are sorted in place by base-three index.

Regressions cover unsigned zero ordering, non-transitive adjacent-close chains,
candidate blocks crossing scan chunks, no singleton candidate processing, and
complete-order `RankedCoupon.rank` values when threshold filtering skips an
earlier tolerance-tied coupon.

Verification: focused package tests `24 passed`; full pytest `444 passed`;
repository-wide Ruff passed. Synthetic no-tie `uint32` and all-tie `uint8`
surfaces both ranked all `3**15 = 14,348,907` indices exactly. The combined
process completed in `1.00 s`; `/usr/bin/time -l` reported a `229,786,488`-byte
peak memory footprint and `433,176,576`-byte maximum resident set size while
running both surfaces sequentially.

## Latest Completed Task: Fresh Drawing EV Package Command

Task 5 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.drawing` path resolves only page one of the live TotoBrief API,
chooses the nearest future `active`/`expected` drawing by `(ended_at, id)`, and
immediately fetches `drawing-info`. It never falls back to SQLite. The fresh
receipt timestamp is recorded in UTC.

Drawing parsing requires exactly event orders 0 through 14, normalizes every BK
triplet, applies the approved Jeffreys smoothing to every pool triplet, and
fails closed on missing or invalid pool, jackpot, quote, and possible-winnings
inputs. Possible winnings are either an explicit override with the default
factor or the disclosed `pool_sum * prize_fund_factor` proxy. Event results are
not consumed.

`build_open_ev_package()` computes the complete reusable category components
once, materializes and selects the 0.70/0.80/0.90/1.00 sensitivity surfaces,
and reuses the configured factor's package where applicable. No probability or
coupon candidate space is truncated. Package cost divided by `pool_sum` is the
self-dilution ratio: exactly 1% remains supported; above 1% is unsupported.
Unsupported Playable output suppresses `PLAY` to `NO BET`, while Research output
retains diagnostics and an explicit warning.

The new rollback-safe report publisher fully renders deterministic exact-package
CSV and Markdown artifacts before publication and restores both prior files if
the second final replacement fails. Reports disclose fresh timestamps, sources,
the independent-event crowd model, prize factor, bank and self-dilution ratios,
decision, package metrics, derived brief, top-20 diagnostics, sensitivity, and
that modeled ROI is not observed ROI.

`ev-package` requires `--open`, accepts the exact planned mode, bank, stake,
threshold, prize-factor, possible-winnings, and jackpot options, and uses Rich
phase/category progress. API, validation, numerical, interruption, and report
failures become controlled `BadParameter` errors. An interrupted calculation
prints no `PLAY` decision.

Verification before documentation: focused Task 5/API-inspector tests `34
passed`; full pytest `468 passed`; CLI help listed all eight planned options;
repository-wide Ruff passed.

## Task 5 Review Hardening

Unsupported Playable runs are now fully non-actionable. When the proposed
package exceeds the 1% self-dilution limit, the returned package is `NO BET`
with no coupons, zero cost and expected payout, the full bank unused, no
modeled ROI, and an empty derived brief. Sensitivity rows apply the same
suppression, and the exact package CSV contains only its header. Research mode
still retains diagnostic coupons and the unsupported warning. The exact 1%
boundary remains supported.

Atomic report publication now rolls back after any `BaseException`, including
`KeyboardInterrupt` and `SystemExit`, once publication has started. The
original exception is re-raised after both prior artifacts are restored and
temporary/backup files are cleaned.

Fresh `drawing-info` payload IDs must exactly match the requested drawing ID
before EV components are computed. Oversized numeric conversion failures are
normalized to `ValueError`, CLI overflow failures become controlled
`BadParameter` output, and parser receipt timestamps must include an explicit
timezone. Reports now disclose whether jackpot came from the TotoBrief payload
or an explicit override.

Sensitivity factors are materialized and selected sequentially. The workflow
retains only scalar sensitivity summaries and the requested main
surface/package; instrumentation observes at most the main surface plus one
transient sensitivity surface. Main package selection and bounded top-20
diagnostics share one complete deterministic ranking. Every `3**15` EV value
is still ranked for selection; no probability or coupon candidate truncation
was introduced.

Review-fix verification before documentation: focused EV/API-inspector tests
`66 passed`; full pytest `476 passed`; CLI help listed all planned options;
repository-wide Ruff passed.

## Latest Completed Task: Chronological Modeled-EV Backtest

Task 6 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.backtest` module exposes immutable config, row, summary, and result
types. It validates dynamic stake-multiple banks, finite unique thresholds and
prize factors, and validated frozen holdout IDs from the existing strategy
manifest loader.

Finished drawing candidates are selected from `Drawing` rows with holdout IDs
excluded in SQL before any event or quote query. Historical EV inputs query
only ordered event identifiers and BK/pool quote columns; actual result columns
are loaded only after all factor/bank/threshold packages and deterministic
SHA-256 hashes for that drawing are complete. Inputs require exactly orders
0..14, valid normalized BK rows, Jeffreys-smoothed pool rows, positive pool
sum, and non-negative jackpot.

Each drawing builds one reusable exact component set. Every prize-fund factor
materializes and ranks one complete surface, then reuses that ranking across
all banks and thresholds without candidate limits or timeouts. Selection is
monotonic by threshold, respects exact bank caps, leaves unused bank, and emits
honest zero-cost `NO BET` rows. Realized output records best hits and cumulative
9..15 indicators.

Completed drawings are atomically checkpointed to a diagnostic partial CSV
bound to the exact normalized run configuration, requested window, community,
and forbidden IDs. Resume accepts only complete drawing groups and does not
turn interrupted work into report rows. Final reports include modeled expected
payout/ROI, bank utilization, hit rates, skip rate, and the over-80% model
review alert. They state that expected crowd denominators are modeled and that
modeled payout/ROI are not observed bookmaker payout/ROI.

`backtest-ev` requires `--frozen-manifest`, resolves forbidden IDs before
opening the read-only database, parses comma-separated banks and thresholds
deterministically, and shows drawing/category progress with ETA.

Verification: focused backtest/report tests `27 passed`; full pytest `497
passed`; worktree-local CLI help listed all six options and marked the manifest
required; repository-wide Ruff passed. No historical EV run was interpreted as
profitability evidence, and the old frozen holdout was not used for development
or evaluation.

## Task 6 Review Hardening

`--last N` now means the latest `N` drawings that ultimately have both valid
pre-result inputs and complete normalized actual results. Candidates are scanned
newest-first; each package surface, ranking, selection, and hash is completed
before that candidate's result projection is queried. Incomplete or invalid
newer candidates are skipped and older candidates are evaluated until `N`
complete drawings are obtained. Returned rows remain chronological.

Checkpoint skip records are diagnostic only and are re-evaluated on every
resume. Only completed drawing row groups are reusable. Loading now requires the
exact unique Cartesian grid of configured bank, threshold, and prize factor for
each completed drawing, and validates decision, bank cap, selected count, cost,
unused bank, payout/ROI, self-dilution support, package hash, best hits, and all
9..15 indicators. Stale skips can become processed drawings and displace older
checkpoint rows while preserving same-config equivalence with uninterrupted
execution.

Historical Playable rows now apply the same self-dilution boundary as the live
command: exactly 1% remains supported, while above 1% is a truly empty `NO BET`
with zero cost/payout, full unused bank, no modeled ROI, and explicit ratio and
support fields. Summaries include unsupported counts. Final reports and CLI
checkpoints include the full configuration hash in their deterministic paths,
so bank, threshold, or frozen-manifest holdout changes cannot overwrite another
configuration's artifacts.

Leakage regressions inspect SQL order and projections: the initial `Drawing`
query contains holdout exclusion before any event/quote query, pre-hash input
queries omit `Event.result`, and the result projection appears only after the
`packages_ready` callback carries deterministic hashes. A manageable complete
`3^3` orchestration regression uses real materialization and the production
ranker once per factor and confirms all 27 coupons remain available; full
15-event acceptance remains Task 7.

Review-fix verification: focused backtest/report tests `36 passed`; full pytest
`506 passed`; CLI help listed all required options; focused and repository-wide
Ruff passed.

## Final Task 6 Checkpoint Integrity

Checkpoint CSVs now include one deduplicated `package` manifest record per
referenced package hash. Each record stores the canonical ordered coupon payload;
loading requires unique 15-character `1`/`X`/`2` coupons, recomputes SHA-256 with
the production comma-separated encoding, and matches coupon counts against every
referencing row. Every `PLAY` row must reference a non-empty manifest, while
`NO BET` references only the empty payload and `EMPTY_PACKAGE_HASH`. Missing,
duplicate, conflicting, orphan, malformed, or tampered manifests reject resume.
Coupon payloads remain checkpoint-only and are not added to final report rows.

SQL leakage tests now retain statements and bound parameters. They prove the
initial `Drawing` query excludes frozen holdout IDs, every Event or Quote query
is scoped to exactly one allowed drawing ID, no forbidden ID reaches those
queries, pre-hash projections omit `Event.result`, and actual results are queried
only after `packages_ready` exposes package hashes.

Final integrity verification: focused backtest/report tests `41 passed`; full
pytest `511 passed`; worktree-local `backtest-ev --help` exited successfully with
required `--frozen-manifest`; repository-wide Ruff passed.

## Final Task 6 Row Binding

Checkpoint package manifests now commit not only to exact coupon payloads but
also to canonical sorted unique `(drawing_id, bank, threshold,
prize_fund_factor)` references. The loader derives the expected references from
completed rows and requires exact per-hash equality, so every row context maps
to exactly one matching manifest and equal-count valid package hashes cannot be
swapped between rows. Duplicate, missing, extra, unsorted, or non-canonical
references reject resume. The coupon hash remains solely a hash of the canonical
coupon payload, and row contexts remain checkpoint-only metadata.

The SQL leakage regression now identifies Event/Quote access from SQL table
references, requires every such statement to follow the holdout-filtered
`Drawing` query, and extracts the drawing-ID bind only from an explicit
`events.drawing_id = ?` or `quotes.drawing_id = ?` predicate. Synthetic
Event-only and Quote-only unscoped statements prove unrelated integer binds
cannot satisfy the regression. Pre-package input projections still omit
`Event.result`.

Row-binding verification: focused backtest/report tests `48 passed`; full pytest
`518 passed`; worktree-local `backtest-ev --help` exited successfully with
required `--frozen-manifest`; repository-wide Ruff passed.

## Latest Completed Task: End-to-End EV Acceptance

Task 7 of the Expected-Value Package Engine is complete. Acceptance tests cover
the fresh 15-event payload boundary with an injected deterministic small-space
surface, honest zero-cost `NO BET`, dynamic bank capacity, deterministic report
hashes, complete model assumptions, rollback-safe interruption behavior, and a
direct regression for the independent reference oracle's eight-event limit.
No production EV definition or search behavior changed during acceptance.

Fresh acceptance evidence:

- Full pytest: `526 passed in 5.39s`.
- Repository-wide Ruff: `All checks passed!`.
- Five-event benchmark: `243` coupons, `PASS`, `0.116127 s`, `62.44 MiB`
  peak memory, maximum EV error `1.626e-19`, and zero crowd-tail error.
- `ev-package --help` and `backtest-ev --help` exited successfully and exposed
  every documented option; the latter retained required `--frozen-manifest`.
- Because the shared editable virtual environment targets the parent checkout,
  worktree CLI acceptance used `PYTHONPATH=src` to select this branch's source.

Mandatory full-space benchmark evidence:

- Event count: `15`.
- Coupon count: `14,348,907` (`3^15`), with no candidate truncation.
- Independent samples: `20`.
- Verification: `PASS`.
- Elapsed time: `61.763504 s`.
- Peak resident memory: `1958.73 MiB`.
- Minimum denominator: `0.00550589657572`.
- Maximum sampled EV absolute error: `7.994e-15`.
- Maximum sampled crowd-tail absolute error: `2.776e-17`.

The EV engine is mathematically and operationally accepted under its approved
experimental prize-fund proxy and independent-event crowd model. `PLAY` remains
model output, not a profit guarantee. External probability collection, event
matching, and prospective observed-payout validation remain separate work.

## Latest Completed Task: External Odds Coverage Audit Reports and CLI

Task 6 of the API-Sports coverage audit is complete. Added a read-only
coverage audit over the latest complete stored external-odds snapshot per
drawing. The audit reports all 15 event dispositions for every audited drawing,
including explicit silent-loss diagnostics if a stored snapshot is malformed,
and aggregates overall, per-sport, per-league, and per-drawing metrics for
unique matches, missing/ambiguous/unknown-sport outcomes, consensus coverage at
one/two/three bookmakers, fallback reason classes, quota/provider failures,
fallback events per drawing, and requests consumed per drawing.

The prospective gate returns `PENDING` below 30 drawings or 450 events, `GO`
only when the registered thresholds pass, and `STOP` otherwise. The registered
thresholds remain at least 80% unique matching, at least 70% usable consensus,
zero ambiguous matches, and explicit external/fallback disposition for every
event. Per-sport and per-league metrics are diagnostic only and add no gate.

Added deterministic rollback-safe external coverage CSV/Markdown reports. The
CSV contains one row per event disposition followed by stable aggregate rows.
The Markdown records configuration, provenance/quota summaries, overall/sport/
league/drawing metrics, fallback reasons, gate predicates, and explicit
statements that coverage is neither probability quality nor profitability
evidence.

Added `collect-external-odds --open --provider api-sports --db ...` and
`audit-external-coverage --db ... --last ... --min-bookmakers ...`.
Collection requires `--open`, `provider=api-sports`, and `API_SPORTS_KEY`
before constructing the provider. Audit opens the existing SQLite database in
read-only mode, performs no migrations or network calls, and writes reports
from stored snapshots only. This remains audit-only and does not change
`ev-package` or `PLAY`.

Verification before final commit: focused audit/CLI tests passed (`13 passed`),
full pytest passed (`607 passed`), both new CLI help commands exited
successfully, and repository-wide Ruff passed.

## Task 6 Review Hardening: Complete Coverage Report Schema

Coverage reports now expose every `CoverageMetrics` field consistently.
Aggregate CSV rows include stale, semantic, and incomplete-market counts, while
event rows also expose provider event IDs and per-collection request counts.
Sport, league, and drawing Markdown tables include explicit disposition,
match, missing/ambiguous/unknown-sport, bookmaker availability at one/two/three,
usable consensus, stale, semantic, incomplete-market, quota, provider-error,
and fallback metrics in deterministic scope/name order.

Fallback classification now parses only canonical stored consensus-rejection
tokens. Stale prices, missing outcomes, duplicate bookmaker markets, and
football/hockey settlement-semantic rejections are counted exactly once per
event; incidental substrings do not collide with stale, semantic, incomplete,
quota, or provider-error classes. One- and two-bookmaker availability includes
matched minimum-bookmaker fallbacks, while usable consensus still requires the
configured minimum and an external-consensus disposition. The prospective gate
and its thresholds are unchanged.

Added dedicated report tests for all 15 disposition rows, complete aggregate
schema/content/order, complete Markdown sections and scope metrics,
byte-identical repeat writes, and rollback/temporary-file cleanup after a
`BaseException`. Focused audit/report/CLI verification passed (`28 passed`).
Full pytest passed (`622 passed`), repository-wide Ruff passed, and both new CLI
help commands exited successfully with their required options. Exact command
evidence is also recorded in the ignored Task 6 report.

## Approved Next Design: API-Sports Coverage Audit

The next isolated subsystem is a prospective, free-tier-first external odds
coverage audit. API-Sports is the first provider because its football and hockey
APIs expose pre-match odds on the free plan. This stage does not change
`ev-package` or any accepted EV definition.

The design requires deterministic fail-closed event matching, strict football
full-time and hockey regulation-time `1/X/2` semantics, per-bookmaker de-vig,
a three-bookmaker median consensus, explicit event-level TotoBrief BK fallback,
quota-aware caching, append-only provenance, and no secret persistence.

The prospective gate requires at least 30 future drawings and 450 events, at
least 80% unique event matching, at least 70% fresh complete consensus coverage,
zero consumed ambiguous matches, and an explicit external/fallback disposition
for every event. A failed gate tests a second free provider before any paid plan.
Payment up to 30 USD/month is considered only when measured quota limits, rather
than missing events or markets, are the cause of failure.

Design specification:
- `docs/superpowers/specs/2026-07-14-api-sports-coverage-audit-design.md`

Next action:
- execute the seven-task TDD implementation plan with independent review gates.

Implementation plan:
- `docs/superpowers/plans/2026-07-14-api-sports-coverage-audit.md`
- Tasks: provider-neutral targets, API-Sports transport/cache/quota, fail-closed
  matching and manual alias suggestions, strict three-way consensus,
  append-only storage/collection, audit reports/CLI, and end-to-end acceptance.

## Latest Completed Task: Live API-Sports Contract Hardening

Authorized live checks found several assumptions that synthetic fixtures had
missed. Football `/fixtures` rejects `page`; official response envelopes omit a
top-level timestamp; odds items omit `teams`; unrelated odds markets may use
numeric outcome labels; a daily quota reserve must not be applied to the
per-minute allowance; and cached quota headers must not act as current quota.
The client now follows those live contracts, stores an explicit receipt time in
cache schema v2, and preserves raw provider payload hashes.

Open TotoBrief drawing 4945 (`id=11953`) returned `start_at=null` and
`name_en=null` for all events. Target times are now optional. Matcher v2 keeps
the three-hour filter when target time exists; otherwise it accepts only one
unique exact directional team match in the deadline-date/next-date schedule
window. Reviewed aliases were added only for pairs observed in live API-Sports
records. Fuzzy and reversed pairs remain unconsumed.

The first complete prospective snapshot contains 15 explicit dispositions,
11 external consensuses, four TotoBrief BK fallbacks, zero ambiguous matches,
two actual HTTP requests on the final cache-assisted run, and 11 cache hits.
Coverage audit result: 73.33% unique matching and consensus, decision `PENDING`
because the 30-drawing/450-event sample floor is not met.

Verification target after documentation: full pytest and repository-wide Ruff.
Next isolated task: decide and test exact reversed-pair handling with explicit
`1`/`2` orientation swapping; do not silently consume reversed provider events.

## Multi-Day Eligibility Task 3A: Persistence Complete

External collection storage now persists the target fingerprint, configured
missing-start horizon, canonical per-date schedule results, drawing
eligibility, provider start, effective start, and timing source. Existing
SQLite databases receive additive columns; legacy runs remain readable only as
`unknown`, and read-only database opening never performs a migration.

`load_current_drawing_eligibility` returns a verdict only for a complete
15-event run matching the exact drawing ID and target fingerprint. Malformed
schedule JSON and inconsistent timing/eligibility provenance fail closed.
Focused verification passed: 16 storage tests and Ruff on all touched files.
Task 3 audit/report diagnostics remain next; category, bank, probability, EV,
and coverage-gate definitions are unchanged.

## Multi-Day Eligibility Task 3B: Audit and Reports Complete

Coverage auditing now exposes target fingerprint, collection horizon,
requested/successful/failed schedule dates, event timing sources, drawing
eligibility, provider-missing events, and partial-schedule events. Diagnostic
collection scopes are disjoint and deterministic: `ordinary_two_day`,
`expanded`, `multi_day`, and `unknown`. Legacy collections stay in `unknown`.

The existing overall coverage-gate population, predicates, and thresholds are
unchanged; scoped metrics are diagnostic only. Failed schedule dates are
counted independently from affected event fallbacks. CSV and Markdown reports
remain atomic and deterministic. Focused verification passed (`37 passed`),
Ruff passed, and repeated report hashes were byte-identical:
`45359a3edb07741261cf3cfa5caa3e6f85628f99e76adb3e9998afa4400655b5`
for CSV and
`796fb78654a5db4a6c0bb9d9f8979fcf37b34c1b1d2f229ee9e080692f6544bb`
for Markdown. Task 4 progressive orchestration is next.

## Multi-Day Eligibility Task 4: Progressive Collection Complete

Fresh prospective collection now has two bounded phases. Base collection keeps
the existing two-day horizon and `max_passes` semantics. A stable canonical
`0 exact candidates` miss expands through day five only when the original
TotoBrief event start is absent. Known-start misses never expand. Expansion has
its own pass limit, reuses the pinned target and cache-session path, retries
only operational failures with the existing delay, and never sleeps merely to
change phase.

The result and CLI expose phase/pass counts, final horizon, schedule-date
totals, eligibility, source counts, and stop reason. New controls are
`--expand-missing-starts/--no-expand-missing-starts`,
`--expansion-horizon-days`, and `--max-expansion-passes`. Focused verification
passed (`31 passed`), CLI help succeeded, and Ruff passed. Task 5 fail-closed
playable timing integration is next; probability, EV, bank, stake, and package
ranking definitions remain unchanged.

## Multi-Day Eligibility Task 5: Playable Timing Gate Complete

`EVPackageRun` now carries immutable timing provenance. The resolver receives
the exact fresh drawing payload already used for EV input, computes its
canonical target fingerprint, and performs only a read-only exact lookup in
the selected SQLite database. No external probability enters EV input,
surface construction, coupon ranking, or sensitivity math.

Playable output now requires timing status `playable`. `multi_day`, `unknown`,
`absent`, and `not_checked` suppress the package and all displayed sensitivity
decisions to zero-cost `NO BET`, and exact top coupons are not published after
the veto. Research retains coupons and ranking while reporting timing status.
Missing/unreadable databases and unparseable timing targets become conservative
warnings rather than Research failures. `ev-package` adds read-only `--db`.

Focused verification passed (`59 passed`), CLI help and Ruff passed, and the
three independent review findings were re-reviewed as resolved. Task 6
end-to-end acceptance and final documentation are next.

## Multi-Day Drawing Eligibility Complete

The approved six-task implementation is complete. Missing TotoBrief starts are
collected first over two Moscow calendar days and may expand through day five
only after a stable exact-pair miss. Schedule success and failure remain
isolated per date, and every pass persists an immutable 15-event snapshot with
target fingerprint, horizon, provider/effective starts, source, and eligibility.

Historical and Research flows retain multi-day and unresolved drawings for
analysis. Playable EV output requires an exact stored fingerprint match and
`playable` eligibility: all 15 effective starts known within an inclusive
two-day Moscow span. Confirmed multi-day, unresolved, absent, mismatched, and
unchecked timing all produce zero-cost `NO BET` without publishing diagnostic
coupons. External probabilities remain audit-only and do not enter EV or
package ranking.

Deterministic end-to-end acceptance covers ordinary two-day, day-five
expansion, partial provider-date failure, confirmed multi-day, and unresolved
drawings through collection, SQLite reload, audit/report, and playable/research
output. Focused verification passed: 179 tests. Full-suite and Ruff results are
green: 746 tests passed, repository-wide Ruff passed, both affected CLI help
commands succeeded, and `git diff --check` passed.

## Approved Next Design: Safe Drawing Runner

The next production task is a single operator command that performs preflight,
waits until T-20, revalidates the exact pinned drawing, runs fresh prospective
collection, timing eligibility, coverage audit, and the existing EV package,
then publishes a deterministic run manifest. T-5 is a hard fail-closed boundary
for starting new runner phases. The command never places a bet.

This orchestration does not change probability, EV, category, bank, stake,
consensus, coverage-gate, or timing definitions. External consensus remains
audit-only while the prospective gate is below 30 drawings and 450 events.

Design specification:
- `docs/superpowers/specs/2026-07-16-safe-drawing-runner-design.md`

Next action: write the TDD implementation plan after user review of the spec.

## Approved Implementation Plan: Safe Drawing Runner

The implementation is decomposed into six independently reviewed TDD tasks:
immutable timing/domain, pinned collection cutoff, provider-neutral
orchestration, deterministic reports, Typer wiring, and end-to-end acceptance.

Implementation plan:
- `docs/superpowers/plans/2026-07-16-safe-drawing-runner.md`

Next action: execute the plan task by task with review gates.

## Safe Drawing Runner Task 1 Complete

Added the provider-neutral immutable runner domain and UTC timing state machine.
`DrawingRunnerConfig` preserves the existing divisible-bank/stake rules and
playable default, `pin_drawing()` binds a deterministic canonical target
fingerprint, and waiting transitions exactly at T-20 with a fail-closed T-5
boundary. Waiting uses injected clocks and sleepers only, rechecks wall time
after each bounded sleep, and never sleeps through the final-window boundary.

Task 1 verification passed: focused runner tests (`51 passed` after the
reviewed fingerprint fix), focused Ruff,
previous full pytest baseline (`796 passed`), full Ruff, and `git diff --check`.

## Audit-only sports-statistics slice (2026-07-27)

Implemented locally, not committed:

- provider-neutral immutable football evidence contracts and canonical hashes;
- additive append-only SQLite run/event snapshot tables;
- API-Sports adapter over the existing authenticated/cache/quota transport;
- strict exclusion of target, future, cancelled, postponed, and non-finished
  fixtures;
- recent overall/home/away W-D-L and goals, points/form, rest, and optional
  standings;
- `collect-sports-stats` with open/id/number selection, secure `.env` loading,
  deadline checks, and cache-only historical as-of;
- JSON/CSV/Markdown audit reports with explicit missing/fallback reasons;
- no influence on probability, brief, package, scheduler, PLAY, result, or
  settlement paths.

Prospective acceptance on drawing 4957 produced a valid 15-row immutable run,
but zero complete events. The API-Sports free plan rejects 2026 team history
and standings (`provider_plan_unavailable`; the provider response limits free
season access to older seasons). The optimized second run used 10 target
context cache hits and 7 HTTP requests, with 15 partial rows and explicit
`MARKET ONLY` fallback. This proves the fail-safe pipeline, not useful sports
coverage and not profitability.

Next: evaluate a lawful free current-season source against the same contracts.
Only if no viable free source exists should the previously allowed paid ceiling
be reconsidered. Do not blend empty API-Sports evidence into market
probabilities.

Verification for this uncommitted slice:

- focused sports-stat regressions: `26 passed`;
- focused provider/collector/runner compatibility: `129 passed`;
- full suite: `1382 passed in 234.10s`;
- repository-wide Ruff: passed;
- `git diff --check`: passed;
- CLI help smoke: passed;
- reviewed prospective drawing-4957 run:
  `be141718e87c9e7a6ca85eecdc34a17cbed20c2e249bc3d0a142cd439db99db4`;
  15 partial rows, no numeric history windows, blank CSV/Markdown feature
  fields, and explicit `provider_plan_unavailable`.

Independent review hardening is implemented locally and remains uncommitted:

- historical as-of uses only frozen raw-detail/provider caches and never
  contacts TotoBrief or API-Sports;
- normal prospective team-history cache entries (`last=10`) are replayable by
  the bounded historical `from/to` path only when their provider observation
  time is at or before the requested as-of; the adapter still applies the
  strict target-kickoff/as-of cutoff locally and records the actual cached
  request fingerprint;
- prospective-to-historical replay is covered end to end with API-Sports
  network access disabled, identical event features, and byte-identical
  JSON/CSV/Markdown reports; a cache captured after as-of is rejected;
- raw detail must have a valid sidecar and `fetched_at <= as_of`;
- unavailable history is `None`, not a zero-valued window;
- target fixture standings capability is parsed from `league.standings`;
- unrelated-team history is ignored and cannot produce a complete event;
- run/event drawing/provider/fingerprint/time/provenance identity is exact;
- sports-stat reports are ignored generated artifacts and deterministic;
- existing databases initialize additively without data loss;
- archived package/PLAY provenance remains unchanged by sports persistence.

The remaining prospective-cache/historical-replay P1 is closed locally.
Final verification for the uncommitted sports-stat slice: focused
sports-stat/provider/collector tests `38 passed`; full suite
`1384 passed in 243.60s`; repository-wide Ruff and `git diff --check` passed.

## Drawing 4958 focused identity patch (2026-07-28)

Implemented locally, not committed: Israel and Uzbekistan now share stable
Russian/English/ISO country identities; reviewed aliases map `Хорезм` to
`Xorazm` and `Термез Сурхан` to `Surkhon`; systematic resolver v2 rejects
women targets unless the provider candidate has explicit W/Women/female
context and is not reserve/academy/youth/U17-U23. Fixture regressions cover
API-Sports IDs `1557935` and `1516080`, while the male false leader `1493023`
remains rejected. API-Sports still has no women fixture for event 5, so drawing
4958 remains unresolved until a second provider supplies that event.

Focused verification: `98 passed`; touched-file Ruff and `git diff --check`
passed.

## Data-health contract v1 (2026-07-29)

Implemented locally for task `TOTO-DATA-HEALTH-CONTRACT-V1`:

- read-only `data-health` CLI with strict default, range/latest selectors,
  controlled exit codes, and CSV/JSON/Markdown exports;
- stable per-drawing reason codes and independent eligibility for four use
  cases;
- explicit `0/0/0` rejection and terminal VOID support;
- canonical RAW discovery limited to `data/raw`;
- actionable settlement obligation limited to `pre_bet_runner` archives;
- fail-closed gates in baseline prospective brief generation and the
  MVP/baseline/strategy historical backtests;
- explicit research-only override with persisted/printed warning.

Current full-history v1 result on `data/toto.db`:

- 2,199 drawings / 32,985 event rows;
- 369 finished drawings with incomplete terminal results;
- 754 missing terminal outcomes in finished drawings;
- 215 drawings with invalid all-zero pool;
- 3 drawings with missing quotes/names/incomplete BK;
- 12 drawings with canonical primary `data/raw` evidence;
- 4 drawings with complete immutable result snapshots;
- gaps 3843/3844; no duplicate visible numbers;
- strict `historical_inventory`: 1 healthy, 2,198 unhealthy;
- `backtest_probability`: 1,651 eligible under v1 SQL-quality semantics;
- `prospective_generation`: 1,981 structurally input-eligible;
- `result_settlement`: 4 result-evidence-eligible.

The RAW count intentionally differs from the forensic report's 15 because the
contract does not accept JSON under reports/tests as canonical source
provenance. Production data was not changed and no network/backfill ran.

Verification:

- contract/gate focused suite: `68 passed`;
- full pytest: `1485 passed in 248.07s`;
- repository Ruff: passed;
- `git diff --check`: passed;
- strict real CLI: controlled exit `3`;
- database SHA-256 remained
  `1a6c9f4d62ba2198852066405342769ebbfa8a057b0525661fc1b58f576fd0c9`.

Next task: P0.2 lifecycle-aware collector freshness.

## Preflight escalation and fallback v1 (2026-07-31)

Implemented locally for `TOTO-PREFLIGHT-ESCALATION-AND-FALLBACK-V1`:

- reviewed alias catalog v3 with provenance/reviewer/date and generic Caracas
  FC/Caracas plus Independiente Santa Fe/Santa Fe team identities;
- conservative source-absence classification that does not mask
  identity-bearing ambiguous provider fixtures;
- fingerprint-bound ACTION REQUIRED JSON/Markdown, immutable attempts,
  provider/candidate diagnostics, optional notification command, and strict
  reviewed-schedule evidence queue;
- passive retry plan at T−360/T−240/T−180/T−100/T−90, hard stop before T−60,
  exact drawing/deadline/fingerprint drift guard, no busy sleep, no activation;
- same-fingerprint-only attention resolution after atomic READY 15/15;
- read-only `preflight-status --open`;
- passive morning candidates default to 08:00/10:30/12:00. Evening activation
  remains disabled and this task installs no LaunchAgent.

Network-free drawing-4960 rehearsal:

- isolated DB copy:
  `reports/rehearsal/preflight-4960-network-free-v1/toto-copy.db`;
- initial: 13/15 event matches, atomic 0/15 pins, unresolved orders 12/14,
  `ACTION REQUIRED: unresolved 2/15`;
- final after reviewed aliases and strict snapshot-backed rehearsal evidence:
  READY 15/15, playable/two-day, 14 API-Sports pins plus one
  reviewed-schedule pin;
- evening candidate generated only, activation not requested, no CSV package
  and no bet-ready marker;
- attention cleared and same-fingerprint `RESOLVED.json` written;
- network calls zero; `data/toto.db` and the source rehearsal DB SHA-256 values
  remained unchanged;
- summary:
  `reports/rehearsal/preflight-4960-network-free-v1/rehearsal-summary.json`.

The `.invalid` source snapshots in this rehearsal validate the strict local
contract only and are not operational betting evidence. A real
provider-missing event still requires captured official and independent HTTPS
sources reviewed before deadline.

## Date-scoped reviewed evidence policy (2026-07-31)

Implemented locally for `TOTO-REVIEWED-EVIDENCE-DATE-SCOPED-POLICY-V1`:

- reviewed fallback and failed-date attribution use the event's API-Sports UTC
  request date;
- unrelated plan-limit failures in an expanded five-day window no longer block
  strict evidence for a successfully fetched relevant date;
- local-calendar cross-midnight events remain bound to the UTC provider date;
- missing/failed relevant dates, ambiguous identity, stale/mismatched evidence,
  fingerprint drift, and ineligible multi-day spans remain fail-closed;
- the reusable retry rehearsal accepts explicit failed provider dates.

Drawing-4961 isolated acceptance used real local 31-Jul/1-Aug caches plus
injected plan-limit failures for 2-4 Aug. It produced ACTION REQUIRED 13/15
with zero pins, then READY 15/15 with 15 atomic mixed-provider pins, zero
network requests, zero package/bet-ready artifacts, and unchanged main DB
SHA-256 `d5ad1ff83f7c93ec14b04a6145ba603ced8f144a87a71f0a1003f621ebb97a73`.
Artifact: `reports/rehearsal/TOTO-4961-DATE-SCOPED-POLICY-V1-ACCEPTANCE-20260731/rehearsal-summary.json`.

## Zero-pool bootstrap retry (2026-08-03)

Implemented locally, not committed: an early 15-event TotoBrief payload with
complete positive BK probabilities but pool `0/0/0` is classified as
`totobrief_pool_not_ready`. It is not cached or imported as synchronized
drawing detail. Morning dispatch preserves the exact drawing identity and
creates a bounded retry plan at approximately +10/+30/+60/+180 minutes and
08:00/10:30/12:00 Moscow time when these instants precede the hard stop.
Only this explicit bootstrap plan may contain exactly one `--activate` per
attempt, allowing the normal evening scheduler to be installed after the pool
becomes valid; ordinary passive retry plans still reject activation. Identity
or deadline drift remains fail-closed, and no automatic bet placement exists.

## Provider-neutral schedule evidence resolver v1 (2026-08-03)

Implemented locally for `TOTO-SCHEDULE-RESOLUTION-V2`: reusable reviewed
schedule observations are keyed by canonical team identities and kickoff, not
by drawing/event order. Exact aliases, competition/class, orientation, bounded
five-day timing and hash-checked review provenance are mandatory. Fuzzy-only,
conditional, reversed, stale, conflicting or missing evidence stays unresolved.
Morning preparation automatically uses the repository ledger when present.

Drawing 4965 evidence resolves events 5, 10 and 12. Events 7 and 13 remain
fail-closed: event 7 has no exact non-conflicting reviewed evidence, while the
supplied event-13 material does not establish the target home/away identity and
kickoff. Any official home/away or identity conflict for event 13 is rejected;
no reverse-orientation inference is allowed. Evidence-only rehearsal therefore
verified **13/15**, with unresolved events **7 and 13**, not READY; no package or
bet marker is published.

The resolver now normalizes multilingual diacritics and club designators while
preserving gender/age class, reuses only reviewed exact aliases across drawing
IDs, derives the complete bounded date range for drawings with missing starts
or four/five-day spans from Moscow calendar boundaries to all intersecting UTC
provider dates, exposes typed source-gap/failure states, and provides
append-only hash-validated reviewed-observation ingestion. Final pin
revalidation binds the observation and ledger semantic hashes.

## Safe mixed external enrichment (2026-08-04)

Implemented and verified: preparation now requires valid, hash-bound 15/15
TotoBrief BK and pool probability rows while allowing explicit per-event
`totobrief-baseline` pins when external schedule enrichment is unavailable.
External identity and probability conflicts remain fail-closed; baseline pins
never synthesize provider fixture/team IDs. Readiness and downstream provenance
record `external_coverage_count` and `baseline_only_event_orders`.

The production 4965 CLI preparation reached READY 15/15 with 13 externally
enriched events and baseline-only orders 7 and 13. At 17:59 Moscow it correctly
deferred as `drawing_not_playable` because the deadline had passed; no package,
bet-ready marker, or bet was produced. Verification evidence: final 25 focused
tests passed, an earlier focused run passed 72 tests, and Ruff/diff-check passed.

## Reviewed catalog hash handoff (2026-08-04)

Implemented locally: morning preparation now reads the validated canonical pin
set's `reviewed_catalog_hash`, binds it into `MorningPreparedDrawing` and the
schema-v5 scheduler plan, and forwards the exact value to `run-drawing` as
`--expected-reviewed-catalog-hash`. Runner preflight passes that binding to
`load_ready_pin_set`; missing or mismatched reviewed-input hashes fail closed.
Targeted verification passed: 71 morning/runner/registry tests plus 155
scheduler/atomic-final tests. The stale sync/prepare CLI test doubles were
updated to implement the complete preparation-result contract without adding
runtime fallbacks. A real 4966 rehearsal then exposed a separate preparation
boundary bug: merely loading the schedule-evidence ledger attached its hash to
a canonical pin set even when none of the 15 selected pins used reviewed or
schedule-evidence input. Preparation now derives the reviewed catalog binding
only from the source and provenance of the actually selected canonical pins;
zero selected reviewed/evidence pins persist a null hash, while selected pins
still require one exact hash and missing/conflicting/mismatched bindings remain
fail-closed. The integration regression covers a present but unused ledger
with API-Sports plus TotoBrief baseline-only pins. Full local verification
passed: 1614 tests and Ruff. No network rehearsal or scheduler activation was
performed after this fix.

## Dynamic pool refresh semantics (2026-08-04)

Implemented locally for `local-totoai-dynamic-pool-pin-fix`: a later valid
TotoBrief pool snapshot no longer conflicts with an otherwise unchanged ready
pin set. Canonical pins and their hashes remain unchanged; the preparation
summary advances its latest combined BK/pool evidence hash, and final EV input
uses the pool from the fresh final payload. BK matrix drift and drawing/event
fingerprint drift remain fail-closed. Regression coverage includes the mixed
13-external/2-baseline preparation path, pinned collection revalidation,
latest-pool EV input, immutable BK rejection, and participant-fingerprint
rejection. External rehearsal/scheduler activation was not run for this task.

## EV package quality-v2 (2026-08-10)

Implemented locally for `TOTOAI-FIX-4971-PACKAGE-QUALITY-20260810`:

- selector-side exposure minima now scale continuously as `K*s*p**alpha`
  instead of branching at probability 0.20; defaults give meaningful
  multi-coupon exposure at K=166 and remain per-event sum-feasible;
- the unchanged hard concentration cap has a configurable soft-headroom tier;
  diagnostics report every residual soft violation;
- deterministic quality swaps use incremental exposure and Hamming statistics,
  exact weighted-union P(13+/14+/15), provenance-seeded Monte Carlo P(9+),
  diversity, and robust log-EV tie-breaking;
- selector diagnostics and runner manifests bind probability snapshot/input,
  schedule-ledger byte/semantic hashes, package hash, and diagnostic self-hash;
  missing or mismatched required provenance fails closed;
- the historical selector feasibility result was paper-only; the hardened
  contract now names it `STRUCTURAL_PASS` while top-level output stays `NO BET`;
- the final independent package-safety veto was not weakened.

Frozen one-run-per-fixture evaluation completed for 4967/4969/4970 and the
then-prospective 4971 package. Every quality-v2 package has 166 unique coupons at bank 4,980
and stake 30, passes the unchanged safety evaluator, and has zero soft-headroom
violations. Exact results and all exposure rows are in
`plans/TOTOAI-AUDIT-4971-PACKAGE-20260810/quality-v2-frozen-comparison.md` and
its JSON companions. The pre-result comparison was descriptive only. The later
4971 result is recorded in the authoritative snapshot and postmortem below.
No profitability or real-money claim is made.

Final test verification was partitioned without omission: pytest collected
1,690 tests; the three explicit frozen quality-v2 nodes passed individually in
166.18s, 90.05s, and 86.69s; the exact complement passed 1,687 tests with those
three nodes explicitly deselected in 272.65s. The union is exactly 1,690 tests.

### Independent-review hardening checkpoint

Quality-v2 no longer exposes structural feasibility as top-level `PLAY`.
Selectors, direct CLI, runner reports/manifests and scheduler results remain
real-money `NO BET`; feasible coupons are isolated as `STRUCTURAL_PASS` and
`TRAINING/PAPER`. A trusted prospective-evidence registry does not yet exist,
so arbitrary evidence IDs/hashes and `real_money_actionable=true` fail closed.

The weighted quality score was removed. After hard safety and non-worsening
headroom, swaps compare P(13+), P(14+), P(15), optimization-stream P(9+),
diversity and robust log-EV lexicographically with explicit deadbands. P(13+),
P(14+) and P(15) remain nested exact unions and are never added. Optimization
and evaluation MC streams/seeds are domain-separated.

Provenance now requires actual regular non-symlink probability snapshot,
schedule ledger and canonical schema-v6 scheduler-plan artifacts. Their bytes,
semantic identities and the complete quality-v2 configuration/RNG/release
protocol are bound into diagnostics and manifests. Direct playable CLI use has
no way to self-declare provenance and therefore remains fail-closed.

Targeted regressions cover 166 coupons at 4,980/30, 332 at 9,960/30, and 100 at
2,500/25, plus nested modeled-union monotonicity. The full prospective 4971
bank-4,980 build exercised all four sensitivity factors with unchanged default
quality search (12 iterations, 512 candidates, 2,048 optimization samples and
8,192 evaluation samples) in 299.254715 seconds, inside the 360-second test
budget. Scheduler subprocess timeout remains the independent fail-closed
operational boundary.

The old and safety-v1 frozen values were preserved. Separate actual quality-v2
runs refreshed the finished-drawing goldens: 4967 hash `d4e407...aec15`, best/
mean hits 7/2.518072; 4969 hash `4b5e39...e8aa4`, 9/5.801205; 4970 hash
`2aa986...6a417`, 9/5.222892. Their core runtimes were 163.110503s,
87.664523s and 86.505469s. All remained 166-coupon, zero-headroom-violation
`STRUCTURAL_PASS` paper packages with top-level `NO BET`. The frozen 4971
quality-v2 artifact was not rerun and lacks coupon strings; its actual result
is known from the separate postmortem. No edge or profitability is proven.

### Quality-v2 release/heavy test split (2026-08-10)

The three full frozen recomputations, full bank-4,980 sensitivity runtime,
historical drawing-4951 replay/pinning, stale-schedule replay, and scheduler
prepare/final replay are retained as 13 `heavy`/`research` tests. Default
pytest now exercises 1,700 release tests from small deterministic surfaces and
hash-bound goldens; it does not recompute the `3**15` surfaces. The final clean
default run passed `1700 passed, 13 deselected in 103.71s` (104.19s wall),
inside the preferred 120-second target. A current stale-schedule heavy smoke
passed in 13.20s. The multi-minute heavy suite was intentionally not rerun;
last successful frozen/runtime results remain documented in the task
verification artifact.

The concise 4967 finding-to-code/test map is
`plans/TOTOAI-AUDIT-4971-PACKAGE-20260810/4967-package-defect-checklist.md`.
It explicitly records the poor best score of 7/15 and the lack of predictive
or real-money evidence.

### Generic runner/CLI release-boundary hardening (2026-08-10)

The public runner no longer propagates a residual legacy `EVPackage("PLAY")`.
It converts that package to top-level `NO BET`, empties actionable fields, and
retains coupons only as `TRAINING/PAPER` diagnostics. Sensitivity `PLAY` rows
are likewise suppressed. The CLI independently maps a residual injected
runner `PLAY` to `NO BET` before progress display or artifact publication.
Explicit orchestration and CLI regressions prevent test doubles or legacy
package builders from escaping the paper-only release boundary.

### Model/report boundary and complete selector context (2026-08-10)

The paper-only gate now starts at `DrawingRunnerResult`, not only orchestration:
manually constructed or injected top-level/package `PLAY` is converted to
`NO BET`, actionable fields are emptied, and retained coupons are labelled
`TRAINING/PAPER`. Direct runner report writing and transactional publication
apply the same sanitizer, and actionable EV child artifacts are not emitted.

Selection provenance now carries a canonical bound context and SHA-256 for
bank, stake, requested/effective coupon capacity, minimum gross EV,
concentration/probability policy, safety/provenance flags, and all quality-v2
algorithm fields. The selector compares it exactly with current inputs and the
referenced scheduler plan; schema-v6 plans, manifests, and diagnostics bind the
same context. Parameterized mismatch and incomplete-plan tests fail closed.

Targeted verification completed before the release run: 39 package-quality
tests passed in 3.02s; 158 report/scheduler tests passed in 4.87s; the combined
runner/provenance group passed 250 tests in 6.17s; and the three corrected
legacy schema-downgrade fixtures passed in 18.51s. Heavy research tests were
not run.

Final release verification after the model/report and selection-context
hardening passed `1716 passed, 13 deselected in 115.75s`. This supersedes the
earlier 1,700-test release count while preserving that run as historical
verification. No heavy/research test was executed.

### Direct EV report boundary closure (2026-08-10)

`write_ev_package_reports` now invokes the same shared `paper_only_ev_run`
normalizer as runner construction/orchestration. An arbitrary or legacy
`EVPackageRun` carrying `PLAY` is rendered as top-level `NO BET`: actionable
coupon CSV has only its header, selected cost/count/payout are zeroed, and
retained coupons appear only in an explicitly non-wager **Training/Paper
Coupons** Markdown section. Existing valid `NO BET`/`STRUCTURAL_PASS`
training artifacts remain reportable without losing their paper diagnostics.

The focused EV/package/drawing and runner report/orchestration group passed
`197 passed in 1.68s`. Heavy research tests were not run.

The final fast/release suite passed `1718 passed, 13 deselected in 110.78s`.
The two added tests are the direct injected-PLAY writer regression and the
legitimate structural-pass training-report regression.

## Drawing 4971 frozen-package postmortem (2026-08-11)

The complete result was `X2111X111X121X2`. Read-only scoring of the frozen
old and safety-v1 packages produced a best coupon of only 7/15 and zero 13+.
The frozen quality-v2 artifact did not retain its 166 coupon strings, so only
its exposure-derived mean (`5.144578`) can be recovered exactly; best, median,
and category counts must remain unknown rather than be regenerated after the
result.

Quality-v2 removed all zero-exposure actual outcomes and improved structural
concentration/diversity, but this is not evidence of predictive edge or
profitability. The durable postmortem is
`reports/analysis/drawing_4971_quality_v2_actual_evaluation.md`; the project
remains `NO BET / TRAINING/PAPER`.

## Drawing 4973 preparation and scheduler activation (2026-08-11)

The next open BaltBet drawing was discovered immediately after 4972 and bound
as drawing ID 12027 / visible number 4973, deadline 2026-08-12 17:00 MSK,
fingerprint `955d243b...20c`. Four API-Sports gaps were resolved from reviewed
official schedule evidence; the final canonical pin set is READY/PLAYABLE with
15/15 external schedule coverage (11 API-Sports, 4 schedule-evidence) and no
baseline-only events.

The schema-v6 evening scheduler is installed as
`com.totoai.production-scheduler.v6.9bd0e77f4fdc9257`, plan ID
`9bd0e77f4fdc9257`, bank 4,980 and stake 30. Its Moscow triggers are
15:00/15:30/16:00/16:15/16:30/16:40/16:44/16:50, with T-10 at 16:50.
An immediate wrapper smoke returned exit 0 / `no due scheduler phase`.

The daily morning dispatcher was replaced by an activating candidate with
08:00/10:30/12:00 plus post-deadline discovery attempts at
17:05/17:12/17:20. A live control run rediscovered 4973 and idempotently reused
the exact evening plan. This is operational evidence only; no package or
profitability result exists yet, and the release boundary remains
`NO BET / TRAINING-PAPER`.

The live setup exposed a repeat-preparation defect: a provider plan gap on the
UTC date of an already validated `schedule-evidence` pin incorrectly rejected
that pin, although first preparation already treats independent schedule
evidence as authoritative for that date. The repeat-pin check now applies the
same exemption. A regression performs first and repeated preparation across a
provider date failure and requires identical READY/PLAYABLE results.

## Drawing 4972 settlement and morning 4973 status (2026-08-12)

The daily morning dispatcher ran successfully twice on 2026-08-12, exited 0,
and idempotently reused/activated the exact drawing-4973 evening plan
`9bd0e77f4fdc9257`. Its production scheduler is installed for drawing 4973;
the first evening trigger is 15:00 MSK and T-10 is 16:50 MSK.

Drawing 4972 is now reconciled as `21X2222*2X2XXX*`. Events 8 and 15 are
reviewed voids after API-Sports returned `PST / Match Postponed`. The evening
scheduler had produced no authoritative final package (`NO BET`, final run
timed out at T-10). The pre-existing factor-1.00 preliminary paper file was
archived only for audit and settled: 166 unique coupons, hypothetical cost
4,980, best 11/15, zero 13+/14+/15. No bet was placed and actual cash loss is
zero. An alternative pre-existing factor-0.80 paper scenario had one 13-hit
coupon, but that is retrospective sensitivity evidence, not a valid strategy
selection claim. The durable report is
`reports/analysis/drawing_4972_preliminary_package_evaluation.md`.

## Drawing 4973 full-path rehearsal and timing fix (2026-08-12)

An immediate atomic-final rehearsal exposed a gap between preparation and the
final collection boundary: four exact `schedule-evidence` pins revalidated as
matched and carried reviewed kickoff times, but collection discarded those
times because no API-Sports fixture object exists for schedule-only evidence.
The final eligibility therefore became `unknown` for orders 0/8/10/13 despite
the same canonical pin set being READY/PLAYABLE. Collection now carries the
revalidated reviewed start through event records, eligibility classification,
storage validation, and reload. A regression covers a mixed 11-provider / four
schedule-evidence final collection and persistence round trip.

The corrected live drawing-4973 rehearsal completed exit 0 in 506.34 seconds:
raw/effective timing were both `playable`; the package contained 166 unique
paper coupons for 4,980; package safety approved all 166; and structural status
was `STRUCTURAL_PASS`. The top-level decision remained `NO BET` solely because
the quality-v2 prospective real-money release gate is closed. This is an
operational package-generation result, not profitability evidence or betting
authorization.

The rehearsal also proved the old primary-final timeout unsafe: the T-20
attempt was capped at T-16 minus 45 seconds, only 195 seconds, while the live
full-quality run required 506 seconds. The primary T-20 attempt now owns the
complete window through the actionable cutoff at T-10 minus the 45-second
publication reserve. The T-30 checkpoint remains the last-known-good fallback;
a later tick cannot overlap because the scheduler lock is process-scoped. No
search quality, samples, candidate count, or bank was reduced.

## Drawing 4973 evening incident: fix 1, T-45 child timeout (2026-08-12)

The T-45 warmup timeout was deterministic rather than a generic performance
failure. Warmup recursively used the fallback runner path, and command
construction selected `final_lead_minutes = 30` from that internal path. The
child therefore waited for T-30 while the parent deadline was T-30 minus five
seconds, guaranteeing termination immediately before work could start.

Command construction now gives a scheduler `warmup` phase a lead of 45 while
preserving refresh at 30 and atomic final at 20. A parameterized regression
binds all three phase-to-lead mappings. The next incident item is the separate
T-30 `safety_reselection_infeasible` failure; it has not been changed by this
fix.

## Drawing 4973 evening incident: fix 2, fallback provenance (2026-08-12)

The T-30 `safety_reselection_infeasible` result was not caused by an
infeasible coupon/exposure search. Its stored diagnostics named three missing
references: probability snapshot, schedule-evidence ledger, and scheduler
plan. The fallback CLI path constructed hash-only provenance, while quality-v2
correctly requires the referenced immutable artifacts.

Every scheduler fallback package phase now captures or reuses a run-scoped
immutable TotoBrief input and passes both `TOTO_FINAL_INPUT` and
`TOTO_SCHEDULER_PLAN` to `run-drawing`. This selects the existing
artifact-backed provenance path and retains the exact ledger binding. A
regression proves that refresh creates the snapshot and passes both artifact
paths. Related scheduler/runner/selector verification passed 264 tests. Full
release verification passed `1779 passed, 13 deselected in 111.15s`; Ruff also
passed.

## Drawing 4973 evening incident: fix 3, runner schema contract (2026-08-12)

The observed schema-v4 fallback report and schema-v5 scheduler expectation had
the same upstream cause as fix 2: the old fallback path had no final-input
provenance, and runner reports without that provenance are legacy schema v4.
Artifact-bound fallback now returns a result with `FinalInputProvenance`, so the
normal report writer emits current schema v5 and the existing strict scheduler
parser accepts it.

Regressions now prove both ends of the contract: an artifact-bound runner
result serializes as schema v5, and a refresh fallback captures its immutable
input, emits a schema-v5 manifest, and passes real scheduler parsing. The
previous proposal to weaken scheduler parsing by accepting v4 fallback was
discarded because it would conceal incomplete provenance. Related verification
passed 208 tests; full release verification passed
`1780 passed, 13 deselected in 109.31s`; Ruff passed.

## Drawing 4973 evening incident: fix 4, EV runtime (2026-08-12)

The exact saved 4973 run spent 430.741 of 506.342 seconds in EV. An offline
profile with the same snapshot and production quality settings took 444.760
seconds; `_pair_deltas` alone consumed 290.605 seconds across 12,106 calls.
The kernel's event loop was replaced by exact `int16` matrix multiplication.
No candidate, sample, sensitivity scenario, bank unit, safety constraint, or
objective tier was removed.

The identical cProfile run now takes 259.966 seconds (1.71x overall speedup),
with `_pair_deltas` reduced to 102.301 seconds. A realistic kernel benchmark
requires exact array equality and a material median speedup; related selector
verification passed 72 tests. A second full unprofiled run returned
`STRUCTURAL_PASS`, 166 coupons, four sensitivity scenarios, and the exact same
selected-package SHA-256 as the frozen pre-change 4973 report:
`dcb53918dc62f21749d17c38a925a9baa54220afbcc9cd1883230794b29364a7`.
Full release verification passed `1781 passed, 13 deselected in 123.04s`;
Ruff passed.

## Drawing 4973 evening incident: fix 5, DNS resilience (2026-08-12)

The emergency final recorded a real external DNS failure resolving
`totobrief.com`. The client already exhausted four bounded attempts. The
missing package was not caused by insufficient DNS retries: no valid LKG
existed because the earlier warmup/refresh phases had failed for issues 1–3.

After those upstream fixes, the existing LKG architecture is the correct
resilience mechanism. A dedicated regression establishes a valid 166-coupon
refresh package, injects four-attempt DNS failures across both final scheduler
attempts, and proves that the same package remains
available before T-10 as `LAST_KNOWN_GOOD_DEGRADED`; no `.bet-ready` marker is
created. No DNS bypass or stale-to-fresh relabelling was added. Full release
verification passed `1782 passed, 13 deselected in 119.67s`; Ruff passed.

## Drawing 4973 evening incident: fix 6, emergency-plan binding (2026-08-12)

The second emergency attempt failed because a new plan was manually rebuilt
without the original plan's `reviewed_catalog_hash`. The scheduler then
correctly rejected the canonical reviewed pins as unbound. Emergency recovery
must no longer reconstruct target, bank, probability, or evidence arguments.

`scheduler-recover-plan` now loads one current immutable source plan and clones
every field except the fresh output directory. The implementation uses
`dataclasses.replace`, so future plan fields are preserved by default rather
than maintained in a second manual copy list. Regressions compare every
dataclass field, verify CLI artifact generation, and prove that the exact
reviewed hash reaches the final child command. Against the real original 4973
plan, source plan, recovery plan, and command all retained
`7b789a9d0d4372ac7e6644af15b79612bdf4771944c8b88382044cf1f56b4469`.
Scheduler/CLI verification passed 160 tests. Full release verification passed
`1784 passed, 13 deselected in 110.98s`; Ruff passed.

## Drawing 4973 evening incident: fix 7, late final admission (2026-08-12)

The emergency direct final started at `13:45:57Z` with only about 197 seconds
left before the actionable publication cutoff. It nevertheless entered a full
calculation and finished 282.9 seconds later at `13:50:40Z`. The scheduler's
old 180-second minimum was below the measured workload, and the command runner
did not recheck that minimum after final-input capture.

New scheduler plans bind a 300-second minimum final runtime. The production
phase runner rechecks the remaining budget immediately after immutable input
capture and before spawning `run-drawing`. A scheduler-bound manual playable
`run-drawing` applies the same gate, so bypassing the wrapper cannot start a
known-too-late network/EV run. Exact T-16 admission remains possible only while
at least 300 seconds remain; input capture consuming that margin causes an
immediate LKG/`NO BET` path instead of late computation.
Scheduler/CLI/LKG verification passed 226 tests. The actual 4973 late-start
timestamp is rejected by the new bound before network access. Full release
verification passed `1786 passed, 13 deselected in 111.35s`; Ruff passed.

## Drawing 4973 evening incident: fix 8, post-deadline operator artifact (2026-08-12)

`reports/rehearsal/evening-4973-final-1644-package.txt` was manually created at
`16:59:32+03:00`, after the 16:50 T-10 boundary, outside the scheduler plan
directory and publication protocol. It was not a successful scheduler
publication. Existing atomic publication already rejects a final calculation
inside the reserve, removes late archives, and refuses package recovery after
T-10.

A real operator-surface gap nevertheless existed: a pre-deadline LKG
`baltbet-upload.txt` and its `operator-result.json` pointer remained visible
after a terminal `NO BET`, because the T-10 tick returned early for terminal
state. The T-10 tick now expires this non-actionable surface before the
terminal return: the upload text and current LKG pointer are deleted,
`operator-result.json` is replaced with coupon-free `NO_BET`, and the source
CSV is retained only for audit. Project instructions now forbid manually
constructing or displaying upload packages from research/expired artifacts.
Scheduler publication/LKG verification passed 189 tests. Full release
verification passed `1786 passed, 13 deselected in 111.71s`; Ruff passed.

## Drawing 4982 reviewed-schedule enrichment (2026-08-20)

Five unresolved kickoff times (event orders 4, 8, 11, 12 and 14) were frozen
in `data/reviewed-schedule/4982/` with exact official and independent public
source snapshots, checksums and a strict drawing/fingerprint-bound catalog.

Preparation now permits a newly supplied reviewed catalog to monotonically
upgrade an already-ready `totobrief-baseline` pin set. The upgrade is scoped
only to baseline-only event orders: previously validated provider or reviewed
pins are retained and are not re-admitted against unrelated schedule-date
diagnostics. Regression verification passed 23 mixed-provider/partial-
enrichment tests and 40 morning-dispatch tests; Ruff passed.

## Drawing 4982 live preparation and authorized scheduler (2026-08-20)

The immediate `morning-dispatch` path now loads `API_SPORTS_KEY` through its
configured protected `--env-file`, matching generated wrapper behavior instead
of requiring a separately exported shell variable. This is drawing-neutral.

Reviewed reusable aliases for the five previously unresolved fixtures allow
API-Sports to resolve them exactly. Preparation can now monotonically upgrade
an existing baseline-only canonical row to an exact provider pin while
preserving every unrelated pin hash. Production source contains no drawing
4982/12054 or team-name branch; the drawing-specific aliases and frozen source
evidence remain reusable data.

Live preparation is READY/PLAYABLE with 15 pins and zero unresolved events for
drawing 4982 (internal ID 12054, deadline 2026-08-21 19:00 MSK). Schema-v6 plan
`453829753fa55b5f` is activated for bank 4,980 and stake 30. Its generated and
installed LaunchAgent plists have identical SHA-256
`94359370a1cc82edb27ed6ddb67b148df7b0e970549193c797c0cfb50f5032e2`;
launchd reports zero prior runs before the first 17:00 MSK phase, and a direct
pre-phase wrapper smoke returned `no-op / no due scheduler phase`.

The exact plan has a hash-bound `EXPERIMENTAL_MANUAL` authorization through
T-10 at 18:50 MSK. Preflight reports
`experimental_manual_authorized`, package generation enabled, 15/15 pins and
zero unresolved events. A fresh final package that passes structural, safety,
identity and deadline checks may therefore become `PLAY`; insufficient
prospective sample alone no longer forces that authorized final to `NO BET`.
Profitability remains unproven and automatic wagering remains disabled. The
actual scheduled final/operator-export path is still pending live execution.

The read-only `preflight-status` output now includes a hash-verified
`evening_scheduler` block. It exposes every phase, attempt count, last reason,
next UTC/MSK checkpoint, overdue checkpoints and terminal state without
mutating the plan or generating a package. Against the live 4982 plan it
reports `waiting`, revision 0, no overdue checkpoints and next checkpoint
`tls_preflight` at 2026-08-21 17:00 MSK.

## API-Sports diagnostic observability (2026-08-24)

API-Sports now records a secret-safe per-request diagnostic contract: category,
endpoint path, attempt number, HTTP status, normalized provider error
code/message, and daily/minute quota limit, remaining, and reset metadata.
Known API keys, credential-like fields, URL queries, response headers, and raw
response payloads are excluded from diagnostic artifacts. Complex provider
error values collapse to a generic message instead of being serialized.

Schedule request attempts round-trip through the existing requested,
successful, and failed schedule-date JSON artifacts. Preparation attempts are
stored in the existing `readiness_summary.schedule_diagnostics` artifact.
Market failures retain the bounded sanitized final diagnostic in the existing
event fallback reason; successful market evidence continues to use its existing
endpoint/request-fingerprint source provenance and run-level quota fields.
There is no database column or migration for diagnostics, and collection
eligibility, matching, fallback, and fail-closed decisions are unchanged.

Verification was local and made no live provider request: the combined focused
suite passed `110 passed in 12.82s`; Ruff passed on all changed Python files and
`git diff --check` passed.

## Drawing 4987 conservative operational cutoff (2026-08-25)

TotoBrief drawing 4987 is stored as internal ID 12068 with 15/15 events and
`ended_at=2026-08-26T18:45:00Z` (21:45 MSK). GOAL API candidate collection
resolved 15/15 fixture identities; 12 kickoffs precede that field. Independent
Sofascore spot checks agreed with the sampled GOAL times. The earliest observed
kickoff is event 11 at `2026-08-26T15:45:00Z` (18:45 MSK), so the safe T-10
boundary is `2026-08-26T15:35:00Z` (18:35 MSK). Official BaltBet rules require
the package to be placed before the earliest event in the system.

Scheduler schema v7 now separates immutable TotoBrief `ended_at` identity from
`operational_cutoff`. A new hash-bound `conservative-cutoff.json` is derived
from the immutable candidate report and applies only
`min(ended_at, earliest_kickoff)`; it can never move the boundary later.
Unproven early cutoffs, later cutoffs, drawing drift, source-report drift and
legacy schema-v6 plans fail closed. All scheduler phases and passive retry
hard stops are based on the operational cutoff.

Morning source collection writes the cutoff evidence when qualifying
independent evidence exists. The same invocation immediately tightens and
rewrites an existing passive retry plan before LaunchAgent installation; later
morning runs automatically load the exact persisted artifact. This does not
promote candidate schedule rows into the canonical ledger, alter sports
probabilities, create a package or authorize a wager.

The 4987 dry-run retained source `ended_at=18:45Z`, used operational
cutoff `15:45Z`, and produced T-10 `15:35Z`; no scheduler was activated and no
package was generated. The evidence artifact is
`reports/canary/goal-api-4987/conservative-cutoff.json`.

Verification passed: `2021 passed, 13 deselected in 164.09s`; Ruff passed on
the full repository and `git diff --check` passed.

## Drawing 4987 morning automation control run (2026-08-25)

The installed generic morning dispatcher is now version v6. Its LaunchAgent
and generated candidate plist have identical SHA-256
`ec39d528c2f2e90c193bcce349243d0ebcb863acd93ec55a42d9a0a3d7fe1ee2`.
Launchd has the six Moscow checkpoints 08:00, 10:30, 12:00, 17:05, 17:12 and
17:20 plus the existing hourly interval; automatic betting remains disabled.

A live control collection for drawing 4987 completed rather than hanging.
GOAL found exact identities for 15/15 events and retained 846/1000 daily
requests; Sofascore supplied three candidates. Exact UEFA plus independent
Sofascore consensus promoted two reviewed schedule observations into the
append-only ledger. Thirteen events remain unresolved, so the result is
correctly `deferred` and an identity-bound passive retry LaunchAgent is active.
The persisted conservative cutoff remains 18:45 MSK with T-10 at 18:35 MSK.
Its first due attempt at 20:22 MSK completed normally with return code 2 and no
child run because no additional schedule evidence had become available; later
predeclared attempts remain loaded.

The control run exposed two generic defects which are now fixed. A normal
`deferred` result has dedicated exit code 75, and the generated recurring
wrapper treats it as a completed invocation instead of retrying the full
collector and spending provider quota. Identity drift remains terminal exit
code 3; other failures retain bounded retries. Schedule-evidence resolution
now skips individual source aliases whose scripts cannot produce a comparable
key, while retaining exact matching through supported aliases. It no longer
lets one Arabic or other unsupported alias crash the complete ledger lookup.

Final verification passed `2022 passed, 13 deselected in 162.24s`; Ruff and
`git diff --check` passed.

## Drawing 4987 retry-chain hardening (2026-08-25)

The first live v6 control exposed three sequential retry-chain defects rather
than a collector hang. They are fixed generically:

- a newly promoted consensus row now triggers one bounded re-preparation from
  the updated ledger before the final dispatch result;
- retry artifacts and an installed plist can be atomically replaced only for
  the same drawing ID/fingerprint label, with bootout/bootstrap when an
  independent dispatcher changes their bytes;
- passive runtime state accepts changed detail/review/cutoff evidence only for
  the same immutable drawing identity and an equal or earlier operational
  cutoff; a later cutoff still fails closed.

Retry plans now carry `runner_version=2` and every generated child command is
marked `--preflight-retry-child`. A retry child may refresh evidence and its
plan but cannot bootout/reinstall its own LaunchAgent. The independent generic
morning dispatcher owns installation and version upgrades. A same-cutoff
evidence refresh deliberately keeps the current retry schedule rather than
churning plist bytes.

The final live generic control exited once with code 0. It correctly reduced
4987 from 15 to 13 `timing_unknown` events, retained operational cutoff 18:45
MSK/T-10 18:35 MSK, persisted runner-v2 child markers, and installed a
hash-matching passive retry job. No evening package, operator upload or bet
marker was created. GOAL resolved all 13 remaining identities as candidate
data (12 earlier-time conflicts plus Bradford at the TotoBrief boundary), but
the provider remains candidate-only, so readiness is still deferred.

Latest full verification passed `2028 passed, 13 deselected in 170.19s`; the
subsequent retry-chain focused suite passed 86 tests and Ruff/diff checks.

The first scheduled runner-v2 attempt executed automatically at 21:13 MSK.
It completed once with retryable exit 75, persisted a structured 13/15
`timing_unknown` child result, left `retry_scheduler=null` inside the child,
and did not unload or reinstall itself. Post-run verification reports the
installed plist byte-identical, loaded and active, with next checkpoint 21:33
MSK. GOAL had 624/1000 daily requests remaining after the run. Final code
verification for this state passed `2029 passed, 13 deselected in 170.19s`;
Ruff and `git diff --check` passed.

## Drawing 4987 live recovery and evening readiness (2026-08-26)

The time resolver no longer treats TotoBrief `ended_at` as the earliest event
time. GOAL and Sofascore now share a bounded Moscow calendar window. A strict
GOAL-plus-Sofascore consensus lane promoted target-bound v2 schedule evidence;
legacy rows missing target competition remain audit-only. Monotonic ledger
growth now preserves exact observation identity while safely rebinding the
whole-ledger hash, and an artifact-free deferred morning record may advance to
that validated hash.

Live drawing 4987 is READY 15/15 with zero unresolved events. Schema-v7 plan
`f28e5483bcea337a` is loaded as LaunchAgent
`com.totoai.production-scheduler.v7.f28e5483bcea337a`. Operational cutoff is
18:45 MSK and T-10 is 18:35 MSK. The first checkpoint is 16:45 MSK, followed
by 17:15, 17:45, 18:00, 18:15, 18:25, 18:29 and 18:35. Automatic wagering is
disabled.

The morning training run exposed a stale provenance check that accepted only
scheduler schema v6. It now accepts exactly active schema v7 and has a
cross-module drift regression. The same frozen 4987 input then produced a
`STRUCTURAL_PASS` quality-v2 training package with 166 unique coupons, cost
4,980 and full bank use. It remains non-actionable `TRAINING_PAPER`.

Verification: targeted schedule/morning/provenance suites passed 91 and 52
tests respectively; the full default suite passed `2038 passed, 13 deselected`
in 183.62 seconds; full Ruff passed. The next required work is observing the
live evening checkpoints and validating the scheduler-owned terminal result.

## Drawing 4987 incident closure and drawing 4988 readiness (2026-08-26)

The 4987 evening run proved that schema-v7 parent phases were anchored to the
verified operational cutoff while their `run-drawing` children still waited on
the later TotoBrief identity `ended_at`. Warmup, refresh and final therefore
timed out. The child now receives the operational cutoff. Scheduler phases have
a T-60 true E2E canary, phase-specific admission/deadline budgets, bounded
timeout diagnostics and a plan-scoped verified schedule-only shared cache.
Market/probability payloads remain run-scoped and cannot be reused as fresh
final evidence.

Drawing 4988 (internal ID 12071) is prepared READY 15/15 with zero unresolved
events. Independent schedule work resolved St Gallen/Nordsjaelland and
Sitra/Malkiya, including conservative Latin compatibility folding. Its identity
`ended_at` is 2026-08-27 22:00 MSK; the verified operational cutoff is 19:00
MSK and T-10 is 18:50 MSK. Schema-v7 plan `095bea62149ea735` is generated but
not activated. The training result is `TRAINING_PAPER`, structural pass, 34
coupons / 1,020 RUB effective budget under the pool self-dilution cap; it is
not actionable.

A live rehearsal exposed a generic split-brain selector: morning dispatch had
correctly retired 4987 using its verified operational cutoff and selected 4988,
but production preflight re-selected the nearest page-one row by raw
`ended_at`, choosing 4987. Preflight now validates the exact immutable target
bound into the plan, and mandatory preparation uses that exact `drawing_id`
instead of `--open`. Missing, duplicate, drifted or no-longer-playable target
rows remain terminal fail-closed conditions.

An invalid local accelerated-clock drill wrote four future probability-history
timestamps into the 4988 preparation. The database was backed up, only those
four versions were removed, and the last real version was restored before a
fresh exact-ID preparation. Current evidence is real-time and READY 15/15.
Scheduler E2E phases must not be accelerated with a virtual parent clock while
children use wall time; production validation will occur only at the real
checkpoints.

Verification after these repairs: scheduler/runner/cutoff focused suite
`316 passed`; full default suite `2066 passed, 13 deselected` in 187.08 seconds;
full Ruff and `git diff --check` passed.

The 4988 plan is now activated as LaunchAgent
`com.totoai.production-scheduler.v7.095bea62149ea735`. A separate
`scheduler-preflight-only` command exercises the exact production preparation
and target-validation path before T-120 while forbidding training, package
generation, scheduler-state mutation and automatic wagering. Two live runs on
4988 passed; the public CLI run took about 36 seconds. A one-shot LaunchAgent
is loaded for 2026-08-27 16:00 MSK, one hour before the first evening
checkpoint, with results isolated below the plan's `daytime-preflight/` root.
The focused scheduler/runner regression passed `318 tests` and Ruff.

Sports analytics remains shadow/research-only. GOAL and Sofascore currently
affect schedule identity and kickoff evidence, not production probabilities.
The frozen GOAL-history adapter can compare equal-budget BK and sports-shadow
packages, but 4988 still needs a complete 15/15 GOAL fixture/team binding and
frozen team histories before that separate comparison can run. Production must
not silently switch from BK for 4988.

## Drawing 4987 settlement and Git home guard (2026-08-27)

The frozen equal-bank research packages for drawing 4987 were settled against
all 15 resolved results. The BK baseline reached at most 7/15 (mean 4.5602),
while the experimental GOAL sports shadow reached at most 5/15 (mean 3.3735).
Neither package, nor their 327-coupon unique union, reached 9/13/14/15. Baseline
had zero actual-outcome exposure in events 5, 9, 11 and 15; sports shadow had
zero exposure in events 5, 8, 9 and 11. The sports candidate remains strictly
`NOT_ACTIVATED`. Durable analysis is in
`research/drawing-4987-package-review.md`.

The recurring whole-home Git scan was traced to `/Users/turshevr/.git` making
`$HOME` a Git work tree. TotoAI now provides `scripts/project-git`, which pins
all project Git operations and rejects `ls-files` or repository overrides. A
tested user-local guard at `~/.local/bin/git`, placed first in login-shell PATH,
returns exit 64 for `status`/`ls-files` when the resolved repository root is
exactly `$HOME`, while allowing Git in nested repositories. The home repository
was not removed or modified.

## Drawing 4989 schedule closure and activation (2026-08-28)

The five previously unknown kickoff times are closed by exact target-bound
official-plus-independent reviewed evidence for Tenerife/Sporting Gijon,
Braunschweig/Hertha, Al Ittihad Alexandria/Ceramica, Galway/Shelbourne and
Dunfermline/Raith. Immutable source snapshots and the partial catalog are in
`data/reviewed-schedule/4989/`.

Preparation now permits an exact reviewed record during an explicit provider
`access`/`plan` outage, while still rejecting ambiguous identity, generic
transport/quota failures, an absent catalog event and evidence captured after
kickoff. Reviewed evidence may conservatively tighten an inaccurate later
TotoBrief deadline. Mixed schedule-ledger and reviewed-catalog pins use one
deterministic aggregate binding hash; every component hash remains validated.

Drawing 4989 is READY 15/15 with zero unresolved event orders. Operational
cutoff is 18:00 MSK, T-10 is 17:50 MSK, and schema-v8 plan
`ceaa292700dbb903` is loaded as LaunchAgent
`com.totoai.production-scheduler.v8.ceaa292700dbb903`. Checkpoints are 16:00,
16:30, 17:00, 17:15, 17:30, T-25 final at 17:35, retry at 17:44 and expiry at
17:50 MSK. The activation-time training package is a non-actionable
`STRUCTURAL_PASS`: 166 unique coupons, 4,980 RUB, full configured bank.
Automatic wagering remains disabled and profitability is not proven.

The optional GOAL sports-shadow capture failed closed because its report did
not bind all 15 event orders. It did not affect preparation, scheduler
activation or production probabilities. Verification passed `2090 passed, 13
deselected`; full Ruff and `git diff --check` passed.

## COVER_14_BK_FILL core (2026-08-28)

The equal-input research layer now has a deterministic
`COVER_14_BK_FILL` adapter. It preserves every coupon in the exact verified
TotoBrief-style Cover-14 package, then fills the remaining dynamic capacity
`bank // stake` with unique coupons in descending joint BK probability. The
Cover-14 brief and guarantee remain attached to the result, the full configured
bank is used, and exact P13/P14/P15 are recomputed for the combined package.
Focused tests cover 4,980/30 (166 coupons) and 9,960/30 (332 coupons), preserve
the Cover subset and verify no loss of modeled P13 relative to unfilled Cover.
The adapter is research-only and is not yet wired into scheduler selection.

It is now included as the fifth strategy in the shared equal-input comparison
bundle and report set. Strict and legacy benchmark scoring/report cardinality
has been updated from four to five strategies; legacy checkpoint schema is v4
so incompatible four-strategy checkpoints fail closed. The comparison remains
paper-only and does not change scheduler selection or operator output. Focused
strategy/strict/legacy verification passed 23 tests and Ruff.

The first drawing-4989 activation-input comparison completed at bank/stake
4,980/30. Modeled P13 was 0.00326133 for current EV/crowd, 0.01112910 for
BK-only and 0.01243595 for `COVER_14_BK_FILL`. The challenger is approximately
3.81x current EV/crowd and 11.74% above BK-only on P13, while BK-only remains
slightly higher on P14 and higher on P15. This is one pre-outcome paper
snapshot, not a profitability verdict. Durable details are in
`research/drawing-4989-preliminary-strategy-comparison.md`.

## Drawing 4989 category-hit selector migration (2026-08-28)

The main 15-event safety-aware selector now uses protocol
`quality-v2-category-hit-hybrid-v2`. Its seed preserves an exact Cover-14 core,
allocates BK-based fill marginals inside the existing exposure/headroom bounds,
and then runs the unchanged P13/P14/P15-first local optimizer. A raw BK fill
was correctly rejected by production safety; the bounded fill fixed that
failure without disabling any gate.

On the exact frozen 4989 activation input, an artifact-bound selector canary
completed in 86.34 seconds with `STRUCTURAL_PASS`, 166 unique coupons, cost
4,980, zero headroom violations and modeled probabilities P13 0.01157973,
P14 0.00112965 and P15 0.00004832. The old EV/crowd P13 on the same input was
0.00326133. Profitability is still unproven.

Focused verification passed 191 scheduler/runner tests and 90
strategy/package tests. The full default suite passes `2096 passed, 13
deselected`; Ruff and `git diff --check` pass. The old active plan
`ceaa292700dbb903` is intentionally incompatible with protocol v2 and must be
superseded by a regenerated, verified drawing-4989 plan before the 16:00 MSK
checkpoint. No scheduler checkpoint has run yet.

The refreshed frozen heavy regressions also passed after explicit golden
review. New versus old quality-v2 best hits were 12 vs 7 on 4967, 9 vs 9 on
4969 and 10 vs 9 on 4970. Mean hits improved on 4967 and 4970 but declined on
4969. This supports the experimental category-hit direction but remains only
three retrospective drawings and does not prove profitability.

## Drawing 4989 live evening run (2026-08-28)

Active schema-v8 plan `e27c56d2ef849b11` is loaded as LaunchAgent
`com.totoai.production-scheduler.v8.e27c56d2ef849b11`. TLS and API preflights
completed. The 17:00 freshness preflight exposed an invalid comparison between
the complete reviewed-catalog semantic hash and the selected-evidence pin-set
hash. Those are different hash domains; the runner now binds the catalog bytes
and verifies the selected hash through canonical pin loading without comparing
the two values. A regression test covers the distinction.

The fix passed 246 scheduler/runner tests, the complete suite passes
`2102 passed, 13 deselected`, and Ruff passes. The real 17:15 warmup then
completed successfully with the 15/15 prepared pin set. The live watcher
remains active through refresh, final, sports sidecar, retry and T-10.

## Drawing 4989 incident closure and drawing 4990 readiness (2026-08-28)

Drawing 4989 did not produce a scheduler-owned operator package before T-10.
Two explicit post-deadline research packages were generated only for diagnosis:
BK baseline and GOAL sports-shadow, each 166 coupons / 4,980 RUB and both
`PAPER_ONLY_NOT_ACTIVATED`. They are not valid BaltBet upload artifacts.

The incident exposed and fixed four generic defects:

- complete reviewed-catalog hashes are no longer compared with selected-pin
  hashes from a different semantic domain;
- reviewed evidence stays fresh for 24 hours, which covers an evening review
  through the following next-day final window while still expiring before a
  later drawing;
- scheduler schema v9 moves heavy work to T-60/T-50/T-40/T-30, keeps a T-18
  retry and T-10 hard boundary, and rejects impossible schema-v8 runtime
  windows;
- pre-final `NO BET` without a package is retryable rather than falsely
  complete, and a successful READY dispatch removes its obsolete preflight
  retry LaunchAgent.

The baseline/category-hit bridge also failed closed when a low effective
budget produced only a partial Cover-14 result. `build_baseline_brief` now
accepts only verifier-confirmed exact category covers and falls back to the
narrowest affordable exact brief; partial cover cannot seed the production
quality selector.

Drawing 4990 (internal ID 12077) is READY 15/15. The final missing kickoff,
Blackburn Rovers versus Queens Park Rangers, is bound to reviewed official plus
independent snapshot evidence at 2026-08-29 14:00 UTC. Operational cutoff is
2026-08-29 16:30 MSK and T-10 is 16:20 MSK. Schema-v9 plan
`3a9fa3fe29a2290b` is loaded as
`com.totoai.production-scheduler.v9.3a9fa3fe29a2290b`; its heavy checkpoints
are 15:30, 15:40, 15:50 and 16:00 MSK, retry 16:12 and hard boundary 16:20.
The obsolete preflight retry is unloaded and no stray TotoAI process remains.

A scheduler-bound 4990 training run now reaches `STRUCTURAL_PASS`. The current
small pool invokes the one-percent self-dilution cap, so the preliminary
effective budget is only 480 RUB / 16 coupons; this is not the final package
and will be recomputed from the fresh final pool. Profitability remains
unproven and automatic wagering remains disabled.

- Full verification for this change set: `2110 passed, 13 deselected`; `ruff check .` passed.
