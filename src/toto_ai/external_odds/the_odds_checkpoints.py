from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from toto_ai.external_odds.collection import collect_target_external_odds
from toto_ai.external_odds.domain import ExternalOddsProvider, TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.the_odds_shadow import write_the_odds_shadow_reports

ShadowCheckpoint = Literal["morning", "control", "t10"]
_CHECKPOINTS = frozenset(("morning", "control", "t10"))
_COLLECTED = "COLLECTED"
_SKIPPED_QUOTA_RESERVE = "SKIPPED_QUOTA_RESERVE"


class _CheckpointProvider(ExternalOddsProvider, Protocol):
    @property
    def credit_state(self) -> Any: ...

    @property
    def credits_spent(self) -> int: ...

    @property
    def request_evidence(self) -> tuple[Any, ...]: ...

    def refresh_credit_state(self) -> Any: ...


@dataclass(frozen=True)
class ShadowCheckpointResult:
    checkpoint_id: str
    input_sha256: str
    manifest_path: Path
    collection_id: str | None
    status: str
    credits_spent: int
    credits_spent_this_run: int
    reused: bool


def checkpoint_input_sha256(
    target: TargetDrawing,
    *,
    checkpoint: str,
    aliases: dict[str, str],
    quota_reserve: int,
) -> str:
    _validate_checkpoint(checkpoint)
    if not isinstance(quota_reserve, int) or isinstance(quota_reserve, bool):
        raise ValueError("quota_reserve must be a non-negative integer")
    if quota_reserve < 0:
        raise ValueError("quota_reserve must be a non-negative integer")
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    payload = {
        "schema_version": 1,
        "provider": "the-odds-api",
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "target_fingerprint": fingerprint,
        "target_events": tuple(
            {
                "event_id": event.event_id,
                "event_order": event.event_order,
                "sport": event.sport,
                "championship": event.championship,
                "starts_at": (
                    None if event.starts_at is None else event.starts_at.isoformat()
                ),
                "home_team": event.home_team,
                "away_team": event.away_team,
                "home_team_en": event.home_team_en,
                "away_team_en": event.away_team_en,
                "bk_probabilities": event.bk_probabilities,
                "pool_probabilities": event.pool_probabilities,
            }
            for event in target.events
        ),
        "checkpoint": checkpoint,
        "quota_reserve": quota_reserve,
        "aliases": tuple(
            sorted((str(key), str(value)) for key, value in aliases.items())
        ),
    }
    return _sha256(payload)


def collect_shadow_checkpoint(
    *,
    target: TargetDrawing,
    checkpoint: str,
    provider_factory: Callable[[], _CheckpointProvider],
    session_factory: Any,
    aliases: dict[str, str],
    quota_reserve: int,
    report_dir: str | Path,
) -> ShadowCheckpointResult:
    input_sha256 = checkpoint_input_sha256(
        target,
        checkpoint=checkpoint,
        aliases=aliases,
        quota_reserve=quota_reserve,
    )
    drawing_label = str(target.drawing_number or target.drawing_id)
    root = Path(report_dir) / drawing_label / "checkpoints" / checkpoint
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        return _load_existing_checkpoint(
            manifest_path,
            expected_input_sha256=input_sha256,
            report_dir=report_dir,
        )
    if root.exists() and any(root.iterdir()):
        raise ValueError("checkpoint directory exists without a valid manifest")

    provider = provider_factory()
    credit_state = provider.refresh_credit_state()
    if credit_state.remaining is not None and credit_state.remaining <= quota_reserve:
        return _write_skipped_checkpoint(
            target=target,
            checkpoint=checkpoint,
            input_sha256=input_sha256,
            manifest_path=manifest_path,
            credits_remaining=credit_state.remaining,
        )
    snapshot = collect_target_external_odds(
        target,
        provider,
        session_factory,
        aliases,
    )
    if snapshot.provider != "the-odds-api":
        raise ValueError("checkpoint provider must be the-odds-api")
    paths = write_the_odds_shadow_reports(
        snapshot,
        request_evidence=tuple(getattr(provider, "request_evidence", ())),
        credit_state=provider.credit_state,
        credits_spent=provider.credits_spent,
        report_dir=report_dir,
    )
    evidence = {
        "json": _evidence_path(paths.json_path, report_dir),
        "csv": _evidence_path(paths.csv_path, report_dir),
        "markdown": _evidence_path(paths.markdown_path, report_dir),
    }
    checkpoint_id = _sha256(
        {
            "input_sha256": input_sha256,
            "collection_id": snapshot.collection_id,
            "evidence": evidence,
        }
    )
    payload = {
        "schema_version": 1,
        "activation_status": "NOT_ACTIVATED",
        "actionable": False,
        "status": _COLLECTED,
        "checkpoint": checkpoint,
        "checkpoint_id": checkpoint_id,
        "input_sha256": input_sha256,
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "target_fingerprint": snapshot.target_fingerprint,
        "collection_id": snapshot.collection_id,
        "credits_spent": provider.credits_spent,
        "credits_remaining": provider.credit_state.remaining,
        "evidence": evidence,
    }
    _write_immutable_json(manifest_path, payload)
    return ShadowCheckpointResult(
        checkpoint_id=checkpoint_id,
        input_sha256=input_sha256,
        manifest_path=manifest_path,
        collection_id=snapshot.collection_id,
        status=_COLLECTED,
        credits_spent=payload["credits_spent"],
        credits_spent_this_run=payload["credits_spent"],
        reused=False,
    )


def _write_skipped_checkpoint(
    *,
    target: TargetDrawing,
    checkpoint: str,
    input_sha256: str,
    manifest_path: Path,
    credits_remaining: int,
) -> ShadowCheckpointResult:
    checkpoint_id = _sha256(
        {
            "input_sha256": input_sha256,
            "status": _SKIPPED_QUOTA_RESERVE,
            "credits_remaining": credits_remaining,
        }
    )
    payload = {
        "schema_version": 1,
        "activation_status": "NOT_ACTIVATED",
        "actionable": False,
        "status": _SKIPPED_QUOTA_RESERVE,
        "checkpoint": checkpoint,
        "checkpoint_id": checkpoint_id,
        "input_sha256": input_sha256,
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "target_fingerprint": target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
        "collection_id": None,
        "credits_spent": 0,
        "credits_remaining": credits_remaining,
        "evidence": {},
    }
    _write_immutable_json(manifest_path, payload)
    return ShadowCheckpointResult(
        checkpoint_id=checkpoint_id,
        input_sha256=input_sha256,
        manifest_path=manifest_path,
        collection_id=None,
        status=_SKIPPED_QUOTA_RESERVE,
        credits_spent=0,
        credits_spent_this_run=0,
        reused=False,
    )


def _load_existing_checkpoint(
    manifest_path: Path,
    *,
    expected_input_sha256: str,
    report_dir: str | Path,
) -> ShadowCheckpointResult:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("checkpoint manifest must be a regular file")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("checkpoint manifest is invalid") from None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("activation_status") != "NOT_ACTIVATED"
        or payload.get("actionable") is not False
    ):
        raise ValueError("checkpoint manifest is invalid")
    if payload.get("input_sha256") != expected_input_sha256:
        raise ValueError("checkpoint input conflict")
    if (
        not isinstance(payload.get("checkpoint_id"), str)
        or not payload["checkpoint_id"]
    ):
        raise ValueError("checkpoint manifest is invalid")
    status = payload.get("status", _COLLECTED)
    if status not in {_COLLECTED, _SKIPPED_QUOTA_RESERVE}:
        raise ValueError("checkpoint manifest is invalid")
    collection_id = payload.get("collection_id")
    if status == _COLLECTED:
        if not isinstance(collection_id, str) or not collection_id:
            raise ValueError("checkpoint manifest is invalid")
    elif collection_id is not None:
        raise ValueError("checkpoint manifest is invalid")
    credits_spent = payload.get("credits_spent")
    if not isinstance(credits_spent, int) or isinstance(credits_spent, bool):
        raise ValueError("checkpoint manifest is invalid")
    if status == _COLLECTED:
        _validate_evidence(payload.get("evidence"), report_dir=report_dir)
    elif payload.get("evidence") != {}:
        raise ValueError("checkpoint evidence is invalid")
    return ShadowCheckpointResult(
        checkpoint_id=payload["checkpoint_id"],
        input_sha256=expected_input_sha256,
        manifest_path=manifest_path,
        collection_id=collection_id,
        status=status,
        credits_spent=credits_spent,
        credits_spent_this_run=0,
        reused=True,
    )


def _validate_evidence(value: object, *, report_dir: str | Path) -> None:
    if not isinstance(value, dict) or set(value) != {"json", "csv", "markdown"}:
        raise ValueError("checkpoint evidence is invalid")
    root = Path(report_dir).resolve()
    for item in value.values():
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("checkpoint evidence is invalid")
        relative = item["path"]
        digest = item["sha256"]
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("checkpoint evidence is invalid")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError("checkpoint evidence is invalid") from None
        if path.is_symlink() or not path.is_file():
            raise ValueError("checkpoint evidence is invalid")
        if _file_sha256(path) != digest:
            raise ValueError("checkpoint evidence hash mismatch")


def _validate_checkpoint(checkpoint: str) -> None:
    if checkpoint not in _CHECKPOINTS:
        raise ValueError("checkpoint must be morning, control, or t10")


def _evidence_path(path: Path, report_dir: str | Path) -> dict[str, str]:
    resolved_root = Path(report_dir).resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError:
        raise ValueError("shadow evidence must stay inside report_dir") from None
    if path.is_symlink() or not path.is_file():
        raise ValueError("shadow evidence must be a regular file")
    return {"path": str(relative), "sha256": _file_sha256(path)}


def _write_immutable_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("checkpoint manifest conflict")
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
