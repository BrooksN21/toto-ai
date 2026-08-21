# Drawing 4981 package audit — 2026-08-21

## Scope and refresh

Local-only comparison after the completed result refresh. No network or tests
were run in this comparison.

- Drawing: **4981** (internal ID `12050`); actual result: **`2X1121XXXX12XX2`**.
- Local result snapshot: `data/toto.db`, 15/15 complete; all event statuses are
  `resolved`; cancellations/postponements/missing results: **none**.
- Scheduler plan: `5caf88df9bdfe566`.
- FINAL_FRESH manifest: `reports/rehearsal/evening-4981-20260820T150000Z/last-known-good/checkpoints/final-01-20260820T144010323067Z-108415dd-85020d62588e/manifest.json`.
- Source package: `reports/rehearsal/evening-4981-20260820T150000Z/last-known-good/checkpoints/final-01-20260820T144010323067Z-108415dd-85020d62588e/package.csv`; SHA-256
  `805238e8dc0dc4fee192e17ec6a24781066b32331ecc67307a196a5a3332fd1e`.
- Paper payload: `reports/rehearsal/evening-4981-20260820T150000Z/paper-package/checkpoints/13d69c396a2e588b498bb38e/paper-package.txt`; SHA-256
  `85020d62588e237a51a0ad4fb972c21ec2c5acea20a718ef53851cf0fe4b3e8d`. Its 166 coupon lines
  match the scheduler package in order.

The retained package is PAPER/non-actionable evidence. The operator result is
expired `NO BET` after T-10; it is not treated as an upload surface.

## Package validation and outcome comparison

- Package size: **166 unique coupons**, 15 signs each.
- Stake/cost: **30 RUB per coupon; 4,980 RUB total** (`166 × 30`).
- Package CSV size: **9736 bytes**; paper payload size:
  **7968 bytes**.
- Exact actual vector present as a selected coupon: **no**.
- Actual result inside the package brief/union: **yes, 15/15 events**. Every
  position's union contains the observed sign; this is not an exact-vector
  guarantee.
- Best coupon: **8/15 hits** (`1 coupon`).
- Hit 13: **0**; hit 14: **0**; hit 15: **0**.
- Hit distribution: `{"1": 2, "2": 6, "3": 25, "4": 48, "5": 51, "6": 24, "7": 9, "8": 1}`.

### Per-event brief containment and result status

| Event | Match | Actual | Brief/union signs | Actual contained | Status | Score |
|---:|---|:---:|:---:|:---:|---|---|
| 1 | Кайрат-Алматы — Андерлехт | `2` | `1/X/2` | yes | resolved | 0 : 3 |
| 2 | Эгнация Рогожина — Лиллестрем | `X` | `1/X/2` | yes | resolved | 0 : 0 |
| 3 | ОФИ — ЦСКА София | `1` | `1/X/2` | yes | resolved | 3 : 0 |
| 4 | Сент-Труйден — Омония Никосия | `1` | `1/X/2` | yes | resolved | 1 : 0 |
| 5 | Линкольн Ред Импс — Ларн | `2` | `1/X/2` | yes | resolved | 0 : 2 |
| 6 | Лугано — Маккаби Тель-Авив | `1` | `1/X/2` | yes | resolved | 2 : 1 |
| 7 | Хартс — Рапид Вена | `X` | `1/X/2` | yes | resolved | 2 : 2 |
| 8 | Шамрок Роверс — КуПС | `X` | `1/X/2` | yes | resolved | 1 : 1 |
| 9 | Хайдук Сплит — Ракув | `X` | `1/X/2` | yes | resolved | 2 : 2 |
| 10 | Динамо Тирана — ФК Пафос | `X` | `1/X/2` | yes | resolved | 1 : 1 |
| 11 | Арсенал Тула — Ротор | `1` | `1/X/2` | yes | resolved | 2 : 1 |
| 12 | Шеффилд Уэнсдэй — Брэдфорд | `2` | `1/X/2` | yes | resolved | 0 : 1 |
| 13 | Райо Вальекано — Алавес | `X` | `1/X/2` | yes | resolved | 1 : 1 |
| 14 | Макара — Сантос | `X` | `1/X/2` | yes | resolved | 0 : 0 |
| 15 | Олимпия Асунсьон — Васко да Гама | `2` | `1/X/2` | yes | resolved | 1 : 4 |

## Missed events and diagnosis

For the best `8/15` coupon, the missed event positions are:

- Event 1: Кайрат-Алматы — Андерлехт — actual `2` (0 : 3)
- Event 4: Сент-Труйден — Омония Никосия — actual `1` (1 : 0)
- Event 6: Лугано — Маккаби Тель-Авив — actual `1` (2 : 1)
- Event 7: Хартс — Рапид Вена — actual `X` (2 : 2)
- Event 9: Хайдук Сплит — Ракув — actual `X` (2 : 2)
- Event 12: Шеффилд Уэнсдэй — Брэдфорд — actual `2` (0 : 1)
- Event 15: Олимпия Асунсьон — Васко да Гама — actual `2` (1 : 4)

Diagnosis: there was no source/result completeness defect. The package brief
covered every actual event sign, but the selected 166-combination package did
not contain the full actual 15-vector. Its best realized coupon reached only
`8/15`, so the loss was combinatorial package-selection coverage rather
than an uncontained event, cancellation, postponement, or missing result.
