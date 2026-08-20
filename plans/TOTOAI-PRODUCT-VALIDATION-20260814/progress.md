# TotoAI Product Validation Progress

Обновлено: 2026-08-20
Текущий этап: 2 — historical benchmark; legacy-100 выполняется
Общий статус: IN PROGRESS

## Этапы

| Этап | Статус | Результат / блокер |
|---:|---|---|
| 0. Live-цикл 4975 | COMPLETE | Final paper package 166 / 4 980, T-10 cleanup, 15/15 result sync, settlement, review request and postmortem complete; best 8/15, no wager |
| 1. EV/BK/TotoBrief-style | COMPLETE | Four equal-input adapters, command and hash-bound reports verified; 4975 EV output exactly reproduces final package |
| 2. Historical benchmark | IN PROGRESS | Strict sample extended to 18 unique drawings; legacy v3 canary/resume complete; legacy-100 running, 500/1000 remain |
| 3. Objective correction | NOT STARTED | Зависит от benchmark findings |
| 4. Schedule evidence automation | PARTIAL | Reusable UEFA v5 + Sofascore exact-consensus promotion is implemented and replayed on 4981 (2/2); non-UEFA authoritative adapters remain |
| 5. Free sports coverage | PARTIAL | Stored-source baseline written: API-Sports odds 10 drawings/150 events/68% consensus; The Odds API 4/15; sports stats 0/15 complete |
| 6. Sports residual model | NOT STARTED | Нет достаточного frozen feature dataset |
| 7. Prospective holdout | NOT STARTED | Release gate требует минимум 30 тиражей / 450 событий |
| 8. Operator product | NOT STARTED | Production остаётся PAPER / NOT ACTIVATED |

## Этап 0: чек-лист 4975

- [x] Drawing 4975 READY 15/15.
- [x] Bank/stake зафиксированы: 4 980 / 30.
- [x] Evening plan `c6a3a25a8459d0d2` установлен и загружен.
- [x] Trigger schedule проверен.
- [x] 15:00 TLS preflight отработал: exit 0, 69.08s, no failures.
- [x] 15:30 API preflight отработал: exit 0, 63.97s, no failures.
- [x] 16:00 freshness preflight отработал: exit 0, 70.10s, no failures.
- [x] 16:15 warmup отработал: exit 0, 316.50s, LKG 166 / 4 980.
- [x] 16:30 refresh/LKG отработал: exit 0, 291.27s, LKG 166 / 4 980.
- [x] 16:40 primary final отработал: exit 0, 224.47s, `FINAL_FRESH`.
- [x] 16:44 retry/admission корректно не понадобился: final завершился terminal в 16:44:01.
- [x] 16:50 T-10 terminal publication отработала: run 7, exit 0, operator upload expired, audit/paper retained.
- [x] Финальный package/package-free result сохранён: `NO BET`, 166 unique paper coupons, 4 980, exact upload format.
- [x] Post-draw LaunchAgent автоматически установлен и `launchctl print` verified.
- [x] Следующий день 12:00 result sync реально запущен.
- [x] Получены 15/15 результаты; VOID отсутствует.
- [x] Settlement и postmortem сформированы и review завершён.

## Последние доказательства

- Resume analysis 2026-08-20: drawings 4975-4980 have 15/15 outcomes and true
  pre-deadline probability snapshots. Drawing 4980 was explicitly synchronized
  after the pause. The real 4975 frozen package scored best 8/15; eight actual
  outcomes had under 10% package exposure. Strict counterfactual rows for
  4976-4980 average BK-only 8.6, EV/crowd 6.6, Cover-13 7.4 and Cover-14 8.4,
  with zero 13+. Across 18 unique strict drawings the averages are 8.889,
  6.889, 8.167 and 8.889 respectively; only Cover-14 has one 13+. The sample
  is still non-interpretable for a strategy/release verdict. Evidence:
  `reports/research/new-drawings-4975-4980-20260820/`.
- Drawing 4975 strict evidence debt: its complete result snapshot lacks a RAW
  hash binding. It is analyzed through the real frozen settlement but remains
  excluded from the strict strategy runner.
- Active drawing 4981 is READY/playable 15/15. Events 7 and 9 were resolved
  before deadline from hash-frozen official UEFA v5 and independent Sofascore
  JSON with exact kickoff agreement. The passive 12:00 MSK retry completed
  automatically with return code 0 and activated evening paper plan
  `5caf88df9bdfe566` for 4,980/30. Launchd reports eight triggers at
  16:00/16:30/17:00/17:15/17:30/17:40/17:44/17:50 MSK. No real-money release
  is authorized and no operator package exists before a scheduler result.
- Reusable UEFA schedule automation: exact localized UEFA target matching,
  official match re-fetch, independent Sofascore re-fetch, identical kickoff
  consensus, immutable snapshots/review and idempotent ledger promotion are
  implemented. The frozen 4981 replay promoted both unresolved rows into an
  isolated ledger, and a live public-source canary repeated the 2/2 result
  without touching production evidence. Automatic deferred morning dispatch
  now runs this path independently of generic non-promoting discovery;
  non-UEFA rows still fail closed and require another authoritative adapter or
  review. Verification: `1904 passed, 13 deselected`; Ruff/diff-check pass.
- Drawing 4981 sports shadows were captured before deadline. API-Sports sports
  stats produced 0 complete / 10 partial / 5 missing event rows and a 15/15 BK
  fallback `INSUFFICIENT_EVIDENCE` artifact. The Odds API control checkpoint
  matched 3/15 events, spent two credits and retained 492; it remains
  `NOT_ACTIVATED`. These are prospective diagnostics, not package inputs.

- Strict strategy benchmark command:
  `historical-strategy-benchmark`; it loads the latest cryptographically
  verified RAW snapshot captured at/before deadline, keeps actual results on a
  separate terminal-snapshot path, reuses the unchanged quality-v2 objective,
  and writes hash-bound JSON/CSV/Markdown/manifest artifacts.
- Full strict run: 13 drawings, bank/stake 4,980/30, 15:08 runtime, zero
  strategy timeouts. Average best hits: EV/crowd 7.00, BK-only 9.00,
  Cover-13 8.46, Cover-14 9.08. Cover-14 recorded one 13+ drawing; no 14+ or
  15 for any strategy. Cover-13/14 spent only 660/2,700 on average, so this is
  not an equal-cost verdict. The sample is explicitly
  `STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE / NOT RELEASE EVIDENCE` and no winner
  is declared. Evidence:
  `reports/research/strict-strategy-benchmark-20260814-all13/`.
- Strict v2 control run: all 13 drawings completed in 14:44 with hash-verified
  artifacts at
  `reports/research/strict-strategy-benchmark-20260814-all13-v2/`. BK-top
  single-coupon average was 6.538. Paired best-hit delta versus BK-only was
  EV/crowd -2.000 with nominal 95% bootstrap interval [-3.462, -0.538],
  Cover-13 -0.538 [-1.077, 0.000], and Cover-14 +0.077
  [-0.692, 0.923]. All intervals have `interpretation_allowed=false` because
  n=13; no winner or profitability claim is permitted.
- BK-top/bootstrap implementation verification: `1900 passed, 13 deselected
  in 123.05s`; Ruff and `git diff --check` passed.
- Legacy runner: `legacy-strategy-benchmark` labels every input and artifact
  `LEGACY_RETROSPECTIVE`, records chronology as unverified, excludes actual
  results from the prediction-data hash, and writes an atomic hash-checked
  checkpoint after each drawing. A real one-drawing canary completed in 1:04;
  its immediate repeat resumed in 0 seconds. On drawing 4974 the mutable
  legacy DB produced EV best 7 versus strict pre-deadline best 5, proving the
  tiers must remain physically separate. Legacy-100 completed in 1:50:22:
  BK-only 8.700 average best, EV/crowd 7.050, Cover-13 8.260 and Cover-14
  8.960. Paired versus BK-only: EV -1.650 [-2.210, -1.120], Cover-13 -0.440
  [-0.650, -0.230], Cover-14 +0.260 [0.060, 0.460]. The report is diagnostic
  only; Cover-14 spent 2,757 RUB on average, and no profitability or release
  winner is declared. A Legacy-500 resume was stopped cleanly at 116
  checkpoints: further non-chronological volume cannot establish observed ROI,
  so prospective evidence has priority.
- Official payout audit: the current BaltBet rules confirm the implemented
  cumulative category fractions. TotoBrief still supplies no separate
  `Possible winnings`, all 420 stored result snapshots have null payments,
  and observed ROI cannot be computed from the current evidence. See
  `research/baltbet_official_payout_audit_20260820.md`.
- Legacy-500 resume initially failed closed because plan 4975 referenced an
  older schedule-evidence hash than the advanced shared production ledger. The
  exact ledger plus review-document bundle was recovered from Git commit
  `9be3cdc`; a separate research scheduler plan passed strict validation and
  resumed the existing checkpoints. No production evidence was rolled back.
- Current full verification: `1904 passed, 13 deselected in 123.15s`;
  Ruff and `git diff --check` passed.
- Ruff: passed.
- Git diff check: passed.
- Latest local implementation commit: `Automate exact UEFA schedule consensus`
  (not pushed).
- 4974 paper review: best 6/15, zero 10+, no wager.
- 4975 BK vs sports comparison: identical 166/166, sports coverage 0/15.
- Free-source baseline: `reports/research/free-source-audit-20260814/summary.md`;
  API-Sports external-odds consensus 102/150 (68.00%), The Odds API 4/15
  (26.67%), both below the 30-drawing/450-event gate.
- Official-documentation audit ranks football-data.org as the first
  sports-feature shadow pilot; TheSportsDB/OpenLigaDB are secondary schedule
  evidence and StatsBomb Open Data is research-only. See
  `knowledge/free_sports_sources.md`.
- Full DB health: 2,216 drawings; 13 strict chronological historical-inventory
  healthy; 1,672 probability-backtest eligible; 3,843/3,844 are also absent from the
  upstream results listing and are not local ingestion loss; phase-2 evidence
  tiers frozen in `phase2-data-eligibility.md`.
- Live 4975 trigger 15:00 MSK: LaunchAgent run 1, exit 0;
  `tls_preflight-01-20260814T120007817342Z-5651ee69` completed at
  `2026-08-14T12:01:16.900047Z`; terminal remains null as expected.
- Live 4975 trigger 15:30 MSK: LaunchAgent run 2, exit 0;
  `api_preflight-01-20260814T123008095081Z-a9b7695e` completed at
  `2026-08-14T12:31:12.061655Z`; zero failure details.
- Live 4975 trigger 16:00 MSK: LaunchAgent run 3, exit 0;
  `freshness_preflight-01-20260814T130018316198Z-a3a97623` completed at
  `2026-08-14T13:01:28.412427Z`; zero failure details.
- Live 4975 trigger 16:15 MSK: LaunchAgent run 4, exit 0;
  `warmup-01-20260814T131523643983Z-f27c7ad1` completed at
  `2026-08-14T13:20:40.148532Z` in 316.50s; zero failure details. It produced
  a validated non-actionable LKG checkpoint with 166 unique coupons, exact
  cost 4,980 and 166 valid BaltBet upload lines. The package remains paper-only
  and the release gate is closed.
- Live 4975 trigger 16:30 MSK: LaunchAgent run 5, exit 0;
  `refresh-01-20260814T133019452143Z-a3e476e3` completed at
  `2026-08-14T13:35:10.720875Z` in 291.27s; zero failure details. The refreshed
  checkpoint contains 166 unique coupons, exact cost 4,980 and 166 valid,
  unique BaltBet upload lines; upload SHA-256 starts with `ff1ad616140a`.
- Live 4975 final started at `2026-08-14T13:40:16.580964Z` and completed at
  `13:44:01.046512Z`, exit 0, no failure details. It published a hash-verified
  `FINAL_FRESH` paper package with 166 unique coupons, cost 4,980 and decision
  `NO BET`; reason: `quality_v2_real_money_release_gate_closed`.
- T-10 trigger raised LaunchAgent runs to 7 with exit 0 and expired the
  operator-facing LKG pointer as designed. The immutable paper package remains
  at `paper-package/checkpoints/00e224fcfa88b102f27daa8e/paper-package.txt`,
  166 lines, SHA-256 `ff1ad616140a9d4f94dd1f3e67475c67b17a8cfa6a67f742b6cc16fed2a4fbe6`.
- Post-draw LaunchAgent `com.toto-ai.post-draw-12033` is installed and loaded;
  first automatic result sync is 2026-08-15 12:00 MSK with bounded three-hour
  retries through 2026-08-16 03:00 MSK.
- Phase-1 shared contract tests: 9 focused tests pass; full suite 1,885 passed,
  13 deselected; Ruff and diff-check pass. Adapter/BK/brief/cover regressions
  regression tests pass; Ruff passes. The new adapters bind one immutable
  input hash, enforce pre-`as_of` chronology, dynamic bank/stake, unique
  15-sign coupons, exact cost and category probabilities. Cover-13 and Cover-14
  both require the existing independent exact verifier to pass.
- `compare-package-strategies` completed on the immutable 4975 final input. All
  four results share input hash `ee938dd3413e...`; the EV package is exactly
  equal to the 166-coupon final paper package in both order and set. Modeled
  P(13+)/P(14+)/P(15): EV 0.00226572/0.00022230/0.00000916; BK-only
  0.01333865/0.00202121/0.00014290; Cover-13
  0.00319861/0.00031179/0.00001273 at 22 coupons; Cover-14
  0.00925712/0.00107714/0.00005283 at 90 coupons. Both Cover variants passed
  exact guarantee verification. This is one modeled snapshot, not historical
  evidence and not a profitability result.
- Data-health chronology audit corrected the old strict count: only 13 rows
  have genuine pre-deadline raw evidence plus complete strict inputs. Contract
  1.2.0 fails closed on `missing_predeadline_raw_snapshot`; 1,888 default tests
  and Ruff pass. The strict sample validates the pipeline only.

## Следующее действие

Автоматически архивировать, а после завершения тиража рассчитывать результаты
четырёх неизменённых стратегий на новых prospective-входах. Не продолжать
Legacy-500/1,000 без нового явного диагностического вопроса и не открывать
повторную BK-only оптимизацию после
зафиксированного hybrid `STOP` без нового протокола и нового untouched-окна.
Параллельно наблюдать каждый триггер активированного evening plan 4981 и
сохранить финальный paper/operator result. Продолжать расширять authoritative
coverage только на источники с тем же exact-consensus/fail-closed контрактом.
