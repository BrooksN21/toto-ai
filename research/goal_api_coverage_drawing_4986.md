# GOAL API coverage canary — drawing 4986

Date: 2026-08-25. Candidate-only research; no scheduler, ledger, package or
wager path was changed.

## Authentication and quota

- `GOAL_API_KEY` is present in the protected project `.env`.
- Authenticated `GET /v1/leagues` returned HTTP 200 and `success=true`.
- Reported free quota: 1,000 requests/day.
- After the bounded canary, 957 requests remained.
- One initial request using Python's default user agent returned an
  unstructured HTTP 403. Repeated requests with a stable TotoAI user agent
  succeeded. A future adapter must set an explicit user agent, retain bounded
  retry/diagnostics and treat 403 as a provider failure rather than an empty
  schedule.

`API_SPORTS_KEY` also remains configured. Its official status endpoint returned
HTTP 200 with semantic error `Your account is suspended`; it remains disabled
by provider state, not removed from TotoAI.

## Exact drawing coverage

The canary paged the official `GET /v1/fixtures/date/:date` endpoint across the
bounded 2026-08-25 through 2026-08-30 window. It loaded 3,265 fixture rows in
37 requests. Exact orientation and kickoff were then checked against all 15
TotoBrief targets.

All targets were present: **15/15**.

The first mechanical alias pass reported 12/15 because GOAL API uses these
short provider spellings:

- `Blackburn - Sheffield Utd`;
- `Cambridge Utd - Millwall`;
- `Vladimir - Krasnoye Znamya`.

Those are naming differences, not source gaps. The other twelve pairs matched
directly, including the three events unresolved by the existing
Sofascore/TheSportsDB union:

- `Ryazan - Spartak Tambov` at `2026-08-25T14:00:00Z`;
- `Vladimir - Krasnoye Znamya` at `2026-08-25T14:00:00Z`;
- `Abha - Al Khaleej` at `2026-08-25T16:05:00Z`.

## Interpretation

This is the first observed 15/15 candidate source for drawing 4986. It is not
a perpetual guarantee and does not authorize production use after one drawing.
GOAL API remains a new registered-account dependency whose terms disclaim
guaranteed fixture coverage. The next required evidence is a reusable
candidate-only adapter plus at least ten consecutive mixed-drawing canaries.

API-Sports must remain configured as a separate provider and be health-checked
without driving retries while its semantic status is suspended.
