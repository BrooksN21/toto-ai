# Audit: drawing 4971 training package

Task: `TOTOAI-AUDIT-4971-PACKAGE-20260810`
Scope: read-only local audit of the training manifest, selector diagnostics,
CSV/TXT package, selector implementation, and tests. No code, database,
scheduler, VCS, or betting action was performed.

## Verdict

**The package is internally consistent as a non-actionable training artifact,
but it is not acceptable evidence for real-money use.** The strongest blockers
are the one-coupon material floor and its discontinuous 20% threshold, extreme
clustering and cap-bound exposure, a single early/mis-timestamped probability
snapshot, incomplete package-bound diagnostics, and an unvalidated payout/
crowd proxy that reports implausibly large modeled returns. `PLAY` here means
only that the current mechanical gate passed; the manifest itself correctly
says `artifact_class=TRAINING`, `actionable=false`,
`production_publication=null`, and `bet_placement=null`.

## Artifact integrity

- CSV and TXT both contain 166 identical, ordered, unique 15-token coupons.
- Package cost is `166 * 30 = 4,980 RUB`.
- Canonical package SHA-256 is
  `3f3c6a5033a2c504d7c85e129271e655c299db312220088e0a8eadc40574302e`
  everywhere it is expected.
- File hashes in the manifest match the files. The frozen input and isolated
  DB hashes also match.
- CSV gross-EV sum is `2161.422527431040`; multiplied by 30 RUB it reproduces
  expected payout `64,842.6758229312` and modeled ROI `12.0206176351`
  (1,202.06%). This is modeled output, not observed payout or profitability.
- Selected complete-ranking positions range from 1 to 30,118. Of the package,
  146 coupons remain in ranks 1..166 and 20 are repair substitutions.
- The selector examined 32,768 candidates out of 13,949,503 eligible coupons:
  `0.2349%` of eligible coupons. It is not exhaustive and not a global integer
  optimum. It is a deterministic repair plus one-swap local improvement.
- Safety repair reduced modeled expected payout by `2,349.786986 RUB`, from
  `67,192.462809` to `64,842.675823` (`-3.4971%`).
- The packaged `selector-pre-post-diagnostics.json` is incomplete compared
  with the in-memory diagnostics model. It omits all 15 pre/post exposure rows,
  `required_coupon_count`, `candidate_universe_exhaustive`,
  `constraint_feasible`, and `infeasibility_reasons`. The unmanifested
  `direct-selector-diagnostic.json` contains these fields. The packaged file
  also has no schema version.
- The manifest does not bind a source revision, dependency/runtime identity,
  selector constants/tie tolerances, package creation timestamp, or manifest
  self-hash. Absolute local paths make it non-portable.
- `rehearsal.stderr.log` retains a `KeyboardInterrupt` traceback from an
  earlier attempt while the final exit file is 0. Attempts are not separated
  or reconciled in the manifest.

## All 45 post-selection exposures

`q` is the frozen TotoBrief BK probability. `slack` is distance from the
integer cap 157; count 158 would fail the 95% safety boundary.

| Event | 1 count/share; q | X count/share; q | 2 count/share; q | max | slack |
|---:|---:|---:|---:|---:|---:|
| 1 | 157 / 94.58%; 30.00% | 1 / 0.60%; 28.00% | 8 / 4.82%; 42.00% | 157 | 0 |
| 2 | 1 / 0.60%; 28.71% | 8 / 4.82%; 32.67% | 157 / 94.58%; 38.61% | 157 | 0 |
| 3 | 1 / 0.60%; 36.00% | 8 / 4.82%; 32.00% | 157 / 94.58%; 32.00% | 157 | 0 |
| 4 | 1 / 0.60%; 26.00% | 153 / 92.17%; 26.00% | 12 / 7.23%; 48.00% | 153 | 4 |
| 5 | 1 / 0.60%; 37.00% | 71 / 42.77%; 26.00% | 94 / 56.63%; 37.00% | 94 | 63 |
| 6 | 1 / 0.60%; 44.00% | 32 / 19.28%; 28.00% | 133 / 80.12%; 28.00% | 133 | 24 |
| 7 | 157 / 94.58%; 29.00% | 8 / 4.82%; 26.00% | 1 / 0.60%; 45.00% | 157 | 0 |
| 8 | 48 / 28.92%; 42.00% | 13 / 7.83%; 27.00% | 105 / 63.25%; 31.00% | 105 | 52 |
| 9 | 117 / 70.48%; 39.00% | 20 / 12.05%; 29.00% | 29 / 17.47%; 32.00% | 117 | 40 |
| 10 | 1 / 0.60%; 43.00% | 20 / 12.05%; 26.00% | 145 / 87.35%; 31.00% | 145 | 12 |
| 11 | 157 / 94.58%; 37.00% | 8 / 4.82%; 30.00% | 1 / 0.60%; 33.00% | 157 | 0 |
| 12 | 157 / 94.58%; 35.35% | 1 / 0.60%; 21.21% | 8 / 4.82%; 43.43% | 157 | 0 |
| 13 | 5 / 3.01%; 41.41% | 4 / 2.41%; 26.26% | 157 / 94.58%; 32.32% | 157 | 0 |
| 14 | 90 / 54.22%; 34.00% | 1 / 0.60%; 32.00% | 75 / 45.18%; 34.00% | 90 | 67 |
| 15 | 44 / 26.51%; 35.00% | 1 / 0.60%; 30.00% | 121 / 72.89%; 35.00% | 121 | 36 |

Token summary:

- All 45 event/outcome cells are nonzero, across 2,490 coupon tokens.
- Twelve cells have exactly one token (`1/166 = 0.6024%`). Their frozen
  probabilities range from 21.21% to 45%. Particularly severe examples are
  E7-2: 45% probability but one coupon, E6-1: 44% but one coupon, and E10-1:
  43% but one coupon.
- Twenty of 45 cells have at most eight tokens.
- Seven events are exactly at the cap: 1, 2, 3, 7, 11, 12, and 13. Event 4 is
  only four coupons below it. Thus the package passes with no integer safety
  margin on almost half the events.
- Event-level total-variation distance between package exposure shares and
  frozen `q` averages `0.5145` and reaches `0.6617`. Exposure need not match
  `q` under an EV strategy, but this quantifies how little the current
  nonzero-floor gate controls directional risk.

## Is the 1/166 material floor too weak?

**Yes.** It proves only token presence, not meaningful risk coverage. It lets a
45% result receive 0.60% of stake while a 29% result receives 94.58%. The final
safety evaluator checks only:

1. no share is `>= 0.95`;
2. a completely fixed outcome is not below the low-probability threshold; and
3. an outcome with `q >= 0.20` is not absent.

There is a discontinuity at 20%: 19.9% may receive zero coupons, while 20.0%
must receive only one. A complete selector rerun that changed E12-X from
21.2121% to 19.9% (transferring 1.3121 percentage points to E12-2) changed 11
of 166 coupons, changed the package hash, and assigned E12-X zero exposure.
The run still returned `PLAY`. This is direct evidence that the threshold/floor
combination is brittle.

No arbitrary replacement floor should be declared safe without evidence.
Before real money, minimum and maximum exposure rules need an explicitly
approved, stress-tested relationship to probability, bank size, and target
loss/category risk, plus positive margin from both bounds.

## Hamming diversity and clustering

There are 13,695 unordered coupon pairs.

- Pairwise Hamming distance: min 1, median 4, mean `3.7993`, max 8.
- Pair counts: d1=444, d2=1,622, d3=3,497, d4=4,182, d5=2,782,
  d6=978, d7=174, d8=16.
- `15.09%` of all pairs are at distance <=2 and `40.62%` at distance <=3.
- Nearest-neighbor distance is 1 for 163/166 coupons and 2 for the other 3.
- At distance-1 graph connectivity, 163 coupons form one component and three
  are singletons. At distance 2 all 166 are one connected component.
- Modal coupon is `122X22121211212`. 76/166 coupons (45.78%) are within
  distance 2 and 137/166 (82.53%) within distance 3 of it.

Safety repair modestly increased mean pair distance from 3.6283 to 3.7993, but
did not create a diversified package. There is no diversity term or category-
union term in the selector objective.

## Category coverage under the frozen independent-q model

These are exact probabilities that **at least one** package coupon reaches the
category, computed over all `3^15` outcomes. They are diagnostic model outputs,
not predictions validated against results.

| Package | P(9+) | P(13+) | P(14+) | P(15) |
|---|---:|---:|---:|---:|
| Pre-repair top 166 | 27.5684% | 0.165291% | 0.017049% | 0.0008149% |
| Post-repair package | **29.2532%** | **0.177896%** | **0.018206%** | **0.0008587%** |

Post-repair odds under this model are approximately 1 in 562 for 13+, 1 in
5,493 for 14+, and 1 in 116,459 for 15. The modeled expected counts of winning
coupons are 4.5800 (9+), 0.004150 (13+), 0.0002758 (14+), and 0.00000859
(15). Conditional on achieving the category at least once, this implies 15.66
9+ coupons, 2.33 13+ coupons, and 1.51 14+ coupons on average—another measure
of overlap/clustering.

The safety repair happened to improve all four category-union probabilities
while lowering modeled payout, but the selector did not optimize those
probabilities.

## What the objective actually optimizes

The coupon EV formula includes cumulative 9..15 category funds and jackpot
weights. However, package selection maximizes the additive sum of modeled
per-coupon gross EV, then performs a constrained local repair. It does **not**
directly optimize any of:

- probability of at least one 9+, 13+, 14+, or 15 result;
- expected best hit count;
- package variance, drawdown, or concentration-adjusted utility;
- Hamming/pairwise diversity.

It is therefore a surrogate monetary-EV objective whose validity depends on
the probability, crowd-denominator, and payout assumptions. Category-specific
risk preferences are absent.

## Snapshot sensitivity and provenance

- Raw metadata says the exact TotoBrief payload was fetched at
  `2026-08-10T09:21:45.599813Z`.
- `frozen-probability-input.json` instead records
  `2026-08-10T09:23:27.218844Z`, because the rehearsal driver injects the
  morning-dispatch record's `observed_at`. It overstates the exact payload's
  freshness by about 102 seconds.
- Package files were written around `09:39:43Z`; the drawing deadline was
  `15:30Z`. The actual quote snapshot was about 6h08m before the deadline and
  about 18 minutes old when the package was written.
- `timing_playable=true` describes event-calendar eligibility, not quote or
  package freshness. The configured T-20/T-5 values were not exercised as a
  production final run by this training driver.
- Only one quote/probability snapshot is bound. There is no nearby-snapshot
  replay, rank-turnover report, or package stability envelope.
- Holding coupons fixed, all possible one-percentage-point transfers within a
  single event move modeled 13+/14+/15 union probabilities by as much as about
  2.30%/2.79%/3.28% relative, respectively. This understates end-to-end
  sensitivity because it does not rerun ranking or the safety selector.
- The full threshold-crossing rerun above changed 6.6% of package membership
  (11 coupons per side; Jaccard 0.8757), demonstrating actual selector/hash
  sensitivity.

## Payout proxy limitations

The package uses `V = pool_sum = 1,348,659 RUB` and `J = 1,000,000 RUB`, giving
modeled category funds:

- 9: 599,404; 10: 299,702; 11: 149,851;
- 12: 74,925.5; 13: 74,925.5;
- 14: 174,925.5; 15: 974,925.5 RUB.

Limitations:

- `V` is a documented proxy, not a verified observed prize fund.
- True probabilities are normalized TotoBrief BK values for all 15 events;
  they are not a calibrated independent model or accepted external consensus.
- Crowd joint coupon behavior is reconstructed from per-event pool marginals
  using event independence. Marginals do not identify the actual joint ticket
  distribution or crowd clustering.
- Winner denominators are expected denominators, not observed winner counts.
- The package's own stakes are omitted from denominators. Its bank/pool ratio
  is 0.3693%, below the code's 1% support cutoff, but omission is still an
  approximation and especially relevant for a clustered package.
- No observed category payouts/winner counts are bound, so modeled ROI cannot
  be validated as realized ROI.
- 13,949,503 of 14,348,907 coupons (97.216%) are modeled at gross EV >=1, and
  every selected coupon is modeled at 7.53x to 15.88x stake. Together with the
  1,202% package ROI, this is a model-validation red flag, not profit evidence.

## Implementation and test assessment

- Constraint translation is mechanically correct: lower bound 1 for each
  material cell and upper bound `ceil(0.95*K)-1 = 157`.
- Final safety veto is independent and unchanged, which is a useful fail-closed
  layer.
- Repair is deterministic and records canonical pre/post hashes.
- The feasible result is only a one-swap local EV optimum inside a ranked
  prefix. It neither proves global EV optimality nor searches explicitly for
  diversity/category coverage.
- Unit tests cover deterministic ranking, threshold behavior, basic repair,
  concentration repair without a material floor, dynamic bank sizes,
  repeatability, and structural infeasibility.
- Frozen regressions cover only drawings 4967/4969/4970 and assert hashes,
  replacement counts, safety `PLAY`, and retrospective best/mean hits. Three
  drawings are explicitly too small for performance claims.
- There is no frozen 4971 regression, no test requiring more than one material
  token, no 20% threshold-edge test, no cap-margin requirement, no Hamming/
  cluster acceptance, no category-union objective test, no nearby-snapshot
  stability test, and no global-oracle test for the safety repair.
- Focused current tests were run read-only with bytecode/cache disabled:
  `tests/test_ev_package.py` and `tests/test_package_audit.py`: **94 passed in
  18.73s**. The expensive three-drawing frozen suite was inspected but not
  rerun in this audit.

## Minimal blockers before any real-money consideration

1. **Training artifact cannot be promoted.** Require a production final
   snapshot at the authorized cutoff, exact capture-time binding, independent
   freshness validation, and a package generated from that exact snapshot.
2. **Replace/strengthen the material exposure policy.** A one-token floor and
   20% cliff are not meaningful safety. Require empirically justified lower
   bounds and positive upper/lower-bound margin; re-audit after every snapshot.
3. **Validate the monetary model prospectively.** Collect lawful pre-close
   snapshots plus actual category funds, winner counts, and payouts; verify
   calibration and chronological realized performance. Modeled ROI alone is
   insufficient.
4. **Bind complete diagnostics and reproducibility evidence.** Include all 15
   pre/post rows, feasibility/exhaustiveness/reasons, algorithm/source revision,
   exact timestamps, runtime identity, and attempt status in the manifest.
5. **Add package-level risk acceptance.** Report and set reviewed thresholds
   for category-union probabilities, Hamming clustering, exposure margin, and
   snapshot turnover. The acceptable thresholds must be chosen from research,
   not invented during a live run.
6. **Require an out-of-sample gate.** No real money until sufficient
   prospective drawings establish probability calibration, payout-proxy
   accuracy, stability, and realized risk/return with predeclared stopping
   rules.

## Research improvements, not immediate safety blockers

- Compare the deterministic repair with MILP/CP-SAT or an exact small oracle;
  quantify candidate-prefix and one-swap optimality gaps.
- Evaluate direct 9+/13+/14+/15, expected-utility, and multi-objective
  EV/diversity selectors on frozen chronological inputs.
- Add probability/crowd/payout perturbation grids and report package overlap,
  rank churn, exposure churn, and category-probability intervals.
- Measure package self-dilution and crowd-ticket correlation rather than using
  only the 1% bank/pool cutoff.
- Add a portable, schema-versioned audit bundle and a frozen 4971 regression.
