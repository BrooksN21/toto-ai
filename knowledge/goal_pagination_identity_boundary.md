# GOAL schedule pagination identity boundary

GOAL can repeat a fixture across pages or date endpoints with different capture
metadata and provider `updatedAt`. Full dataclass equality incorrectly treated
these observations as contradictory identities and aborted the whole schedule.

Schedule deduplication now compares the canonical raw fixture excluding only
the top-level `updatedAt` bookkeeping field. All other raw fields remain
conflict-sensitive, including IDs, teams, competition, kickoff, raw status,
scores and unclassified provider fields. Status aliases are not newly merged;
missing/unknown values are not inferred, and unknown or terminal events remain
ineligible. A real conflict still fails the collection closed.

Capture time, endpoint, request fingerprint and full raw payload hash identify
observations, not fixture contradictions. Equivalent observations select the
latest capture, with deterministic payload-hash/endpoint/fingerprint tie-breaks.
This prevents retaining pre-kickoff eligibility over a later capture. The
selected event keeps one complete observation; every original page snapshot
and its full raw hashes remain available through request evidence. The semantic
comparison hash never replaces the public payload or snapshot hashes.

`tests/test_goal_api_pagination_identity.py` uses synthetic sessions with real
network calls prohibited. Its portable fixture contains the exact duplicate raw
records extracted from two previously frozen, SHA-256-verified public GOAL
responses; source snapshot and raw-event hashes are retained in the fixture.
Regressions cover page order, metadata-only duplicates, capture across kickoff,
real contradictions, conservative status/score treatment and the downstream
collector's independent-candidate/non-promoting boundary.

This is a generic parser repair. It does not collect live drawing data, change
official-source/review requirements, promote a ledger candidate, or authorize
any wagering, scheduler or operator action.
