# TOTO-SCHEDULE-RESOLUTION-V2 context

## Scope and inspected evidence

- Project instructions: `/Users/turshevr/toto-ai/AGENTS.md`.
- Project context: `memory-bank/CURRENT_STATE.md`, `memory-bank/ARCHITECTURE.md`, and
  `memory-bank/DECISIONS.md`.
- Current reviewed fallback implementation:
  `src/toto_ai/external_odds/reviewed_schedule.py`.
- Drawing 4965 runtime evidence:
  `data/scheduler/morning-dispatch/preflight/drawing-12004-20260804T150000Z-559c7615626b624c/reviewed-schedule-queue-525ec3b5ad9a.json`
  and its sibling `attention.json`.
- Human evidence: `plans/TOTO-4965-REVIEWED-EVIDENCE-20260803/events-5-7.md` and
  `events-10-12.md`.

Drawing 4965 is internal drawing `12004`, deadline `2026-08-04T15:00:00Z`,
fingerprint
`559c7615626b624cdd5ebefa782c6b96593ff9fb4dfcdbd18a3e6155f3c17af8`.
The queue has one record (event order 13, `Тигрес — Реал Солт Лейк`, target
event `179176`) and the attention marker says `unresolved 5/15`:

| order | TotoBrief names | resolver classification | target event |
|---:|---|---|---:|
| 5 | Сент-Жиллуаз — Боде Глимт | ambiguous, best pair 0.661, margin 0.223 | 179168 |
| 7 | Ларн — Иберия 1999 | ambiguous, best pair 0.587, margin 0.127 | 179170 |
| 10 | Ремо — Сантос | ambiguous, best pair 0.6375, margin 0.215 | 179173 |
| 12 | Шарлотт ФК — Пумас УНАМ | ambiguous, best pair 0.467, margin 0.039 | 179175 |
| 13 | Тигрес — Реал Солт Лейк | `source_missing_competition` | 179176 |

All candidate rows have `exact_team_count=0` and `provider_id_count=0`; several
are reversed or only `league-unconfirmed`. API-Sports date diagnostics succeed
for 2026-08-03/04 and then fail for 2026-08-05..08 with “plan does not provide
the requested data”. The evidence documents establish the actual identities
and UTC starts for orders 5, 7, 10, and 12 (UEFA/club/CBF/Concacaf sources),
but the current queue is only a blank per-match review template.

## Exact recurring root cause

This is not primarily a missing-data incident. It is an identity-resolution
boundary failure repeated for every new drawing:

1. TotoBrief supplies localized, abbreviated, transliterated, renamed, or
   otherwise display-oriented team names.
2. API-Sports supplies a broad schedule candidate set, but not a stable exact
   provider-team identity for these competitions/names. The resolver correctly
   refuses weak name similarity: candidate context, orientation, and pair
   scores do not constitute identity, and no exact provider IDs are present.
3. The fallback is modeled as a **catalog**, and `reviewed_schedule.py` makes
   the coupling explicit. A catalog is a non-empty JSON file whose records are
   keyed by the complete tuple
   `(drawing_id, drawing_number, target_fingerprint, event_order,
   target_event_id)`. Selection requires exactly one matching record. Every
   record additionally requires fresh, hashed snapshots, one official plus one
   independent HTTPS claim, exact team/start agreement, and reviewer metadata.
   It deliberately cannot create an API-Sports fixture identity.
4. Therefore evidence is useful only after a human has produced a new
   drawing-specific record. A previously reviewed alias or an official match
   page cannot be reused as a general resolver fact: the current key contains
   the whole drawing and target fingerprint, while the automatic matcher has
   no durable entity/competition identity layer that can safely map new names.
5. Retry/expanded-date calls repeat the same candidate search and may add
   quota failures, but cannot manufacture identity. The result is a recurring
   passive attention queue and `NO BET`, even when independent official
   sources can resolve the same match.

In short: **the system has evidence validation and exact per-run binding, but
not a provider-neutral, durable entity-resolution layer; reviewed evidence is
being used as an exception catalog instead of as input to that layer.** The
fail-closed behavior is correct; the static per-match dependency is the
scaling defect.

## Systemic fail-closed resolver design (no static per-match catalog)

Replace the per-drawing reviewed catalog with an append-only, provider-neutral
**schedule evidence resolver**. It must resolve from fresh source observations
and durable canonical entities, never from a hand-maintained list of future
matches.

### 1. Canonical entities and evidence ledger

Add durable records keyed by canonical `TeamEntity` and `CompetitionEntity`,
with aliases as reviewed observations, not executable overrides. Each alias
stores normalized name, locale/transliteration, source, source-native ID when
available, reviewer, captured time, and snapshot hash. Store match observations
as immutable claims:

`home_entity`, `away_entity`, competition, sport/class, start UTC, status,
venue (optional), source URL/native ID, captured time, snapshot hash.

Never infer a new entity solely from fuzzy similarity. A new alias may become
active only through an acceptance rule below. No record is keyed by drawing
number, drawing fingerprint, or event order.

### 2. Candidate generation and strict adjudication

For each TotoBrief target, derive the UTC date window from the target deadline
and all known candidate starts. Query every configured provider/source for the
relevant UTC date(s), recording successful, quota-failed, and absent dates
separately. Generate candidates using exact normalized aliases, provider IDs,
competition/sport/country context, orientation, and time tolerance.

Accept automatically only if one candidate has all of:

- exact canonical entities (or an already reviewed alias to each entity);
- exact same orientation and compatible sport/class/competition;
- start UTC within the configured tolerance;
- unique match after deduplication across sources;
- at least one identity-bearing official/provider observation; and
- no unresolved source/date failure covering the relevant date.

Fuzzy scores are ranking diagnostics only. They must never create an alias,
provider ID, fixture ID, or identity. Reversed orientation, duplicate
candidates, weak context, missing relevant date, stale/changed evidence, or
conflicting claims returns a typed unresolved reason.

### 3. Evidence-backed promotion path

When no safe candidate exists, the resolver requests generic evidence for the
target tuple (names, sport, competition context, date window), not a blank
match-specific catalog record. An operator or evidence collector supplies two
fresh HTTPS claims (official and independent) with exact names/start/status;
the resolver verifies snapshots and hashes, maps names to existing entities or
creates new canonical entities only with explicit adjudication, then appends
the observation and alias provenance to the ledger. The same observation can
resolve future drawings whenever the canonical entities and schedule match.

This keeps the official/independent and snapshot requirements from the current
catalog, but moves their durable output to reusable entity/competition/fixture
evidence. A source-native fixture ID may be retained only as that source's
identity; it is never fabricated as an API-Sports ID.

### 4. Run-scoped pinning and TOCTOU protection

At preparation, persist a `ResolutionSnapshot` containing the exact target
identity, selected canonical entities, source observations, UTC start,
source/snapshot hashes, resolver version, and semantic hash. Final collection
reloads the ledger and sources, requires the same resolution hash and target
fingerprint, and verifies freshness, status, time, and entity identity. Any
changed alias, source snapshot, source conflict, missing revalidation, or
unavailable relevant date produces typed fail-closed `NO BET`; it never falls
back to a stale alias or fuzzy candidate.

### 5. Fail-closed state machine and diagnostics

Use explicit states such as `RESOLVED`, `REVIEW_REQUIRED`, `SOURCE_MISSING`,
`SOURCE_FAILED`, `CONFLICT`, `STALE`, and `IDENTITY_DRIFT`. Persist provider
coverage per relevant UTC date and candidate explanations. Attention should
reference the target plus reason and generic evidence request; it should not
embed a future static catalog dependency. Retries may refresh sources or await
evidence, but cannot widen acceptance thresholds or turn a quota failure into
absence.

Publication remains gated on all 15 `RESOLVED` pins, exact drawing identity,
fresh revalidation, and valid timing/probability evidence. Any unresolved
order remains passive and emits zero package/marker/bet.

### 6. Migration and required regression coverage

- Import existing reviewed catalog records into the evidence ledger as
  immutable observations, preserving hashes and provenance; do not carry their
  drawing-specific selection key forward as the primary model.
- Keep a compatibility reader only for already pinned historical runs; new
  preparation must use the resolver.
- Add tests for the five 4965 cases, a different drawing reusing the same
  canonical teams, transliteration/rename (Iberia/Saburtalo), reversed names,
  duplicate candidates, missing relevant date, quota failure, stale snapshots,
  changed evidence, source disagreement, and TOCTOU mutation.
- Prove that fuzzy-only candidates stay unresolved, that accepted evidence is
  reusable across drawing IDs, and that no API-Sports fixture/team ID is
  synthesized.

The design preserves the current safety contract while changing the unit of
reuse from “this exact match in this exact drawing” to “this independently
verified canonical entity and schedule observation,” with every use still
bound to a fresh, hash-checked, fail-closed resolution snapshot.

## Reconciled rehearsal result (2026-08-03)

The verified evidence-only rehearsal is **13/15**, with unresolved orders **7
and 13**. Events 5, 10 and 12 are resolved by the executable ledger. Event 13's
supplied Real Salt Lake publications are retained for audit but rejected as
non-identity-bearing for the target; any official home/away or identity
conflict remains `CONFLICT`/fail-closed. It is not promoted into the ledger and
no reverse-orientation inference is allowed. The drawing remains not READY,
with no package or bet marker.
