from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from toto_ai.sports_stats import final_hybrid_sidecar


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_hashed(path: Path, payload: dict[str, object]) -> bytes:
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    content = _canonical(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _retry_fixture(tmp_path: Path) -> SimpleNamespace:
    now = datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)
    output = tmp_path / "scheduler-output"
    plan_path = output / "scheduler-plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text('{"immutable":"plan"}\n', encoding="utf-8")
    plan = SimpleNamespace(
        plan_id="0123456789abcdef",
        drawing=6001,
        drawing_id=16001,
        output_dir=output,
        publish_deadline=now + timedelta(minutes=10),
    )
    sidecar_root = output / "parallel-challenger"
    wrapper = sidecar_root / final_hybrid_sidecar.PARALLEL_SIDECAR_WRAPPER_FILENAME
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o700)
    status_path = sidecar_root / "output" / "sidecar-status.json"
    _write_hashed(
        status_path,
        {
            "schema_version": 2,
            "status": "SKIPPED_OPERATOR_NOT_READY",
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "drawing_id": plan.drawing_id,
            "scheduler_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            "started_at": (now - timedelta(minutes=15)).isoformat(),
            "observed_at": (now - timedelta(minutes=1)).isoformat(),
            "reason": "operator PLAY was not ready before sidecar safe start",
            "automatic_wagering": False,
        },
    )
    operator_path = output / "operator-result.json"
    operator_bytes = _write_hashed(
        operator_path,
        {
            "schema_version": 3,
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "drawing_id": plan.drawing_id,
            "run_id": "final-generic",
            "decision": "PLAY",
            "actionable": True,
            "expires_at": plan.publish_deadline.isoformat(),
            "automatic_wagering": False,
        },
    )
    return SimpleNamespace(
        now=now,
        plan=plan,
        plan_path=plan_path,
        status_path=status_path,
        wrapper=wrapper,
        operator_path=operator_path,
        operator_bytes=operator_bytes,
    )


def _retry(case: SimpleNamespace, launcher):
    return final_hybrid_sidecar.retry_parallel_sidecar_after_operator_publication(
        plan=case.plan,
        scheduler_plan_path=case.plan_path,
        observed_at=case.now,
        process_launcher=launcher,
    )


def test_skipped_not_ready_retries_when_exact_operator_becomes_ready(tmp_path):
    case = _retry_fixture(tmp_path)
    launched = []

    result = _retry(case, lambda *args, **kwargs: launched.append((args, kwargs)))

    assert result.status == "STARTED"
    assert result.operator_result_sha256 == json.loads(
        case.operator_bytes
    )["record_sha256"]
    assert launched[0][0][0] == [str(case.wrapper)]


def test_retry_is_exactly_once_for_same_ready_operator_state(tmp_path):
    case = _retry_fixture(tmp_path)
    launched = []

    def launcher(*args, **kwargs):
        launched.append((args, kwargs))

    first = _retry(case, launcher)
    second = _retry(case, launcher)

    assert first.status == "STARTED"
    assert second.status == "ALREADY_STARTED"
    assert first.operator_result_sha256 == second.operator_result_sha256
    assert len(launched) == 1


def test_retry_does_not_start_at_or_after_operator_cutoff(tmp_path):
    case = _retry_fixture(tmp_path)
    case.now = case.plan.publish_deadline
    launched = []

    result = _retry(case, lambda *args, **kwargs: launched.append((args, kwargs)))

    assert result.status == "SKIPPED_POST_CUTOFF"
    assert launched == []


def test_retry_fails_closed_on_hash_valid_malformed_sidecar_identity(tmp_path):
    case = _retry_fixture(tmp_path)
    malformed = json.loads(case.status_path.read_text(encoding="utf-8"))
    malformed.pop("record_sha256")
    malformed["plan_id"] = "fedcba9876543210"
    _write_hashed(case.status_path, malformed)
    launched = []

    result = _retry(case, lambda *args, **kwargs: launched.append((args, kwargs)))

    assert result.status == "IDENTITY_MISMATCH"
    assert launched == []


def test_retry_hook_preserves_primary_operator_bytes_and_never_waits(tmp_path):
    case = _retry_fixture(tmp_path)

    class Process:
        def wait(self):
            raise AssertionError("primary publication must not wait for sidecar retry")

    launched = []

    def launcher(*args, **kwargs):
        launched.append((args, kwargs))
        return Process()

    before = case.operator_path.read_bytes()
    result = _retry(case, launcher)

    assert result.status == "STARTED"
    assert case.operator_path.read_bytes() == before
    assert len(launched) == 1
