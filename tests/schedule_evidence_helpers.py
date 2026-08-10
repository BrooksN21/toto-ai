from __future__ import annotations

import json
from pathlib import Path


def write_empty_schedule_evidence_ledger(root: Path) -> Path:
    path = root / "data" / "schedule-evidence" / "ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-06T00:00:00Z",
                "observations": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return path
