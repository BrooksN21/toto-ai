# Parallel report coupon-hash contract

`StrategyResult.package_sha256` hashes ordered UTF-8 coupon strings with a
newline after **each** coupon, including the last. Archive/selector canonical
package hashes instead join the same ordered strings with commas. Neither is
the SHA-256 of an operator-export file. Do not compare these digest domains.

New native comparison payloads label the existing LF hash with
`package_sha256_semantics` and expose a separately labelled
`canonical_package_sha256`. Definitions and strict reader validation live in
`src/toto_ai/package/hash_contract.py`.

Legacy compatibility is limited to native schema-1 reports with the known
artifact class and absent semantic fields: their existing `package_sha256`
means LF-terminated only. The reader recomputes it from the exact byte-bound
control coupons and independently checks the comma hash against the archive.
It never tries arbitrary alternative digests, changes coupon order, or
rewrites/re-signs historical reports. Unknown or explicit-null semantics fail
closed. Existing plan, final-input, file-byte and primary bindings remain.

Native exports contain ASCII spaces after semicolons. Delivery strips these
spaces only when parsing tokens; original file-byte hashes remain checked.
Duplicates, changed/reordered coupons and foreign bindings are rejected.

Regression tests: `tests/test_parallel_hash_contract.py` exercises the native
writer through the delivery consumer, not merely a hand-written report.
Already-running Python watchers do not hot-reload source changes. Operations
must explicitly activate a reviewed observer update; never restart calculations
or alter the scheduler/consent to repair an observer contract.
