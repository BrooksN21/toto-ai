# G1 main import-only finish — PASS; wrapper compatibility pending

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Only `tests/test_final_hybrid_g1_integration.py` changed.
Current-main Ruff I001 corrected; no rules/ignores or functional code changes.
Identical imports/non-import AST verified. Before `6b07250aad6c1572bca073faf815d07ed5131da7ebfa77643ad6d87bbbe36302`;
after `880463b07461334f6d88b0061f316bc0d8c20088e7e1853dc9fb9b335a20daf7`. Previous integration receipt/history preserved.

- Target test-file: **15 PASS in1.03s**,25s command bound. No whole96 repeat.
- Ruff all9 integration files: **PASS**,15s bound.
- All other8 integration and7 protected source/plan hashes passed after tests.
- Audit blocked one socket.bind attempt; tests passed nonetheless. A subsequent
  receipt assertion expecting zero denied attempts failed; this was not a test
  or lint failure. No bind was permitted, no guard weakened, no blind rerun.
  Logs/runtime preserve this limitation; do not claim zero attempted actions.
- No jobs/wrapper/seed/authorization/API/DB or activation change; no owned process.

Exact patch: G1_MAIN_IMPORT_ONLY.patch. Hashes/runtime/harness:
G1_MAIN_IMPORT_ONLY_RECEIPT.json. DONE: code/lint. NEXT: wait only for ab34
wrapper-parser compatibility handoff/verdict before operational rebind/opt-in;
no new cache dependency, setup/reuse invocation, research upload or PLAY claim.
