# Native Codex routing implementation handoff

Task: `TOTOAI-RESUME-20260915`. **PATCH_READY_NOT_ACTIVATED**.
Baseline `6b367e5` is parent-attested. No Git/stage/commit/push/PR operation.

## Work summary
Updated the two policy entrypoints plus a local routing guide and a machine-readable instruction record. Default routine Luna/low; bounded code Terra/medium; complex mathematics/architecture/critical review Astra/high. Main model unchanged. Max two active delegated workers (existing active child tasks count), no nesting, no full context fork, one bounded attempt and concrete blocker escalation. External model/proxy/Yandex bans and existing child-task scopes preserved.

## Verification
- RED: 13 new contracts failed before implementation.
- GREEN: 21 focused tests PASS (0.05s); Ruff PASS; JSON parse PASS.
- No native config/TOML created: local CLI 0.154.0, app 26.623.141536/4753 metadata does not supply a verified schema at the documented checked paths.
- Explicit native spawn fields are parent-attested; this worker has no callable native spawn tool. No inference test or agent launch.
- This is tested instruction policy, not runtime enforcement, a filesystem sandbox or verified automatic cost routing.

## Exact patch files and SHA-256
- `AGENTS.md`: `82f00f3aa8dc692f9a45a52c9fc23d142a2c5c95ecb79b145efd7e2154d45f64`
- `memory-bank/TOOLING_POLICY.md`: `36f11bef6d0afb28046ae81d95a04b95866403c4ede3e9e70bd61d5b76953888`
- `memory-bank/NATIVE_CODEX_ROUTING.md`: `bc404db80f77a72a7082ba99f91cf5049806b53e963811b33e8380c59a501952`
- `prompts/native-codex-routing.json`: `609fdd689e1111e8db39ab502ff905a1fb41b2d900810bdde7234a635c7c45c5`
- `tests/test_native_codex_routing_policy.py`: `3629d8cb048ff0163dd84509a0b91e972231b863d950ab09992a63d009f0756d`

## Finalizer / activation
Review and publish these scoped files plus this handoff pair. Policy must be committed and the commit exposed through a PR before activation. Parent must then verify callable native spawn parameters and enforce the two-worker cap; no fallback to external tools/CLI or new user-owned tasks if unavailable. No smoke agent ran.
No changes to production code, 5008 operations, DB, models, credentials, global settings or canonical live-state memory. No unfinished command/background process.
