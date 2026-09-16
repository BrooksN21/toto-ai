# Verified timing uncertainty — decision and implementation plan

Task **TOTOAI-RESUME-20260915**. CONTEXT/PLANNING ONLY. No implementation, tests, runtime mutation, source refetch, or readiness claim. Existing operations remain fail-closed. Parent dispatches any implementation separately; no nested delegation.

**Goal:** separate inability to prove an exact kickoff minute from inability to prove pre-match/deadline/span safety, without inventing starts_at or weakening identity/provenance.
**Architecture:** preserve exact-time contracts unchanged by default. First document explicit source adjudication. If exact adjudication is unavailable, an opt-in, versioned, hash-bound timing-envelope certificate can eventually prove specified safety predicates for ALL credible kickoff alternatives. Never disguise an interval endpoint as an observed kickoff.
**Stack:** existing Python datetime/ZoneInfo, immutable JSON/hash records, native reviewed-source/preparation/scheduler flows. No new services.

## 1. Verified current contracts — exact source references

1. `src/toto_ai/external_odds/schedule_evidence_admin.py:143-210,382-430,643-651`: supported prepared-review CLI requires >=2 sources, distinct publishers and registrable domains; at least one official OR two independent sources. Both source and observation starts_at must be explicit UTC-Z; each source within5min. Only scheduled/unconditional records. Exact-fields schema has NO raw-walltime/TZ-interpretation/range/conflict-disposition fields. It validates claimed UTC+bytes, not the truth of local-clock interpretation.
2. `src/toto_ai/external_odds/schedule_evidence.py:628-640`: lower-level reusable ledger claim loader accepts one official claim. **Not equivalent to the supported prepared-review CLI**, which demands2. Hand-building a single-source ledger to evade that requirement is NOT a supported operational resolution.
3. `src/toto_ai/external_odds/reviewed_schedule.py:284-320,400+`: other production drawing-bound catalog requires one official AND >=1 independent claim, agreement, exact target/fingerprint/provenance. One home programme alone is not sufficient for this route either.
4. `src/toto_ai/external_odds/schedule_evidence.py:290-423`: identity/sex/age/competition/orientation/staleness checks; observations grouped by exact kickoff/class/orientation. Multiple accepted exact schedules ->CONFLICT. There is no automatic home-club>away-club priority or latest-publication-wins adjudicator. Unreviewed contradictory candidates are not comprehensively incorporated by this resolver; selecting only agreeing claims must not be misrepresented as resolving all known evidence.
5. `src/toto_ai/external_odds/timing_overrides.py:69-149,686+,851-908` and `src/toto_ai/runner/models.py:145-234`: existing reviewed manual timing overlay is an **exact UTC point assertion** with reviewer/source_ref, target IDs/fingerprint, pre-pin review/hash checks. It preserves raw/effective audit; bounds are drawing close through close+5days. This supports recording an independently justified exact decision, NOT automatically establishing timezone/precedence or storing uncertainty. Writing a guessed UTC through this less-rich route would still be a bypass.
6. `src/toto_ai/external_odds/preparation.py:1110-1139,1160-1204`: reviewed fallback requires exact identity/class, kickoff not started, and agreement with any existing target point; provider access/plan outage can be allowed explicitly. Effective starts feed eligibility.
7. `src/toto_ai/external_odds/eligibility.py:15-35,115-182`: known means a datetime point; any missing among15 ->unknown (unless alreadymulti_day); playable requires inclusive **MSK calendar span<=2days**. The5day external-search/overlay horizon is NOT the permitted wager span.
8. `src/toto_ai/runner/morning_dispatch.py:786-813`: timing_unknown blocks plan before playability; requires playable and span<=2. This is why repeated retries without new evidence do not solve5008.
9. `src/toto_ai/runner/scheduler.py:7588-7620,7705-7745`: actionable manifest requires effective playable/details_available/known_count15/no missing/span1or2; override identity/review/hash/point equality and legal horizon are rechecked. Interval support is **not currently available** and requires a deliberate versioned change, not flipping known_count/status.

## 2. Decision for current evidence

Verified home-club PDF (ignored path `reports/rehearsal/5008-homeclub-context/programme-d72bcb94403b69a9.pdf`, SHA d72bcb94403b69a948d6a2380a4297b732dbfc98cedae0b71ba3c2a0b8d2e9ce), page1: Wed16September19:30; page3: Willand/SilverStreet venue. Official publication14Sep18:56:54UTC. No printed timezone on these relevant pages. Europe/London conversion is reviewer **venue-local interpretation**, not literal PDF UTC/BST evidence. Publication offset is not kickoff offset.

A documented timezone interpretation is not prohibited as human research, but native schema neither encodes nor proves it; provenance must state the inference and its accepted basis. It also cannot prove the undated away19:45 listing obsolete. League19:30display/raw19:30Z and Sofa18:45:18Z remain unaltered contradictory evidence. Home specificity/date is a reason to propose precedence, not existing encoded policy or proof of supersession. Therefore **no existing automatic rule yields an unambiguous apply-ready record today**. Current5008 remains last verified14/15/planNULL; close16Sep15:30Z=18:30MSK per fresh native collection.

Prefer exact evidence if a genuine dated correction + accepted venue/timezone basis and required independent corroboration become available. Otherwise stop source hunting and request a bounded systemic implementation decision; do not silently choose, fabricate seconds, suppress sources, or call the13:00retry a fix.

## 3. Which stages really need a point?

| Consumer | Mathematical need | Existing implementation / safe direction |
|---|---|---|
| Exact fixture identity, sex/age, home-away | Identity and uniqueness, not a convenient minute | Keep unchanged; if several same-team/date fixtures remain possible, block. Interval cannot cure identity ambiguity. |
| Provider date-window / source retrieval | Bounded UTC dates, not minute | Query/cache union of all plausible dates, bounded budget; unknown/unbounded dates still block. |
| Match binding to provider | Unique matching under time assumptions | Require uniqueness across ALL alternatives; do not replace existing5minmatching with a broad fuzzy range. |
| Basic package combinatorics from frozen valid probabilities | No intrinsic kickoff-minute requirement | Research/preparation can be separate nonactionable artifacts. Do not claim odds/model inputs valid from this fact alone. |
| Sports history/rest/form/time-to-kickoff features, odds prematch eligibility | Some features need a point or invariant value | Evaluate invariance over interval, or disable exact-time-dependent feature via explicit existing missing-data policy; never mid-point/latest-time imputation or silent sports fallback. This impact needs scoped verification before production. |
| Close/T-10/no-start/freshness | Conservative proven lower bound and authoritative close | Universally safe guards below; whole interval/current statuses, not most likely time. |
| 2-day eligibility / 5-day source horizon | Proven lower+upper bounds | Worst-case inclusiveMSKcalendarspan<=2; preserve5daysearch/overridebound separately. |
| Current pin/input/plan/consent/operator validators | Point-shaped schemas today | New versioned certificate in all bindings; old exact path unchanged. No fake starts_at, known_count15 or manual PLAY. |
| Postmortem completion | Verified terminal event status/results | Scheduled upper bound is not proof of match completion. |

## 4. Proposed minimal envelope contract — design, NOT implemented

Create an immutable separate `ReviewedTimingEnvelope`: exact target/event/teams/class/orientation + raw source claims, sourcebyteSHA/publication/capture/reviewer times, literal clock/precision, explicitTZ OR named accepted interpretation with basis, candidate UTC instants/intervals, retained conflicts and disposition/reason, valid_from/expires, contract/version and hash. Store originals; UTC normalization is a derivation with documented timezone/tzdb version. No source/draw-specific rules. Minute-only clocks retain minute precision; no altering18seconds in originalSofa.

Use `exact / bounded_conflict / unknown / invalid` rather than promote bounded toexact. A bound is admissible only if reviewer establishes **exhaustive plausible timezone/date interpretations** under an approved policy; taking min/max of whatever providers returned is NOT enough. Unknown timezone/date/identity, unbounded postponement, missing fresh-status evidence or an unhandled source ->unknown and fail closed. Deliberately inconsistent rawZ andwallclock both remain alternatives until explicitly adjudicated.

For each15events let admissible S_i subset[L_i,U_i], E=min_i L_i, H=max_i U_i. Existing exact starts are degenerate bounds. All bounds must share immutable target/finalinput evidence and fresh statuses. For retained authoritativebookclose C:
- Preconditions for existing late-match assumptions: each L_i>=C and U_i<=C+5days (or preserve any stricter nativepoint contract). If not, no automatic extension/reinterpretation of closingtime; separately reviewedcutoff change required.
- Worst-case span: (date_MSK(H)-date_MSK(E)).days+1<=2. Inclusive2days is not48hours.
- Conservative release expiry R=min(C,E)-10minutes, or earlier existing bound; NEVER later than existingT-10. Require actualpublication/consent/now strictly beforeR; source/odds captures must precede earliestpossiblekickoff and satisfy existing staleness windows.
- Actualnotstarted/unconditionalidentity evidence, allsource/hash/catalog/input bindings, modelquality/releasegates, bank/stake/consent, delivery budget andnoautowager rules remain mandatory. Passing time math is necessary, NOT sufficient forPLAY.
- If envelope updated/widened/expired or kickoff/status changed, invalidate oldplanbindings as nativeflow requires; prepare a newplan+freshownerconsent. No consent migration.

**5008 diagnostic only:** under explicitly accepted UKvenue-local semantics, observed interpretations include18:30UTC(homeprogramme),18:45UTC(awaylocal),18:45:18UTC(Sofa),19:30UTC(literalleagueZ). Those candidates are after15:30UTCclose and ononeMSKdate. This is NOT an approved exhaustive bound: timezone interpretation, source-completeness/freshness and all14otherbounds must be certified. Do not claim current15/15 or operator-safety from this illustrative set. Minuteprecision may widen endpoints according to a documented normalization rule.

## 5. Sequential implementation gates (requires parent approval)

- [ ] **A. Adjudication/evidence DTO only.** Add `src/toto_ai/external_odds/timing_envelopes.py` and dedicated tests, extend prepared-review via explicitversion/newcommand rather than looseningv1. Identity/UTCinterpretation/sourceconflict/precision/expiry/hash contracts above. Keep every rejected/contradictory claim. Unit negatives: unknownTZ, DSTfold/gap, women/youth/orientation mismatch, mixeddates, tamperedbytes, duplicatepublisher, postkickoffcapture. Existingexact tests unchanged.
- [ ] **B. Preparation-only certificate.** Pure envelope eligibility helper in `eligibility.py`, `preparation.py` and `runner/morning_dispatch.py`; emit `preparation_ready_bounded`, not playable15points. Allow source collection and nonactionable rehearsal preparation under current locks. Do not modify production finalrelease yet. Tests: preclose/midnight/Moscow2vs3days/5dayhorizon/nointervalbound, point-regressionparity; targeted `test_external_odds_eligibility.py`, `test_morning_dispatch.py`, scheduleevidencetests.
- [ ] **C. Explicitly scoped operator support, separate approval.** Version plan/finalinput/manifests and exact timing validation (`runner/models.py`, `runner/scheduler.py`, existingtimingoverlay/storage consumers). Implement universalguards and tokenizedcertificate/hashes without lyingaboutknown_count. Map downstreamconsent/parallelcompanion/sourcepins by verifiedcallgraph beforecoding. Exact-dependent sports/matching consumers must be invariant or failclosed. Tests: intervals crossingT-10/close/now, stale/widenedcertificate, changedinput/hash/consent, no sourcefallback toanonymousUTC, primary/parallel sameinput, noactionableafterexpiry. No implementation promises for today.
- [ ] **D. Regression/review/activation.** Existingexact flow parity, targeted runner/scheduler/timingoverride tests plus syntheticintervalproperties; native no-wager dry-run before approved activation. Review certificate math and source policy separately from code. Allchangesmust be reviewed/published byparent-ownedworkflow; this context worker does not commit. Preserve clean operating pipeline during implementation; no late hot-switch. Any delay ->safeNO_BET, not fabricatedrelease.

## Risks / stop conditions

Biggest risk is a false exhaustivebound, not the clockconversion arithmetic. Others: source precedence hiding corrections; changing two-day semantics; daylight-saving ambiguity; broadprovider matching; retrospectivefeature leakage; treating prepare-ready asPLAY; changinghashschemas without allreaders; oldconsent/finalinput reuse; postmortem assumingcompletionfromschedule. Ranges address safety/liveness, NOT prediction accuracy or guaranteedreturns. Narrow change is semantic andcross-cutting; cannot truthfully promise a one-line safeproductionfix.

No web requests, model work, test runs, code/DB/catalog/jobs/consent/ACTIVE_PLAN edits were performed. This document is a proposal, not authorization or a validated envelope.


Saved at 2026-09-16T12:51:37.428737+03:00
