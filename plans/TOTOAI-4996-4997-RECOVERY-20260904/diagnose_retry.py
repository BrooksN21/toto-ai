"""Bounded local preflight: reuse cached target and accepted evidence, no network."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from toto_ai import cli

root = Path("/Users/turshevr/toto-ai")
stem = "drawing-12100-20260905T133000Z-fe49b1ba85febf3a"
retry_path = (
    root / "data/scheduler/morning-dispatch/preflight" / stem / "retry-plan.json"
)
retry = json.loads(retry_path.read_text())
now = datetime.now(timezone.utc)
cached = cli.load_drawing_detail_cache(
    12100, cache_dir=root / "data/raw", max_age_seconds=None, allowed_root=root
)
target = cli.parse_target_drawing(cached.payload, fetched_at=cached.fetched_at)
fingerprint = cli.target_fingerprint(
    target.drawing_id, target.drawing_number, target.deadline, target.events
)
expected = retry["identity"]
assert (
    target.drawing_id,
    target.drawing_number,
    fingerprint,
    target.deadline.isoformat().replace("+00:00", "Z"),
) == (
    expected["drawing_id"],
    expected["drawing_number"],
    expected["drawing_fingerprint"],
    expected["deadline"],
)
engine = cli.init_db(root / "data/toto.db")
try:
    prepared = cli.prepare_drawing(
        target,
        (),
        session_factory=cli.get_session_factory(engine),
        provider="api-sports",
        schedule_evidence_ledger=root / "data/schedule-evidence/ledger.json",
        evaluated_at=now,
    )
    unresolved = cli._morning_unresolved_events(
        target=target, prepared=prepared, schedule_diagnostics=()
    )
    evidence = cli.MorningPreparedDrawing(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        deadline=target.deadline,
        drawing_fingerprint=fingerprint,
        detail_sha256=hashlib.sha256(
            json.dumps(
                cached.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        ).hexdigest(),
        preparation_status=prepared.status,
        mapped_count=prepared.mapped_count,
        eligibility_status=prepared.eligibility.status,
        span_days=cli._optional_morning_span_days(prepared.eligibility.span_days),
        external_coverage_count=prepared.external_coverage_count,
        baseline_only_event_orders=prepared.baseline_only_event_orders,
        unresolved_events=unresolved,
    )
    desired = bool(unresolved) and all(
        x.resolution_status == "timing_unknown" for x in unresolved
    )
    result = {
        "observed_at": now.isoformat(),
        "cached_fetched_at": cached.fetched_at.isoformat(),
        "network_calls": 0,
        "identity_match": True,
        "retry_stored_activate_evening": retry["activate_evening"],
        "retry_desired_activate_evening": desired,
        "evidence": asdict(evidence),
        "prepared": asdict(prepared),
    }
    dest = Path(__file__).with_name("retry-evidence-current.json")
    dest.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print(
        "IDENTITY_MATCH true; activate_evening stored=",
        retry["activate_evening"],
        "desired=",
        desired,
    )
    print(
        "PREPARED",
        prepared.status,
        "mapped=",
        prepared.mapped_count,
        "eligibility=",
        prepared.eligibility.status,
    )
    print("UNRESOLVED", [(u.event_order + 1, u.resolution_status) for u in unresolved])
    print("EVIDENCE", dest)
finally:
    engine.dispose()
