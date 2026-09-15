# Event 9 evidence handoff — draw 4998

Task: TOTOAI-4996-4997-RECOVERY-20260904. Context only. Saved 2026-09-06T09:26:32.277815+00:00.

## Result
**Exact public fixture confirmed; reviewed target binding still required.**
Home **SK Beveren**, away **Oud-Heverlee Leuven / OH Leuven**. Scheduled on **2026-09-06 at 17:15 UTC = 20:15 MSK = 19:15 Europe/Brussels (UTC+02)**. Pro League 26/27, round 5, Freethielstadion. Sofa event **16361913**, teams **4859 / 2918**. Both team gender fields explicitly **M**. Senior first-team identity is supported by the professional Pro League context and club/pro/M filters; not a youth, reserve or women's fixture.

## Captures
All are raw, successful HTTPS response bodies, without credentials or retries.

- [official: https://www.skbeveren.be/voordeeltarief/](https://www.skbeveren.be/voordeeltarief/)
  - Captured 2026-09-06T09:23:57.421687+00:00 / 2026-09-06T12:23:57.421687+03:00 MSK.
  - Raw: `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/4998-event9-context/skbeveren-voordeeltarief.html`
  - SHA-256: `8b31688338c3c952774cf0e14360063c20d3c3d6230b5a9e728ac833ae0c7363`
- [independent: https://viasport.no/fotball/kamp/1558625](https://viasport.no/fotball/kamp/1558625)
  - Captured 2026-09-06T09:24:10.378379+00:00 / 2026-09-06T12:24:10.378379+03:00 MSK.
  - Raw: `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/4998-event9-context/viasport-fixture-1558625.html`
  - SHA-256: `23aaea93237a2d05b065bcbed294af20a3580feb0fe58c1e2aa9742d17a957b8`
- [independent: https://www.sofascore.com/nl/football/match/sk-beveren-oud-heverlee-leuven/tibsjXb](https://www.sofascore.com/nl/football/match/sk-beveren-oud-heverlee-leuven/tibsjXb)
  - Captured 2026-09-06T09:24:39.555507+00:00 / 2026-09-06T12:24:39.555507+03:00 MSK.
  - Raw: `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/4998-event9-context/sofascore-exact-match.html`
  - SHA-256: `6e961a8dfde9fe5a7ac9a372be5593a7a83c67ebf892492db5779c598eb410fb`

Sofa raw HTML contains `script#__NEXT_DATA__ /props/pageProps/event`: home/away identities, explicit gender M, status notstarted, Unix timestamp 1788714900. ViaSport JSON-LD independently states both team names, startDate 2026-09-06T17:15:00.000Z and EventScheduled. The official club table lists the same home/away pairing, date and 19:15; its timezone is **not explicit**, so venue-local Brussels interpretation is an inference corroborated by the two UTC sources. Parsed evidence JSONs preserve their source objects and are labelled extracted, never fabricated API responses.

## Identity and rejected evidence
- The official spelling is **SK Beveren**, not literal SC Beveren. No SC alias is asserted or installed.
- **OH Leuven** is directly tied to **Oud-Heverlee Leuven** by `name`/`shortName` in the same Sofa away-team object.
- The queue labels `СК Беверен` / `Ауд-Хеверле Левен` are target labels, not quotations or translations invented for a source. Sofa actually carries Russian `Васланд-Беверен` / `Оуд Хеверли`. A reviewer must approve this target-to-source binding rather than force exact-string equality.
- Existing event-09 Sofa search bytes were reused and hash-verified, but **rejected**: KSK Beveren team455097, historical 2008–2010 events. Current SK Beveren is team4859. Do not use the former as this match's confirmation.
- GOAL and TheSportsDB not_found context reused; neither collector was rerun. Other14 fixtures were not recollected.

## Access limitation
Sportschau web.open returned `is not safe to open (non-retryable error)`; exact URL/error is in access-errors.json. No retry or alternate access to that resource. It is not accepted evidence. The three accepted raw captures returned HTTP200.

## Next exact checkpoint
Parent/authorized reviewer reviews the saved three-source evidence for target180641, event_order8, drawing12102 and bound fingerprint in evidence-handoff.json. Reviewer identity/reviewed_at remain null. No ledger-ready payload or completed gate claim is made. Manual-wager intent is not source authorization.

Only this handoff directory was written. No ledger, DB, source, global memory/policy, scheduler, automation, Git, package or dispatcher mutation.
