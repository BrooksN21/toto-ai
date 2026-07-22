# Decisions

- Use repository memory instead of relying on chat memory.
- This memory bank is project-local to TotoAI and must never be mixed with
  local skills, personal knowledge bases, team knowledge bases, or unrelated
  external memory stores.
- Project knowledge is stored in repository directories:
  - `memory-bank/` for project state and durable decisions.
  - `knowledge/` for domain notes grounded in implemented repository state.
  - `skills/` for project-local workflow checklists.
  - `prompts/` for reusable project prompt templates.
- After every completed feature, update the project knowledge base first.
- One task, one commit, one verification cycle.
- Every hypothesis must be backtested.
- Never claim guaranteed profit.
- Separate prediction quality from cover quality.
- The completed BK-only experiments used `13+` hit rate as their fixed primary
  objective. The next optimizer changes the primary objective to modeled
  monetary expected value under a dynamic user bank.
- The bank may be any positive amount exactly divisible by the configurable
  coupon stake. The optimizer does not force full-bank utilization.
- The Expected-Value Package Engine evaluates all `3^15` coupons. Performance
  optimization may not truncate its candidate space or alter exact rankings
  beyond a documented floating-point tolerance.
- EV research and playable recommendations are separate modes. Research always
  shows top coupons; playable mode uses an explicit threshold and returns
  `NO BET` when no coupon qualifies. It never lowers the threshold merely to
  force a package.
- Initial crowd joint probabilities use an explicitly disclosed independence
  model derived from pool marginals. This is an assumption requiring stress
  tests, not an observed property of player tickets.
- Historical modeled ROI is not observed ROI because category payouts and
  winner counts are not present in the current data. Profitability claims
  require prospective validation with lawful payout data.
- Direct Pinnacle access and prohibited scraping are out of scope. External
  odds use a provider-neutral, event-level interface with TotoBrief BK fallback
  so missing external matches do not silently drop a drawing.
- External odds collection starts on API-Sports' free football and hockey plans.
  A paid plan up to 30 USD/month is a last resort after a prospective audit
  proves request quota, rather than provider coverage, is the limiting factor.
- API-Sports event matching is deterministic and fail-closed. Exact matching
  remains first and may use primary TotoBrief names, optional `name_en`
  alternatives, and reviewed versioned aliases. When both English names are
  absent and both target names are Cyrillic, matcher v4 may consume one
  high-confidence transliterated same-or-reversed pair: pair score >= 0.74,
  both team scores >= 0.55, and margin over the runner-up >= 0.15. Existing
  sport and known-time restrictions still apply. Generic fuzzy suggestions
  remain diagnostic-only; low-margin, low-score, and ambiguous matches always
  fall back. Alias files remain deterministic and reject normalized-key or
  canonical-value collisions and cycles.
- External odds must be complete full-time football or regulation-time hockey
  `1/X/2` markets. Two-outcome hockey moneylines must never be mapped to Toto
  three-way outcomes. Exact `Home`/`Draw`/`Away` outcome-label validation is
  applied only after a market name matches the existing semantic allow-list;
  unrelated markets remain ineligible diagnostics and do not abort the event.
- Initial external consensus requires three eligible bookmakers, applies
  multiplicative de-vig per bookmaker, then normalizes component-wise median
  probabilities. The initial maximum odds age is 36 hours and remains visible
  in provenance and coverage reports.
- External probabilities cannot affect `PLAY` during the coverage audit. Every
  one of the 15 events records either an eligible external consensus or an
  explicit TotoBrief BK fallback reason.
- External odds collection snapshots are append-only and immutable. The
  deterministic collection identity includes the canonical drawing target,
  the fresh TotoBrief target `target_fetched_at`, the external observation
  `fetched_at`, provider matching decisions and market payload provenance,
  request/cache counters, observed quota state, and consensus configuration.
  Saving the same canonical collection is idempotent; operationally distinct
  retry passes receive distinct identities, and conflicting content under the
  same identity is rejected.
- External odds consensus age and future-update checks use the explicit
  external observation time, not the earlier TotoBrief target fetch time. The
  observation time must be at least as late as every consumed provider market
  fetch timestamp.
- API-Sports schedule endpoints use one unpaged request per date and must report
  `paging.current = paging.total = 1`; the live fixtures endpoint rejects a
  `page` parameter. Odds pagination remains explicit and fail-closed. Exact
  duplicate provider records may be deduplicated, while conflicting duplicate
  identifiers remain an error.
- Official API-Sports response envelopes do not provide a top-level observation
  timestamp. The client records its UTC receipt time in cache schema v2 and
  reuses that exact time on cache hits without mutating the raw provider payload.
- TotoBrief may return `start_at = null` for every event in an open drawing. A
  missing target time searches the approved progressively expanded schedule;
  a known target time still requires the existing three-hour UTC window. The
  accepted exact or constrained matcher-v4 pair may have the same or reversed
  home/away orientation. Reversed consensus swaps `1` and `2` into TotoBrief
  orientation while raw provider quotes stay in provider orientation.
  Orientation is persisted and reported; multiple or low-confidence candidates
  fail closed.
- `quota_reserve` protects the API-Sports daily request allowance. The minute
  counter blocks only at zero. Cached historical quota headers are provenance,
  not current operational quota, and must not block a fresh client request.
- API-Sports request accounting reports actual HTTP attempts, including retry
  attempts and additional pages. Cache hits and logical fetch calls are tracked
  separately and must not be reported as requests.
- Safe-runner T-5 enforcement is propagated through prospective collection to
  every schedule date/page, event-market request/page, and API-Sports transport
  retry. Closure completes the immutable pass with explicit safety-stop
  fallbacks and permits no later provider call.
- Prospective API-Sports collection is fresh by default. Each CLI invocation
  uses a unique cache-session directory, pins one TotoBrief target before any
  provider pass, and creates a new provider client per pass while reusing that
  invocation's cache. The defaults are three passes and 65 seconds between
  retries. Only quota reserve, provider schedule failure, and provider odds
  failure are retryable. Shared-cache behavior requires explicit
  `--reuse-cache`; stale cache must never masquerade as a new observation.
- Safe-runner preflight computes all possible coverage, EV, and runner paths
  after target pinning and before waiting. Lexical and symlink collisions with
  the database, aliases, cache root, or sibling outputs fail before provider
  construction; report/cache writability is probed and the guard repeats at
  publication.
- Safe-runner publication is the final deadline-aware phase. Actionable child
  and runner artifacts are covered by one transaction until commit; every
  pre-commit `BaseException` restores/removes all artifacts, and an already
  committed publication is command success. Runner `NO BET` never links an EV
  child report or coupon strings.
- The second fresh EV payload is compared with the expected `PinnedDrawing`
  before timing or EV computation. Expected target mutation is a valid
  zero-cost target-mismatch `NO BET` with `ev_run=None`; structurally corrupt
  results remain command failures.
- Rare holiday and off-season drawings may span up to five days. Missing-start
  external collection will use progressive two-to-five-day schedule expansion
  rather than querying five days for every normal drawing. A playable drawing
  must have effective start times for all 15 events and an inclusive
  Europe/Moscow calendar span of at most two days. `multi_day` and `unknown`
  eligibility are fail-closed `NO BET`; provider timing metadata may veto PLAY
  but external probabilities remain audit-only.
- Playable EV output requires an exact stored eligibility match for the same
  fresh target fingerprint and status `playable`. `multi_day`, `unknown`,
  `absent`, and `not_checked` all suppress package and sensitivity output to a
  zero-cost `NO BET`. Exact diagnostic coupons are not published after this
  veto. Research preserves EV computation and ranking while reporting timing
  provenance or a conservative timing warning.
- Provider provenance is stored explicitly, not only committed through an
  opaque event hash. Matched dispositions retain schedule-event fetch time and
  payload hash plus candidate IDs and match reason; quotes retain market fetch
  time and payload hash. Collection identity binds all of these fields.
- Quote records are ordered canonically before collection identity, storage
  comparison, insertion, and load. Provider response order is not data and
  cannot create a different immutable collection.
- The unique quote key remains `(collection_id, event_order, bookmaker_id,
  market_name)`. Multiple assessments with the same exact key remain rejected
  by consensus and are coalesced into one ineligible anomaly row. That row
  stores every source market in canonical provenance and uses a deterministic
  aggregate payload hash, so duplicates neither disappear nor abort the
  15-event transaction.
- Prospective external collection must never silently drop events. Unknown
  sports, missing or ambiguous matches, provider failures, quota exhaustion,
  stale or partial markets, and minimum-bookmaker consensus failures all retain
  the TotoBrief BK triplet with an explicit fallback reason in the event
  disposition.
- Direct package optimization is evaluated before further brief-first
  heuristics. A brief may be derived from a package but does not constrain the
  v1 optimizer.
- Direct Package Optimizer v1 uses only pre-drawing BK probabilities. External
  providers and payout optimization follow only after a fixed baseline test.
- Direct strategy experiments require a manifest frozen before evaluation. The
  manifest records exact drawing IDs, protocol/data hashes, and a clean Git code
  version; evaluation rejects protocol, data, or code-version mismatch.
- A frozen strategy manifest may be reused for bank sensitivity only. Other
  strategy/protocol settings must remain unchanged.
- Historical result data is included in the experiment data hash but is not
  available to package generation.
- The first frozen 500-drawing retrospective experiment found no statistically
  proven strategy winner. Weighted coverage must not be called superior based
  on its higher average best-hit count alone.
- Do not tune against the 150-drawing frozen holdout. Diagnose and select
  changes on development data, then use a newly frozen prospective or otherwise
  untouched evaluation window.
- The Hybrid Direct Package experiment tests only top-core fractions 0.50,
  0.75, and 0.90 at the frozen 5000 RUB / 30 RUB / category 13 protocol.
- Hybrid GO requires at least two additional development 13+ hits over
  top-probability, no worse 13+ results in at least four of five chronological
  folds, no lower average best hits, and zero operational failures. Otherwise
  the optimizer direction stops and the project moves to external data and
  payout/ROI modeling.
- Hybrid evaluation requires a development-only seal derived from the frozen
  manifest, the development prefix of the frozen backtest CSV, and a read-only
  database. Separate SHA-256 hashes bind canonical CSV rows, pre-drawing
  development inputs, development results, and the fixed hybrid protocol.
- Hybrid pre-drawing input seals include drawing number, ordered event IDs and
  event order, and pool/BK values without results. Evaluation verifies CSV,
  protocol, and input seals before loading any result; it accumulates the
  result seal only after each drawing's top package hash passes.
- Hybrid seals require a clean Git code version, reject collisions between
  source/database/output paths, and publish the development CSV and manifest as
  a rollback-safe pair.
- Hybrid evaluation resolves its deterministic report paths before opening the
  database and rejects any collision with the sealed manifest, development CSV,
  or database.
- The hybrid per-drawing deadline covers every package-generation stage.
  Timed-out selectors do not perform exact coverage after expiry, and any stage
  overrun fails the evaluation before reports are written.
- The sealed hybrid development experiment returned STOP: core fractions 0.50,
  0.75, and 0.90 added -2, -1, and 0 observed 13+ hits respectively versus
  top-probability, despite improving average best hits and having zero
  operational failures. The sealed rerun exactly reproduced the initial
  metrics, used zero holdout IDs, and is the final decision for this direction.
- Further tuning of the BK-only direct package optimizer is closed. The next
  research direction is the Expected-Value Package Engine plus a
  provider-neutral external-probability interface. Any later optimizer work
  needs a new hypothesis and a new untouched evaluation window.
- Budget-constrained oracle commands may use actual results only as benchmark
  upper bounds; they must not be treated as playable prediction methods.
- Budget-oracle must not reduce the candidate search space by default. Candidate
  limits only apply when explicitly requested.
- Budget-oracle drawing timeouts keep the best candidate found so far and should
  not fail the whole run.
- Budget-oracle workload profiling is observational only. It must not change
  oracle candidate generation, candidate order, scoring, or default search
  space.
- Budget-oracle pruning must be mathematically safe and match exhaustive
  evaluation in regression tests.
- Budget-oracle incumbent pruning may skip a candidate only when its maximum
  possible hit count is strictly below the incumbent's actual hit count.
- Dominance pruning is disabled until equivalence with exhaustive evaluation is
  proven. Its previous subset rule changed oracle hit metrics.
- A full-cover coupon-cost lower bound must not prune Budget Oracle candidates:
  the oracle objective evaluates useful partial packages under budget.
- Category 13 means maximum Hamming distance 2.
- Category 14 means maximum Hamming distance 1.
- Category 15 means exact match.
- Cover guarantee only applies if actual outcomes are inside the selected brief.
- Cover Engine performance optimizations must preserve selected coupons,
  coverage rate, worst minimum distance, and guarantee results.
- Cover Engine caches may depend on brief structure and category, but must not
  change candidate order or greedy tie-break semantics.
- Strategy package diagnostics use sorted coupon log probabilities and exact
  pairwise Hamming distances for deterministic structural metrics. Package
  overlap uses set intersection/union; mean unique-coupon log probability is
  unavailable when its unique set is empty.
- User bank can be any positive amount exactly divisible by the configured
  stake.
- `--open` means next playable drawing with `ended_at` in the future.
- `--live` means betting is closed and drawing is ongoing.
- `--latest-finished` is for historical analysis.
- Internal drawing ID differs from visible drawing number.
- Multi-day timing acceptance is deterministic and must forbid real network
  calls and sleeps. A lawful live dry run is optional operational evidence, not
  a prerequisite for accepting the collection-to-eligibility-to-veto boundary.
- The production `run-drawing --open` workflow preflights and pins one exact
  target, waits until T-20, revalidates that same target, then runs fresh
  collection, exact stored timing, diagnostic coverage audit, existing EV, and
  rollback-safe linked reports. It never submits a bet. T-5 forbids new work
  and suppresses any package that completes at or after the cutoff.
- Historical/current operational replay is an explicit `run-drawing
  --offline-replay` mode, not an environment switch and not scheduler input.
  It requires exact target/schedule cache envelopes and an aware injected
  as-of time, validates payload hashes and drawing/provider/event identity,
  and never falls back to network clients or process credentials.
- Offline replay is permanently research-only even if diagnostic EV is
  computed. It writes only runner JSON/Markdown with additive manifest-v4
  `replay` provenance (`actionable=false`, as-of, provider, cache paths and
  hashes). Scheduler parsing rejects non-null replay provenance, so a replay
  cannot authorize PLAY or publish a production package. Full scheduler
  execution classifies it as non-production `ignored`, writes status only, and
  creates no terminal marker; malformed production manifests still create
  `.failed`.
- Replay mutable state requires an explicit isolation capability:
  `--replay-root`. SQLite, reports, provider cache, and temporary files derive
  below it. Live defaults are resolved only after the replay branch. Output
  overrides must remain strictly contained; repository/live-root overlap and
  symlink traversal are rejected before any directory or database is created.
- Equal external observation timestamps do not define collection chronology.
  SQLite latest-snapshot reads use append order as the deterministic tie-break
  before collection-ID order, preserving a later progressive pass without
  changing immutable collection identities or timing definitions.
- Runner manifest schema v2 makes every terminal artifact carry a structured
  `ev` object and package summary. Schema v1 used `ev: null` when package
  computation did not run and did not provide this contract. In v2, when package
  computation is skipped or suppressed, the summary is canonical zero-cost
  `NO BET`: no coupons, zero selected count/cost/payout, full unused bank, and
  unavailable modeled ROI. This is report evidence only and changes no EV or
  package-selection definition.

- Drawing-4950 boundary is defined by strict fail-closed rules: `7/15` raw matches are validly fail-closed without aliases; reviewed aliases may raise the resolved set but unresolved targets are preserved as missing. Two unresolved provider events are not coerced into synthetic matches.
- Exact timing provenance is now required for production decisions. The runner uses `PlayTimingEligibility` as raw and effective pair; only a reviewed timing overlay with exact catalog hash/provenance parity can change effective timing. Any unverified, invalid, or catalog-changed override drives effective timing to `unknown`.
- Runner manifests and scheduler ingestion are strict:
  - current manifest must be `schema_version = 4` and include exact
    `raw`/`effective` timing payloads plus an authoritative
    `pinned_revalidation` summary; schema v3 remains historical only;
  - manifest and package inputs are path-safe and hash-checked (`package_sha256`, timing catalog hashes, manifest manifest fields);
  - strict JSON parsing rejects duplicate keys, non-finite numbers, non-JSON, and symlink/collision hazards.
- Self-dilution budget is exact and authoritative for package budget math: `requested_cap = min(requested_bank, floor(pool_sum*1% / stake) * stake)`, and `effective_budget` follows that cap before EV sensitivity and selection.
- `drawing 4947`/legacy `drawing 4950` `schema_version = 2` runner outputs are historical; they are not a source of current production truth.

## Systematic Team Identity and Preparation

- A production drawing is actionable only when its exact target fingerprint,
  provider, and event IDs have one `ready` preparation and exactly 15 valid,
  fixture-unique pins. Pins carry provider fixture/team IDs and `starts_at`.
- Preparation publication is atomic. An unresolved attempt writes diagnostics
  and review records but zero authoritative pins. A later complete retry may
  replace unresolved state with one transactional ready version. Ready content
  is immutable; changed provider data requires invalidation/new fingerprint or
  fails closed.
- Reviewed aliases and exact provider-team IDs outrank inferred evidence.
  Normalization and transliteration never authorize a match by themselves.
  Non-registry acceptance requires date, competition/country/league context,
  home-away orientation, pair uniqueness, one exact/high-confidence side, and
  confidence margin. Two weak shared-token names remain unresolved.
- Team aliases are scoped by sport, provider, normalized alias, country, and
  competition context. Context-free Phase-1 aliases remain compatible only
  when lookup is unambiguous; SQLite initialization migrates existing rows
  using their canonical team context.
- The production runner defaults to systematic pins. Legacy name matching is
  an explicit direct-command compatibility option and is never inherited by
  scheduler execution.
- Final collection revalidates pinned provider fixture ID, team IDs, start
  time, provider, and schedule freshness. Display-name differences are ignored
  after pinning; unavailable, absent, stale, or changed identity data is a
  fail-closed outcome, not a reason to rematch names.
- Playable work is gated before timing/audit/EV on exactly 15 successful pin
  revalidations. The same provider, fixture ID, oriented home/away team IDs,
  bounded start-time tolerance, fresh schedule, and complete required-date
  fetches are all mandatory. TotoBrief BK fallback is diagnostic only after
  any pin-revalidation failure.
- Schedule preparation expands null starts progressively by UTC dates derived
  from the Moscow drawing horizon. Each date is isolated, successful dates are
  retained, API client cache/retry/quota behavior is reused, and diagnostics
  preserve each failed date's reason. Any failed required date in the bounded
  eligible window prevents READY and transactional pin publication.
- Preparation derives conservative sport/country/competition/league context
  directly from TotoBrief championship text. Local normalization may map
  stable geographic exonyms, but no network translation or team-specific
  alias may supply identity. Conflicting country, league level, date, sport, or
  orientation fails closed in the production path.
- Drawing numbers, current team names, and provider fixture IDs are test replay
  data only. Production resolution contains no drawing-4951 or per-team branch.
