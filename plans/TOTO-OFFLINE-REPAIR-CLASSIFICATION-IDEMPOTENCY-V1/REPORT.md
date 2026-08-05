# TOTO-OFFLINE-REPAIR-CLASSIFICATION-IDEMPOTENCY-V1

## Scope

Standalone, network-free bugfix only. No Git operation and no mutation of
`data/toto.db`.

## Defect

The second `repair-canonical-raw --apply` for drawing 4954 reported
`logical_changes=0` but changed:

```text
importer_loss_recoverable_local -> source_incomplete
```

The importer incorrectly reused network source-completeness classification for
an offline canonical-RAW repair.

## Corrected contract

Offline states:

```text
offline_repair_recoverable
offline_repair_recovered
offline_repair_no_changes
```

Network `source_incomplete` remains isolated in its
drawing/provider/source-keyed reconciliation state.

An erroneous historical `source_incomplete` raw classification is normalized
once only when all of the following hold:

1. exact canonical RAW snapshot, payload, metadata, source, endpoint, lifecycle
   and archive paths match;
2. the RAW is already fully incorporated in SQLite;
3. a complete result snapshot passes independent hash verification;
4. all persisted event results match that snapshot;
5. any VOID has explicit persisted HTTP(S) evidence.

Otherwise repair is a no-op with
`ambiguous_local_classification_manual_review`.

## Drawing 4954 network-free replay

Replay database:

```text
/private/tmp/toto-offline-repair-4954-v1/toto-4954-copy.db
```

Exact state:

| Stage | Classification | Logical changes | Status |
|---|---|---:|---|
| Before | `source_incomplete` | — | historical defect |
| Corrected apply | `offline_repair_recovered` | 1 | `repaired` |
| Second apply | `offline_repair_recovered` | 0 | `no_change` |

Proof:

- post-correction and second-run SQLite SHA-256 are identical:
  `f74b52d789dd21dd1323c7588ca4014f039760aba6d1577948f8ecae9526bc32`;
- logical database state is identical after the second run;
- reconciliation-state rows are unchanged;
- 62 archive files and their aggregate hash are unchanged;
- event 15 remains `result=*`, `result_status=NULL`, `score=""`; its terminal
  VOID is retained through the separately verified result snapshot;
- `quick_check=ok`;
- foreign-key violations: `0`;
- primary database SHA before/after is unchanged:
  `a98eeeb8ec2a7c8121589edace4c7a72c144893f330175277cf205bae995650e`.

Machine-readable replay output:

```text
/private/tmp/toto-offline-repair-4954-v1/replay-result.json
```

## Readiness

The bugfix is ready. Nightly reconciliation remains **NO-GO** until the full
wave-2 idempotency protocol is rerun with this code and one more bounded,
backed-up allowlist wave passes.
