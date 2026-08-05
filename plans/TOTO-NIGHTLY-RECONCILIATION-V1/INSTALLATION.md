# TOTO-NIGHTLY-RECONCILIATION-INSTALL-V1

Installation and smoke verification date: 2026-07-30 (Europe/Moscow).

## Installed LaunchAgent

- Label: `com.totoai.nightly-reconciliation.v1`
- Installed plist:
  `/Users/turshevr/Library/LaunchAgents/com.totoai.nightly-reconciliation.v1.plist`
- SHA-256:
  `4a7302736e75e3eb3820acddb51223388ea3a5f518a9ac40d84225cb12907003`
- Mode/owner: `0600`, current user `turshevr`
- Domain: `gui/501`
- State after smoke: loaded, `not running`
- Runs after smoke: `1`
- Last exit code: `2`, corresponding to the controlled `PARTIAL` result below
- `RunAtLoad`: `false`
- Schedule: daily at `03:20` local macOS time
- Next scheduled run after installation: `2026-07-31 03:20 MSK`

The pre-existing passive morning agent
`com.totoai.morning-dispatcher.v1` remained loaded and unchanged.
No duplicate or conflicting nightly agent was present before installation.

## Artifact inspection

The installed plist is byte-identical to the generated candidate.

The wrapper uses only absolute project-local paths and runs:

- database: `/Users/turshevr/toto-ai/data/toto.db`
- project root: `/Users/turshevr/toto-ai`
- Python: `/Users/turshevr/toto-ai/.venv/bin/python`
- latest finished drawings: `30`
- maximum network attempts: `8`
- force: disabled (`--no-force`)
- timeout: `240` seconds
- backup retention: `7`
- state, RAW archive, request state, backups, stdout and stderr:
  under `/Users/turshevr/toto-ai`

The plist schedule is exactly `03:20`, its working directory is the project
root, and its stdout/stderr paths are project-local.

Negative inspection found no:

- API keys, tokens, passwords, `.env` loading, or other secrets;
- package generation;
- `build-brief`;
- betting or upload commands;
- `activate-evening`;
- morning-dispatch commands.

## Backup precondition

Before the smoke run, the implementation was verified to create an online
SQLite backup immediately before network/apply work, validate that backup with
`quick_check` and `foreign_key_check`, write a hash-bound manifest, set mode
`0600`, and retain seven known-good nightly backups.

## Manual smoke run

- Run ID: `20260730T123449533325Z-88726-0ab76a`
- Classification: `PARTIAL`
- Reason: `source_incomplete_or_transient`
- Duration: approximately 18 seconds
- Timed out: no
- Captured drawings:
  `4930, 4931, 4932, 4933, 4934, 4935, 4936, 4937`
- HTTP/network attempts: `8`
- Completed: `7`
- Source-incomplete: `1`
- Transient errors: `0`

Drawings 4930 and 4932–4937 were restored to 15 terminal results. Drawing
4931 remained source-incomplete at 14/15 and received a cooldown; no result or
VOID was invented.

### Data Health delta for the captured eight drawings

- Healthy: `0 -> 6`
- Unhealthy: `8 -> 2`
- Missing RAW snapshot reason count: `8 -> 0`
- Missing result snapshot reason count: `8 -> 1`
- Incomplete result reason count: remains `1`
- Invalid zero pool reason count: remains `1`

`PARTIAL` is an accepted controlled result for source-incomplete data. It is
not a process crash or an integrity failure.

## Backup and integrity evidence

- Backup:
  `/Users/turshevr/toto-ai/data/backups/toto-nightly-before-20260730T123450210809Z.db`
- Manifest:
  `/Users/turshevr/toto-ai/data/backups/toto-nightly-before-20260730T123450210809Z.manifest.json`
- Backup SHA-256:
  `7b9ac7729cc83f6086303bbb4012c2395e8d80912b2581a27e318b01235e477f`
- Manifest and actual backup hashes match.
- Backup mode: `0600`
- Backup `quick_check`: `ok`
- Backup foreign-key violations: `0`
- Main database `quick_check` after run: `ok`
- Main database foreign-key violations after run: `0`
- Maintenance lock held after run: no
- stderr: empty

Run report:

`/Users/turshevr/toto-ai/data/nightly-reconciliation/runs/20260730T123449533325Z-88726-0ab76a/report.json`

## No-bet proof

The wrapper/plist contain no package, brief, upload, betting, marker, evening
activation, or morning-dispatch commands.

Comparing package/bet/upload/marker artifact inventories immediately before
and after the smoke run produced no new files. No `.bet-ready` marker was
created. The smoke touched reconciliation data only.

After an additional stability wait, the nightly agent remained loaded,
`not running`, with `runs = 1`; it did not continuously restart.

## Decision

**GO** for unattended nightly reconciliation at 03:20 local time under the
installed bounded configuration.

The job remains non-betting and fail-closed. `PARTIAL` and `DEFERRED` are
expected controlled outcomes when an upstream source is incomplete or no work
is eligible. Any future `FAILED` result requires investigation before relying
on subsequent unattended runs.
