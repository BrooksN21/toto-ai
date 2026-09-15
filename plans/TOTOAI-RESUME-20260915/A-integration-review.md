# Stage A integration review

Verdict: **PASS — narrow inert-library adoption only**.

Reviewed 2026-09-15, against production receipt checkpoint 17:18:18 MSK.
No P1/P2 findings in the requested integration scope. This is not Sports V3
model qualification, Stage F acceptance, publication approval, or operational readiness.

## Independently verified

- All 17 source/test final hashes match the adoption JSON. All original source
  hashes match manifest06 and the actual author files. Nine library modules and
  seven tests are byte-identical; only the declared generator test differs.
- Review06, manifest06, snapshots05/06 and delta05-to06 hashes match the receipt.
  Review06 acceptance remains limited to its deadline correction.
- Six protected entrypoint/config files and eight existing dependencies match
  their receipt pre-adoption hashes. No overwrite with obsolete child versions.
- `tests/test_sports_v3_generation.py:19` replaces the eager parallel import with
  real probability-library fixtures. Assertions in every original test compare
  equal by AST after normalizing only `req`/`ctx` names: **16 preserved**.
  `tests/test_sports_v3_generation.py:239` explicitly skips Stage F, moving its
  worker import inside the skipped test. Worker source is absent in production.
- `tests/test_sports_v3_library_isolation.py:23` exercises real source imports
  with audit guards; `:89` runs both library and production import directions.
  Independent run: **11 passed in 0.99s**, exit 0, subprocess ceiling 25 seconds.
  No bytecode or pytest cache; plugin autoload disabled. Imported production
  modules were not invoked as operational commands.
- Independent Ruff rerun using the receipt's final command: **18 files PASS**,
  exit 0, timeout 15 seconds.
- `A-library-adoption.md:14` discloses the unrun worker; `:25` explicitly disclaims
  real training, fitted artifacts, replay, quality lift, activation and profitability.

## Verification limits

The reported **99 passed / 1 skipped** focused suite is implementation evidence,
not an independent full rerun. This review reran only isolation and Ruff, and
performed hash/AST/diff inspection. It did not audit the entire repository,
runtime state, DB, jobs, consent, ledger, or drawing 5007. Protected-code hashes
are compared with the recorded before-state, not independently reconstructed Git
history. No live-state invariance beyond that code scope is certified.

The import guard blocks socket creation (including the tolerated, denied urllib3
capability probe), SQLite, subprocess execution, file writes and literal `.env`
reads. It is scoped regression evidence, not a general sandbox/security proof.

No operational CLI, training, full suite, Git, commit, push, PR, live checks, or
production edits were performed. Shell commands used the production cwd required
by the supplied project instructions; report writes are confined to this review
worktree. Stages B–F and old 7470/C7 work remain out of scope.

## Reviewed receipt bindings

- MD SHA-256: `a2c2be2e14a52b98345e978a54f8b7f237fab5b309dbffa58d8a4d886d235bc2`
- JSON SHA-256: `58bec415bf87455f29981aaf94fc56a7e68c4780fec0c22546f4bcb870b305e7`
- Generator test SHA-256: `8e566478e9ee09819e2dfa96d3c886dd6b96a14eff7dde6c28a84f583ea463ed`
- Isolation test SHA-256: `a16ce7e2b62168f3a16ed0125b6264dbd3c09c76ca07c7389f68258b144dda69`
