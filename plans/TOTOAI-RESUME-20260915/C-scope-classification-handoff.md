# C classification binding — durable proposal handoff

Task TOTOAI-RESUME-20260915. Prepared 2026-09-15T19:17:34.774136+03:00.

**PROPOSED / NOT APPROVED / NOT IMPLEMENTED / NOT ACTIVATED.** This is a review recommendation, not an architecture decision or permission to train/release. Prior inactive envelope adapter acceptance and published code `cefb408` are separate.

## Current project step
A inert library and bounded B research are published. C representation/path/provenance defects are fixed and independently accepted, but C remains12/15events with unknown historical classes and zero sports reliability. D real fitting and F activation remain blocked. No predictive-quality, profit or improvement claim.

## Contract finding and correction to the search direction
GOAL's inspected24history wrappers/240rows do not contain gender/age_group/squad_type. V3 currently reads these literals from every accepted history row and compares each to the target participant. Its intended concept is common team-entity scope; it has no reusable provider/canonical entity + dated taxonomy binding.

A separate legal regulation for each game is NOT required by code. League/season need not match for the same team's rolling form; optional standings and competition-scoped evidence have their own boundaries. Senior/open team taxonomy is not a legal claim that all individual players are over18. Current test labels are male/adult/first; aliases such as senior/first_team are not silently equivalent. Exact team ID alone does not authorize fabricating missing classes.

## ONE proposed next isolated change
Add one versioned reviewed entity-scope sidecar contract with deterministic fixture/date binding in the inactive feature assembly boundary; retain existing scope/reliability/fit/release guards.

### Evidence schema
- **subject**: provider; provider_team_id; canonical_team_entity_id; entity_kind=TEAM_ENTITY; explicit side/membership binding.
- **taxonomy**: version; gender; age_group; squad_type; field-specific supported/unknown state; explicit reviewed alias mapping; existing fixtures use male/adult/first, not automatic senior/first_team.
- **temporal**: valid_from; valid_to; source_captured_at; source_declared_published_at separately; independently established available_at if any; reviewed_at; evidence_domain.
- **scope_boundary**: TEAM_ENTITY or COMPETITION_SEASON with explicit membership; competition_id/season required only when that evidence is competition-scoped.
- **lineage**: original source path+SHA; canonical-ID mapping path+SHA; reviewed taxonomy assertion path+SHA; per-row fixture/team/kickoff binding; exact target and raw-history hashes; named independent review scope.

### Binding and authority
Resolve each consumed historical occurrence against canonical entity and validity; several fixtures may cite one shared assertion if every join/time check passes. Produce new per-row normalized scope and derivation lineage; never edit GOAL raw bytes. Direct source labels remain evidence, not overridden by a sidecar. Target-time scope checked independently; never copy target scope into past rows.

Reviewer may approve exact taxonomy/mapping assertions, not a fabricated provider field or a new independent provider. Evidence is not self-authorized by a boolean or hash. Do not emit a historical/fold common-scope receipt until every claimed row is genuinely supported.

Today-collected pilot evidence remains retrospective research-only unless historical availability is independently proven. The existing trainer accepts only FROZEN_HISTORICAL_INPUT/SYNTHETIC_TEST_ONLY; no new training domain or reinterpretation is part of this change.

### Bounded first acceptance slice
One complete independently reviewed dated team-scope assertion + exact provider/canonical mapping, demonstrated on at least2already-frozen occurrences inside the proven period and1outside/conflicting negative. Both target participants must ultimately be covered. No legal regulation is mandatory; dated provider taxonomy/team roster or explicit official team categorization can suffice when it actually supports all claimed fields.

This is a proposal for a reviewed, pure offline normalization boundary, not an implementation plan approved by the owner. It may reuse one genuinely supported taxonomy assertion for multiple fixtures only after checking each identity/date. It cannot backfill current-team labels into past rows or reclassify an opponent. No new training domain, whole-project redesign, raw mutation or relaxation of missing/conflict/as-of gates is authorized here.

## Already collected pilot: retain partial support, not full approval
Composite exact-match identity for Osasuna–Getafe31August2026 is supported by the official fixture and club announcement. RFEF material explicitly supports male competition category; Osasuna's dated Primer Equipo article supports that participant's first-team association, not Getafe's full taxonomy or all-season membership. Full senior/first-team classification for both participants remains unproven. Sources were collected15September; a publisher-declared historical date does not establish an immutable pre-draw capture or justify entering FROZEN_HISTORICAL_INPUT.

Existing public source links (collected by prior worker, not fetched in this job):
- [LaLiga fixture](https://www.laliga.com/en-ES/match/temporada-2026-2027-laliga-ea-sports-ca-osasuna-getafe-cf-3)
- [Osasuna announcement](https://www.osasuna.es/osasuna-getafe-entradas-31-agosto-2026)
- [RFEF VAR tender](https://rfef.es/sites/default/files/pdf/BASES%20DEL%20CONCURSO%20VAR.pdf) — category support only, not a complete player/club eligibility rule.

Do not restart unbounded regulation hunting. After explicit contract approval, request one complete dated taxonomy assertion plus exact ID mapping with real temporal/provenance evidence; test two covered historical occurrences and one outside/conflicting case, then independent review. Missing support stays missing. Today-collected evidence must not be falsely promoted to historical availability.

## Required negative/compatibility tests for the proposed change
1. Identical club/team display name but different provider/canonical IDs: reject join.
2. Provider ID maps ambiguously to first/reserve/women/youth entities or overlaps validity ranges: reject, no fuzzy-name fallback.
3. Wrong side/orientation or absent fixture membership: cannot apply entity proof.
4. Competition-scoped evidence applied to another league/season, cup or reserve eligibility without explicit membership: reject.
5. Fixture kickoff outside [valid_from,valid_to), or naive/ambiguous time: not covered; boundary equality tested.
6. Only gender supported: age_group/squad_type remain unknown; scope_verified stays false.
7. Post-asof capture or review basis without independently established earlier availability: cannot enter FROZEN_HISTORICAL_INPUT; publisher-declared date alone not immutable proof.
8. Current profile retroactively asserted for old history without historical validity: reject.
9. Raw/provider explicit class conflicts with sidecar or two independent sources conflict: reject rather than prefer convenient proof.
10. Unsupported taxonomy value/alias, including senior→adult or first_team→first without versioned mapping: reject, no guessed normalization.
11. Source SHA, entity mapping SHA, target/raw history SHA or review binding altered: reject even when booleans say verified.
12. Caller self-asserts reviewed=true or supplies synthetic test references: cannot produce real independent scope receipt.
13. No evidence / partial coverage: existing unknown/fallback/denominator behavior unchanged; never delete uncovered rows.
14. Cross-competition histories with identical independently proven entity scope remain admissible to rolling core; optional standings scope cannot block them.
15. All accepted sources and regulation90 features unchanged; sidecar does not overwrite raw archives or reuse AET/PEN aggregate scores.
16. Junior players appearing in a senior/open team do not reclassify the team as youth; player DOB is not team-category evidence.
17. Fully valid sidecar cannot bypass15event/fold/common-scope/full-feature/prospective/operator gates; no fit/PLAY automatically.

## Identity, missingness, reliability, and release are distinct
- Identity safety: hashes/provider/team/fixture/orientation/as-of. Same name is insufficient.
- Missing features: None is retained; absent taxonomy is not fabricated and not automatically a corrupt source.
- Reliability is a sports-shrinkage weight, not a calibrated winning probability: zero for rejected/nonexact/unverified scope, otherwise0.2×min(1,min(prior_counts)/10)×feature completeness.
- If genuine class proof existed,38/53 or42/53 features with10prior matches per side would imply weights≈0.1434/0.1585. This arithmetic does not prove forecast improvement. Current weight remains0; even scope-only repair leaves these rows0/12 at the full-feature F4 coverage criterion.
- Independent scope/fold receipts,15unique ordered events, label chronology, existing fold/quality/coverage/prospective and operator gates remain unchanged. Training/activation not ready.

## Operations5007 checkpoint — provenance and limits
The parent submission handoff reports complete full preparations at19:00(107.7s) and19:10(101.8s),166coupons/4980bank, expected warmupNO_BET. It also reports actual-config final experimental-path verification with4tests and existing plan-bound consentVALID until19:50MSK. Those4operational tests were NOT rerun by this metadata worker and are distinct from the4scope unit checks below; no file receipt for these newer checkpoints was located in the bounded current-task top-level inventory. Treat these values as parent-reported, not this worker's fresh live attestation.

Previously saved parent receipts: checkpoint5007-1830.json and watcher5007-hashfix-activation.json (observerPID34611 at that observation). No fresh PID or future PLAY assertion. Parent owns19:20next scheduled check,19:30final target,19:50T-10expiry,20:00close. WarmupNO_BET does not prove final failure or finalPLAY. This task changes no jobs/config/consent/DB/operator artifacts.

## Verification and exact next action
Current metadata publication:4existing scope/identity guards PASS; Ruff4PASS. These establish current contract behavior, not implementation of the proposal. The earlier bounded scope review had126C/native+2F4boundary tests PASS/Ruff5. No recalculation, real training, API/web queries or code edits in this job.

**Next research action:** obtain explicit approval for C-SCOPE-ENTITY-BINDING-V1, then implement/review that single isolated contract against the negative cases above. Keep corpus and fit blocked until actual evidence qualifies. Preserve5007operations independently.

## Exact local source references
Full ignored research artifacts stay local; no raw/sourcePDF/DB upload. This handoff preserves the substantive recommendation and negative tests even if those artifacts are absent from another checkout. Hashes identify the original review/extract bytes, not proof of historical availability. Paths are repository-root relative:

- `reports/rehearsal/TOTOAI-RESUME-20260915/C-scope-contract-review/review.md` — SHA-256 `952f4381b9302dc2696949b13b6cb9eac15159658e8c6f6ff48d04a0e540832a`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-scope-contract-review/review.json` — SHA-256 `d3bd3a37d63ad4260f6794434bb1cc5de412676c43c7d1312237e51cf92d1a0e`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-scope-contract-review/proposed-contract.json` — SHA-256 `c7fc87a774fd0e97f45e853be94f162cb68824208e67d1f1de0cab5040f86a9a`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-scope-contract-review/verification.json` — SHA-256 `9b56d6ca6b18a00623df3299796d9e1f3b8d28c756e2d1847504033d137508e5`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/proof-pilot.md` — SHA-256 `5e18ef715931b4b5fd289c3350bac9bc5efbe96da78c380ed58c32dfa25439fc`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/proof-pilot.json` — SHA-256 `9cd5954e2cf59a0823f6cf3933462516cebb9344f1e32660b56d8c77c9dd2f95`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/regulation-onecase-verdict.md` — SHA-256 `980c07051cb046b9e623c53fd89e7f2b37aaff0878cce1d9b772cf25146804f9`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/regulation-onecase-verdict.json` — SHA-256 `1272534aaa817a4b7571c03695158d9aa90e72fd2e84cd49533b8bee8997789e`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/laliga-fixture.json` — SHA-256 `ca49a620c13832f3fdc797c03c4cddfdc16fcce1f4be528fa44ac9af35173115`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/osasuna-announcement.json` — SHA-256 `3c4fd7963b5fab0fc1231aba15c6df44355ced93ac03f1d4958d83ead6af90be`
- `reports/rehearsal/TOTOAI-RESUME-20260915/C-class-proof-pilot/rfef-regulation-evidence.json` — SHA-256 `6c229a254c60eb83b67248256f0c430ca1889b5194032da6b60ab7bb11fe39b3`

Code contracts: `src/toto_ai/sports_stats/v3_probability_features.py:71–161,286–325`; `v3_family_evidence.py:90–98,142–147,260–296`; `v3_probability.py:148–152`; `v3_f4.py:37–117,287–315`; `v3_f4_gate.py:80–91,168–175`. Exact source hashes remain in the ignored review.json. No DECISIONS acceptance entry has been made.
