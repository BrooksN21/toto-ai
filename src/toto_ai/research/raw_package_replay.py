"""Verify RAW market inputs without inventing historical operator evidence.

This adapter currently stops at the native quality-v2 provenance boundary.
It deliberately does not replace the safety-aware selector with research EV top-N.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from toto_ai.collector.lifecycle import RawArchive, RawArchiveRecord
from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import validate_selection_provenance
from toto_ai.optimizer.strategy_comparison import FrozenStrategyInput
from toto_ai.optimizer.strategy_historical_benchmark import (
    frozen_input_from_raw_payload,
)
from toto_ai.totobrief_time import parse_totobrief_timestamp

DOMAIN = "CURRENT_CODE_RETROSPECTIVE_REPLAY_NOT_PROSPECTIVE"
_MANIFEST_KEYS = {
    "schema_version",
    "evidence_domain",
    "drawing_id",
    "drawing_number",
    "requested_bank",
    "stake",
    "raw",
}
_RAW_KEYS = {
    "payload_path",
    "metadata_path",
    "snapshot_sha256",
    "payload_sha256",
    "metadata_sha256",
    "captured_at",
}


@dataclass(frozen=True)
class ResearchInput:
    frozen: FrozenStrategyInput
    requested_bank: int
    source_snapshot_sha256: str
    source_payload_sha256: str
    source_metadata_sha256: str
    probability_input_sha256: str
    seed_material_sha256: str
    config: EVConfig
    evidence_domain: str = DOMAIN
    operator_compatible: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if (
            self.evidence_domain != DOMAIN
            or self.operator_compatible is not False
            or self.automatic_wagering is not False
        ):
            raise ValueError("research input cannot carry operator authority")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _object(path: Path, *, max_bytes: int = 2_000_000) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("input must be a bounded regular non-symlink file")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("captured_at must be a timestamp")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or set(value) - set("0123456789abcdef")
    ):
        raise ValueError("expected lowercase SHA-256")
    return value


def load_replay_input(manifest_path: str | Path) -> ResearchInput:
    """Validate genuine archive bytes, then project ONLY prediction-time fields."""
    manifest = _object(Path(manifest_path))
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError("unexpected/missing manifest fields")
    if manifest["schema_version"] != 1 or manifest["evidence_domain"] != DOMAIN:
        raise ValueError("unsupported research manifest")
    ref = manifest["raw"]
    if not isinstance(ref, dict) or set(ref) != _RAW_KEYS:
        raise ValueError("unexpected/missing raw reference fields")
    for key in ("drawing_id", "drawing_number", "requested_bank", "stake"):
        if type(manifest[key]) is not int or manifest[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if manifest["stake"] != 30 or manifest["requested_bank"] % 30:
        raise ValueError("research bank must be divisible by stake30")
    raw_path, meta_path = Path(ref["payload_path"]), Path(ref["metadata_path"])
    metadata = _object(meta_path, max_bytes=16_384)
    snapshot = _sha(ref["snapshot_sha256"])
    if raw_path.name != f"{snapshot}.json" or meta_path != raw_path.with_name(
        f"{snapshot}.meta.json"
    ):
        raise ValueError("archive filename/hash binding mismatch")
    for key in ("drawing_id", "drawing_number"):
        if metadata.get(key) != manifest[key]:
            raise ValueError("archive drawing identity mismatch")
    for key in ("snapshot_sha256", "payload_sha256", "metadata_sha256"):
        if metadata.get(key) != _sha(ref[key]):
            raise ValueError("declared archive hash mismatch")
    if metadata.get("captured_at") != ref["captured_at"]:
        raise ValueError("archive capture binding mismatch")
    if (
        metadata.get("schema_version") != 1
        or metadata.get("source") != "network"
        or metadata.get("lifecycle_status") != "active"
        or metadata.get("source_endpoint") != f"/drawing-info/{manifest['drawing_id']}"
    ):
        raise ValueError("only genuine active network captures are supported")
    _object(raw_path)
    record = RawArchiveRecord(
        snapshot_sha256=snapshot,
        payload_sha256=ref["payload_sha256"],
        metadata_sha256=ref["metadata_sha256"],
        drawing_id=manifest["drawing_id"],
        drawing_number=manifest["drawing_number"],
        captured_at=ref["captured_at"],
        source=metadata["source"],
        source_endpoint=metadata["source_endpoint"],
        lifecycle_status=metadata["lifecycle_status"],
        payload_path=raw_path,
        metadata_path=meta_path,
        created=False,
    )
    payload = RawArchive(raw_path.parent.parent).load(record)
    data = payload["data"]
    if data.get("number") != manifest["drawing_number"]:
        raise ValueError("payload drawing identity mismatch")
    if data.get("name") != "baltbet-main" or data.get("status") != "active":
        raise ValueError("only active BaltBet RAW is supported")
    if data.get("payments") not in (None, {}):
        raise ValueError("post-result payments in prediction input")
    captured = _timestamp(record.captured_at)
    deadline = parse_totobrief_timestamp(
        data.get("ended_at"), community="baltbet-main", field_name="ended_at"
    )
    if captured >= deadline - timedelta(minutes=10):
        raise ValueError("RAW capture must be strictly before historical T-10")
    # Never pass the source object or unknown fields to the model layer.
    clean_events = []
    for event in data["events"]:
        for field in ("result", "score"):
            if field not in event:
                raise ValueError(f"missing {field} sentinel")
            if event[field] not in (None, ""):
                raise ValueError("post-result event in prediction input")
        if event.get("result_status") not in (None, ""):
            raise ValueError("post-result status in prediction input")
        clean_events.append(
            {
                key: event.get(key)
                for key in ("id", "order", "name", "championship", "start_at")
            }
            | {
                "quotes": {
                    key: (event.get("quotes") or {}).get(key)
                    for key in (
                        "bk_win_1",
                        "bk_draw",
                        "bk_win_2",
                        "pool_win_1",
                        "pool_draw",
                        "pool_win_2",
                    )
                }
            }
        )
    clean = {
        "data": {
            key: data.get(key)
            for key in ("id", "number", "name", "ended_at", "pool_sum", "jackpot")
        }
        | {"events": clean_events}
    }
    effective = effective_selection_budget(
        requested_bank=manifest["requested_bank"],
        pool_sum=clean["data"]["pool_sum"],
        stake=30,
    )
    if effective < 30:
        raise ValueError("pool does not support one coupon")
    frozen = frozen_input_from_raw_payload(
        clean,
        captured_at=captured,
        bank=effective,
        stake=30,
    )
    config = EVConfig(
        bank=effective,
        stake=30,
        effective_budget=effective,
        mode="playable",
        package_safety_enabled=True,
        package_provenance_required=True,
    )
    _, _, probability_hash, seed_hash = validate_selection_provenance(
        None,
        frozen.bk_probability_matrix,
        config=config,
        required=True,
    )
    return ResearchInput(
        frozen,
        manifest["requested_bank"],
        snapshot,
        ref["payload_sha256"],
        ref["metadata_sha256"],
        probability_hash,
        seed_hash,
        config,
    )


def admit_generation(replay: ResearchInput) -> dict:
    """Expose the native coupling; never fake a scheduler/ledger or relax it."""
    _, reasons, _, _ = validate_selection_provenance(
        None,
        replay.frozen.bk_probability_matrix,
        config=replay.config,
        required=True,
    )
    return {
        "schema_version": 1,
        "evidence_domain": DOMAIN,
        "status": "BLOCKED_NATIVE_QUALITY_V2_PROVENANCE",
        "native_reasons": list(reasons),
        "core_coupling": "ev.package._select_safety_aware_package combines "
        "artifact-provenance failures with structural infeasibility before selection",
        "missing": ["genuine historical scheduler plan", "schedule evidence ledger"],
        "models": {
            name: {"status": "NOT_RUN", "reason": "exact control unavailable"}
            for name in ("quality-v2", "quality-v3", "robust")
        }
        | {
            name: {"status": "SKIPPED_NO_SPORTS"}
            for name in ("sports-shadow", "Sports-v3")
        },
        "packages_generated": 0,
        "executed_drawings": 0,
        "requested_drawings": 1,
        "operator_compatible": False,
        "automatic_wagering": False,
        "roi": None,
    }


def _write_exclusive(path: Path, document: dict) -> str:
    content = _canonical(document) + b"\n"
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    digest = hashlib.sha256(content).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("research output readback hash mismatch")
    return digest


def prepare_report(manifest_path: str | Path, output: str | Path) -> dict:
    replay = load_replay_input(manifest_path)
    directory = Path(output)
    directory.mkdir(exist_ok=False)
    document = asdict(replay)
    document["research_input_sha256"] = _digest(document)
    input_hash = _write_exclusive(directory / "research-input.json", document)
    report = admit_generation(replay)
    report.update(
        input_file_sha256=input_hash,
        research_input_sha256=document["research_input_sha256"],
        drawing_number=replay.frozen.drawing_number,
        requested_bank=replay.requested_bank,
        effective_bank=replay.frozen.bank,
        coupon_capacity=replay.frozen.max_coupons,
        input_only=True,
    )
    _write_exclusive(directory / "generation-blocked.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "generate"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare_report(args.manifest, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if args.command == "prepare" else 2


if __name__ == "__main__":
    raise SystemExit(main())
