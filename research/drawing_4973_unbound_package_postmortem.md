# Drawing 4973 unbound package postmortem

The file named `evening-4973-final-1644-package.txt` was not a production
scheduler publication. It was created at 16:59:32 Moscow time, after the
16:50 T-10 boundary, and had no scheduler identity, BET READY marker, durable
archive, or settlement binding. It is permanently classified as
`unbound_post_t10_research_evidence` and must never be offered for operator
upload.

Frozen evidence is stored in
`tests/fixtures/postmortem/drawing_4973_unbound_package.json`; coupon strings
are deliberately not copied into the regression fixture.

Against the official result `11X22XX122XX1X2`, its best coupon scored 7/15.
None of the 166 coupons reached 10+, 13+, 14+, or 15. The canonical quality-v2
paper candidate also failed, with a best score of 8/15 and no 10+ result.

This single drawing is failure evidence, not a basis for tuning probabilities
and not proof about future profitability. Its operational lesson is narrower:
operator-facing files must only come through the scheduler-owned, pre-T-10,
integrity-checked export gateway.
