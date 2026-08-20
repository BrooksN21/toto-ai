# TOTO-4965-AUTOMATION context

Collected read-only on **2026-08-03 18:19:53 MSK (UTC+03:00)**. No code,
database, scheduler, service, or Git state was changed while collecting this
report.

## Active drawing

- Visible drawing: **4965**
- Internal drawing ID: **12004**
- Betting deadline: **2026-08-04 18:00 MSK**
  (`2026-08-04T15:00:00Z`)
- Fingerprint:
  `559c7615626b624cdd5ebefa782c6b96593ff9fb4dfcdbd18a3e6155f3c17af8`
- Latest observation: **2026-08-03 18:13:20 MSK**
- Preparation: **DEFERRED**, mapped **10/15**, unresolved **5/15**
- Unresolved events: orders **5, 7, 10, 12, 13**
- Activation: `not_requested`; no evening plan or drawing-specific evening
  LaunchAgent exists yet.

## Drawing-specific bootstrap automation

- Loaded label: `com.totoai.bootstrap-4965.v1`
- Plist:
  `/Users/turshevr/Library/LaunchAgents/com.totoai.bootstrap-4965.v1.plist`
- State at inspection: **not running**
- Completed calendar launches: **2**
- Last exit code: **2**, consistent with the persisted deferred result
  `ACTION REQUIRED: unresolved 5/15`
- Each calendar launch performs at most three `morning-dispatch --activate`
  attempts, separated by 60 seconds.
- The 17:50 and 18:10 launches ran. Their six total attempts remained at
  10/15. Drawing-specific stderr is empty.
- Configured calendar triggers, MSK:
  - 2026-08-03 **17:50** — completed
  - 2026-08-03 **18:10** — completed
  - 2026-08-03 **18:40** — pending
  - 2026-08-03 **20:30** — pending
  - 2026-08-04 **08:00** — pending
  - 2026-08-04 **10:30** — pending
  - 2026-08-04 **12:00** — pending

## Other scheduler state and overlap

- Generic passive label `com.totoai.morning-dispatcher.v1` is also loaded and
  runs daily at **08:00, 10:30, and 12:00 MSK**. It does **not** pass
  `--activate`.
- Therefore, on 2026-08-04 the generic passive job and the drawing-specific
  activation-capable bootstrap are both scheduled at **08:00, 10:30, and
  12:00**. This is duplicate collection/preparation work and may consume extra
  provider requests, although the dispatcher is intended to be idempotent.
- A passive retry-plan JSON exists but is not installed as a LaunchAgent. Its
  planned times are **12:00, 14:00, 15:00, 16:00, and 16:30 MSK** on
  2026-08-04, with hard stop **17:00 MSK**. It has
  `activate_evening=false`.
- `com.totoai.nightly-reconciliation.v1` is loaded separately; it is unrelated
  to package activation for drawing 4965.

## Exact recommended trigger times

Use one activation-capable drawing-4965 sequence, without duplicate passive
launches:

1. **2026-08-03 18:40 MSK**
2. **2026-08-03 20:30 MSK**
3. **2026-08-04 08:00 MSK**
4. **2026-08-04 10:30 MSK**
5. **2026-08-04 12:00 MSK**
6. If still unresolved: **2026-08-04 14:00 MSK**
7. If still unresolved: **2026-08-04 15:00 MSK**
8. If still unresolved: **2026-08-04 16:00 MSK**
9. Final preflight retry: **2026-08-04 16:30 MSK**

Do not schedule preparation at or after **17:00 MSK** (T-60). If preparation
becomes strict READY 15/15 early enough, the activation-capable dispatcher can
create the ordinary schema-v5 evening sequence for **17:15, 17:30, 17:40,
17:44, and 17:50 MSK**. Package publication remains manual; no automatic bet
placement exists.

## Immediate factual conclusion

Several near-term launches already exist. The next loaded trigger is
**2026-08-03 18:40 MSK**. No additional immediate trigger is necessary before
then. The operational blocker is not absence of scheduling; it is unresolved
event identity for 5 of 15 matches, so the system correctly has not created an
evening package plan.
