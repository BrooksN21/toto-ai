# TOTO-4965-PARTIAL-ENRICHMENT — context

## Current record

- Drawing: visible **4965**, internal ID **12004**, deadline `2026-08-04T15:00:00Z`.
- Current morning-dispatch record: `data/scheduler/morning-dispatch/drawing-12004-20260804T150000Z-559c7615626b624c.json`.
- Identity fingerprint: `559c7615626b624cdd5ebefa782c6b96593ff9fb4dfcdbd18a3e6155f3c17af8`.
- Latest record status is `deferred`; preparation is `unresolved`, `mapped_count=13`, `eligibility_status=unknown`, with unresolved event orders **7** (`179170`, Ларн — Иберия 1999) and **13** (`179176`, Тигрес — Реал Солт Лейк). The latest preflight attempt is `.../attempts/20260804T134311065018Z-042c29eaf105dda1.json`.
- The unresolved cause is conservative team/fixture ambiguity (`required_evidence_type=reviewed_alias`), not missing TotoBrief identity or missing TotoBrief outcome probabilities.

## Exact blocking path

1. `src/toto_ai/external_odds/preparation.py:prepare_drawing()` documents and enforces atomic publication only after all 15 events resolve. It calls `publish_drawing_preparation()` / canonical pin publication; unresolved preparation publishes diagnostics only, not pins.
2. `src/toto_ai/runner/morning_dispatch.py:_ineligibility_reason()` (around lines 644–653) returns `ACTION REQUIRED: unresolved 2/15` whenever `preparation_status != "ready"` **or** `mapped_count != 15`. This is the direct morning scheduling gate.
3. The same module's `_update_preflight_escalation()` only clears attention for `status == "ready" and mapped_count == 15`; otherwise it writes the retry/attention artifacts.
4. Downstream, `src/toto_ai/external_odds/team_registry.py:load_ready_pin_set()` (around lines 776–806) rejects unless preparation status is ready, `mapped_count == 15`, unresolved orders are empty, eligibility is playable, readiness summary is ready/mapped 15, probability hash matches, and probability evidence is fresh. It raises `preparation_fail:not_ready_15_of_15` or probability evidence failures. The CLI systematic path in `src/toto_ai/cli.py` loads this gate before package/run generation. Thus the package is blocked both at morning dispatch and at package input loading.

## TotoBrief probability completeness for 4965

`data/raw/drawing_12004.json` contains 15 events (orders 0–14). I checked every event's `quotes`:

- all 15 have positive finite BK triples (`bk_win_1`, `bk_draw`, `bk_win_2`);
- all 15 have positive finite pool triples (`pool_win_1`, `pool_draw`, `pool_win_2`);
- all 15 therefore have complete, normalizable TotoBrief BK/pool probability inputs. Some rows lack `norm_*` quotes, but that is not a missing BK/pool triple and must not be treated as such.

## Minimal safe change design (no implementation made)

Make external sports enrichment optional **per event**, without weakening identity or probability safety:

1. Keep the exact TotoBrief drawing identity/detail validation and all 15 event orders mandatory.
2. Represent an event-level enrichment state/source (external resolved, or baseline-only) in preparation/readiness evidence. Missing/failed/ambiguous external schedule data for one event may become baseline-only; do not convert an uncertain external candidate into an identity-bearing pin.
3. Permit a baseline-only fallback only after validating all 15 TotoBrief BK and pool triples (finite, positive, complete, normalized according to existing target/probability validators), with a probability-input hash and freshness/TOCTOU revalidation exactly like the current ready path. The fallback must be explicit in the readiness summary and package provenance; never synthesize an external fixture/team ID.
4. Preserve fail-closed behavior for identity/probability conflicts: conflicting TotoBrief identity/detail, conflicting reviewed/provider home-away identity, stale or changed fingerprint, missing/invalid/changed probability matrix, duplicate/missing orders, or ineligible timing/span must still reject (`NO BET` / preparation failure).
5. Change the readiness predicate from “all 15 external mappings” to “every event is either strictly externally resolved or explicitly baseline-only, and the complete valid 15-row TotoBrief probability matrix is present.” Keep provider enrichment optional per event, not as a drawing-wide 15/15 provider requirement.
6. Ensure package generation/EV consumes baseline probabilities for baseline-only events and external probabilities only where an external market is valid; do not silently blend conflicting sources. Add provenance/reason codes so operators can distinguish `baseline_only_external_unavailable` from a hard conflict.

Likely narrow touch points for implementation: `external_odds/preparation.py` and `team_registry.py` readiness/persistence, `runner/morning_dispatch.py` readiness/eligibility and record serialization, and the CLI systematic preparation loader. Add focused tests for 13/15 external + 15/15 valid BK/pool => eligible baseline-only; invalid/missing one probability => fail closed; conflicting identity/probability => fail closed; mixed external/baseline provenance preserved.

## Project safety constraints observed

Memory-bank architecture explicitly requires exact identity, 15-event preparation, probability hash binding, freshness, and fail-closed conflicts. No code, data, or memory-bank files were edited; only this context handoff was created.
