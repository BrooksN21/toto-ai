# Parallel hash contract — GREEN, review pending

Task TOTOAI-RESUME-20260915. Native writer uses StrategyResult LF-terminated hash; archive and selector canonical hashes use comma-separated strings. They are distinct order-sensitive contracts, now explicitly labelled. Historical native schema1 reports keep LF semantics without rewriting any existing bytes. Reader computes both required hashes from the exact byte-bound control, never accepts an arbitrary alternate digest. Source report, final-input, plan, primary export and archive checks remain enforced.

Adjacent verified incompatibility: native export uses `30; 1; …`; delivery reader rejected its ASCII spaces. Reader now trims ASCII spaces per field after file-byte binding and rejects duplicate coupons, matching native export intent without altering generated packages.

RED3failed/5passed: native writer reports rejected and false alternate hash accepted. GREEN84passed2.84s (new contract+delivery+status suites), Ruff5PASS. Tests include current/legacy, reordered/tampered, wrong finalinput/plan/filehash, null/unknown semantics, duplicate export and valid-primary isolation. Genuine4999archive166coupons passes LF/comma and original file-byte hashes; no originals changed. This is not a claim of an actionable expired package.

Changed scope and SHA map: parallel-hash-contract-fix.json. No generation/scoring/selector/budget/deadline/consent/DB/C-source changes. Git inspection only; no commit/push/restart or live calculation.

## Activation handoff
Fresh Python processes read updated sources at startup. Existing watcher imports do not hot-reload. After independent review, parent should restart ONLY `com.totoai.status-watcher.v1.84b0f69e06487848` using its unchanged plan-bound LaunchAgent configuration, then check delivery. Do not restart/interfere with primary or sidecar calculations. ActualPID was not confirmed: permitted `ps -p16288` read returned operation-not-permitted, no bypass/restart attempted. Other already running Python processes also retain imported old code until they naturally exit; future scheduled fresh processes use the fix.

Remaining: independent review/publication, then controlled observer activation by operations owner. No promise that all unrelated evening stages will succeed.
