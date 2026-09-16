# 5008 Sports-v3 sealed-feature consumer review

**Task:** `TOTOAI-RESUME-20260915`  
**Verdict:** `ACCEPT_12_EXACTLY_BK_FALLBACK_3`

Reviewed the sealed original rows, roster and hash manifest. The 12 accepted
orders are `0–6, 10–14`; each decision binds the original row SHA-256, exact
roster `row_id`, provider fixture ID and kickoff. `derive_reviewed` replayed
successfully and produced only identity-status copies.

Orders `7`, `8`, and `9` (one-based positions 8–10) have no ACCEPT decision:
they remain `BK_FALLBACK_NO_PROVIDER_FIXTURE`, with no provider fixture,
kickoff or invented Sports feature row.

The frozen model file hash matches the manifest. Its full schema has 53
fields; its 26 non-zero Sports-weight fields are supplied from observed
history-derived values. Null optional fields remain null rather than synthetic
zero values. All accepted rows have a pre-kickoff decision cutoff and only
terminal history completed before that cutoff. No 5008 outcome label, fit,
inference, operator export, DB, scheduler or consent action was used.

Artifacts:

- `reports/rehearsal/TOTOAI-RESUME-20260915/sports-v3-packages-v1/5008-feature-review/consumer-decisions.json`
- `reports/rehearsal/TOTOAI-RESUME-20260915/sports-v3-packages-v1/5008-feature-review/derived-reviewed-rows.json`
- `reports/rehearsal/TOTOAI-RESUME-20260915/sports-v3-packages-v1/5008-feature-review/review.json`
