# TotoBrief

TotoBrief is the current primary data source for TotoAI.

Stored data currently includes:
- BaltBet drawing history and statuses.
- Event names, championships, results, and scores.
- Pool probabilities.
- Bookmaker probabilities.
- Normalized odds where available.

Known data notes:
- Modern drawings may include `pool_*`, `bk_*`, and `norm_*` fields.
- Older drawings may include only pool fields.
- Some finished events may have missing result or score.
- Internal TotoBrief drawing id differs from public drawing number.
- Championship strings need whitespace normalization.
- Current/open event `start_at` may be null. TotoAI may recover missing starts
  from provider schedule metadata, but never changes the TotoBrief event value.
- Current/open event `name_en` may also be null. Exact/reviewed aliases remain
  preferred; constrained transliterated matching is allowed only when both
  Cyrillic team names have no English alternatives and the pair clears the
  versioned score, per-team, and runner-up-margin safety thresholds.
- Rare holiday/off-season drawings can span several days. They remain useful
  historical observations, while playable package generation requires all 15
  effective starts to be known within at most two inclusive Moscow calendar
  dates. Confirmed multi-day or unresolved timing is `NO BET`.
- Stored timing eligibility is bound to drawing ID and a canonical fingerprint
  of the exact fresh TotoBrief target. A stale or different target cannot reuse
  an earlier playable verdict.
- `run-drawing --open --bank <RUB>` pins that target at preflight, starts final
  work at T-20, fails closed inside every provider page/retry and at final
  publication at T-5, and writes linked deterministic operator reports in one
  rollback transaction. Preflight protects database/alias/cache inputs, and a
  second fresh target mutation becomes coupon-free `NO BET` before EV work. It
  never submits a bet; API-Sports consensus remains audit-only.
- A suppressed runner package remains explicit in both operator artifacts as
  zero-cost `NO BET`, with no coupons or payout, the full bank unused, and no
  modeled ROI. This structured computed/suppressed `ev` contract starts with
  runner manifest schema v2; schema v1 used `ev: null` when EV did not run.
- A progressive base and expansion collection may share an observation
  timestamp under deterministic clocks. SQLite resolves that latest-snapshot
  tie by append order so the final pass supplies the exact timing verdict.
- Missing TotoBrief `start_at` may be closed by a provider-neutral reviewed
  schedule record only after API-Sports complete required-date coverage proves
  a source-missing competition. The reviewed record requires agreeing official
  and independent snapshot-backed claims and exact drawing/fingerprint/event
  binding. It is never an API-Sports fixture and provides no market odds.
- A successfully revalidated reviewed schedule-only event uses the existing
  TotoBrief BK row with explicit `totobrief_bk_fallback` provenance. Missing,
  stale, changed, cancelled, conflicting, or TOCTOU evidence is `NO BET`, not
  an implicit probability fallback.
- A drawing-info payload can remain incomplete after the listing reports
  `finished`. Fifteen stored event/quote rows therefore do not prove result
  freshness. Reconciliation must continue until 15 terminal source outcomes
  and an immutable RAW-linked result snapshot exist.
- An active/expected detail cache is not authoritative after a transition to
  `finished`.
- `0/0/0` pool values are source data but not useful probability evidence.
- An empty result/score does not prove VOID. VOID/cancelled is terminal only
  with explicit source status and evidence.
- TotoBrief transport failures and absent local RAW are not proof that the
  source itself lacks data. They are tracked separately as transport
  exhaustion and no-local-evidence.

Related:
- [../memory-bank/DATA_NOTES.md](../memory-bank/DATA_NOTES.md)
- [../memory-bank/ARCHITECTURE.md](../memory-bank/ARCHITECTURE.md)
- [../prompts/research.md](../prompts/research.md)
