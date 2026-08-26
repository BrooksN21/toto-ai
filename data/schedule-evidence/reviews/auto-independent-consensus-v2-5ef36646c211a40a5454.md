# Automated independent schedule consensus: Нацбанк ФК — Замалек

Reviewed at **2026-08-26T09:01:09.230992Z** for drawing 4987, event #10.

Scheduled kickoff: **2026-08-26T17:00:00Z**.

GOAL API and a separately fetched Sofascore event agree on canonical home/away identities and exactly on UTC kickoff. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp42pa9adtpg07l6077t0p
- Sofascore: https://www.sofascore.com/football/match/national-bank-of-egypt-zamalek-sc/tXqsBHgc#id:16738931
- GOAL matcher mode: `matched`
- Sofascore event ID: `16738931`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp42pa9adtpg07l6077t0p-9ff54e6028996924.json` — SHA-256 `9ff54e60289969244fe290ccd9319c7c1690387253bd2cf393ad748e0c929337`
- `snapshots/auto/sofascore-search-cmsvp42pa9adtpg07l6077t0p-6a64ebb6c93528f1.json` — SHA-256 `6a64ebb6c93528f1de6bc787d32b6c477c7c77b8786c9e78f9c8788fb1379fe9`
- `snapshots/auto/sofascore-16738931-421abbafe4388693.json` — SHA-256 `421abbafe438869354ff953aa8d1a05c155a780ea3d34c9c5a164f9980c699c5`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
