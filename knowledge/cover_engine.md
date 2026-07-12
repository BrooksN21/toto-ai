# Cover Engine

The Cover Engine generates greedy coupon packages from a brief and category.

Definitions preserved:
- Category 13 means maximum Hamming distance 2.
- Category 14 means maximum Hamming distance 1.
- Category 15 means exact match.
- A coupon covers a full-brief variant when Hamming distance is within the
  category maximum.

Current implementation notes:
- Expanded brief variants are cached.
- Coverage bitsets are cached by `(brief, category)`.
- Coverage is built by bounded outcome mutation instead of all-pairs Hamming
  scans.
- Greedy scoring and tie-break semantics are unchanged.

Regression requirements:
- Selected coupons must stay identical for representative cases.
- Coverage rate must stay identical.
- Worst minimum distance and guarantee result must stay identical.

Benchmark:
- `python -m toto_ai.cli benchmark-cover`
- Representative runtime improved from about 1.70s to about 0.04-0.05s.

Related:
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
- [../skills/algorithm-review.md](../skills/algorithm-review.md)
- [../skills/backtesting.md](../skills/backtesting.md)
