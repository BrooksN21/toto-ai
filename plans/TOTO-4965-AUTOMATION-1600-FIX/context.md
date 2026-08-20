# TOTO-4965-AUTOMATION-1600-FIX — context

## Scope read

Read `AGENTS.md` and all files in `memory-bank/`. Relevant architecture says the generic morning dispatcher is passive by default; reviewed schedule evidence is opt-in and must be explicitly wired, while generation and activation are separate.

## Rehearsal LaunchAgent

Files:
- `reports/rehearsal/bootstrap-4965/1750/totoai-morning-preanalysis.plist`
- `reports/rehearsal/bootstrap-4965/1750/run-morning-preanalysis.sh`
- `reports/rehearsal/bootstrap-4965/1750/logs/morning.stdout.log`
- `reports/rehearsal/bootstrap-4965/1750/logs/morning.stderr.log`

The plist label is `com.totoai.bootstrap-4965.v1`, with a generated wrapper as its only `ProgramArguments`, and scheduled historical/bootstrap times through 2026-08-04 16:30. The wrapper invokes:

```text
python -m toto_ai.cli morning-dispatch ... --activate
```

It passes bank/stake, env/project/state/scheduler roots, DB, aliases, raw/cache paths and rate state, but **does not pass `--reviewed-schedule-catalog`**. It retries the command up to three times, sleeping 60 seconds. Its EXIT trap restores the generic dispatcher after 16:30.

Stdout repeatedly reports `status=deferred`, `reason=ACTION REQUIRED: unresolved 5/15`, with a reviewed-schedule queue. Stderr shows every attempt failing at CLI validation with:

```text
existing preflight text artifact conflicts: .../preflight/drawing-12004-20260804T150000Z-559c7615626b624c/notify.command
```

## Exact conflict source

`src/toto_ai/runner/morning_dispatch.py:1273-1279`, `_write_text_idempotent()`:

- computes exact UTF-8 expected bytes;
- if the path exists and is a symlink, non-file, or byte-different, raises `ValueError("existing preflight text artifact conflicts: {path}")`;
- otherwise returns idempotently;
- absent files are atomically created.

The `notify.command` write is at `morning_dispatch.py:976-980`, inside preflight escalation artifact generation. Thus the error is an artifact-integrity/idempotency failure, not a scheduler execution error.

## CLI / scheduler path

`src/toto_ai/cli.py:3057+` registers `morning-dispatch`; option `--reviewed-schedule-catalog` is optional at `3078-3080` and is forwarded into `MorningDispatchConfig` at `3112-3116`, then into preparation at `3166-3172`.

`src/toto_ai/cli.py:2909+` (`_prepare_morning_drawing`) forwards the catalog to preparation and automatically supplies the repository schedule-evidence ledger when `data/schedule-evidence/ledger.json` exists (`3005-3014`). The preparation call therefore has two distinct inputs: the optional reviewed catalog and the auto-discovered schedule-evidence ledger.

`src/toto_ai/runner/scheduler.py` carries the same optional reviewed-catalog field through plan/config and generated commands (`197-203`, `670-726`, `1135-1195`, `2131-2140`, `2169-2179`). Scheduler execution itself is launched by the generated wrapper as `python -m toto_ai.cli scheduler-execute` (`4897-4901`); it is not the command used by this bootstrap wrapper.

## Why the new resolver is not invoked

The bootstrap wrapper is stale/incomplete for the new reviewed-evidence path: it invokes `morning-dispatch --activate` without `--reviewed-schedule-catalog`, so the catalog-backed resolver cannot be constructed or used. The CLI accepts the option, but the wrapper never supplies it. The repository ledger is auto-wired only if present and is a separate schedule-evidence input; it does not substitute for the reviewed catalog required by unresolved `reviewed_schedule` items.

Additionally, this run never reaches any later schedule-evidence/scheduler path because preflight escalation tries to recreate the existing `notify.command` and aborts first. The existing artifact is content-different (or otherwise non-regular/symlink), so `_write_text_idempotent` fails before a successful deferred/next-attempt flow can proceed. The concrete first blocker is therefore the conflicting preflight artifact; after that is fixed, the wrapper still needs explicit reviewed-catalog wiring for the new resolver path.
