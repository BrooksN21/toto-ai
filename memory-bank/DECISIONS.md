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
- API-Sports event matching is deterministic and fail-closed. Only one exact
  sport/home/away/team match inside the approved UTC time window is usable;
  fuzzy matches are diagnostic only and ambiguous matches always fall back.
- External odds must be complete full-time football or regulation-time hockey
  `1/X/2` markets. Two-outcome hockey moneylines must never be mapped to Toto
  three-way outcomes.
- Initial external consensus requires three eligible bookmakers, applies
  multiplicative de-vig per bookmaker, then normalizes component-wise median
  probabilities. The initial maximum odds age is 36 hours and remains visible
  in provenance and coverage reports.
- External probabilities cannot affect `PLAY` during the coverage audit. Every
  one of the 15 events records either an eligible external consensus or an
  explicit TotoBrief BK fallback reason.
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
