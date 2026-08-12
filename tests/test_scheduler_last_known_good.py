from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.runner.scheduler import (
    SchedulerIntegrityError,
    SchedulerPhaseResult,
    _freeze_authoritative_drawing,
    _load_last_known_good,
    build_scheduler_plan,
    execute_scheduler_tick,
)

ENDED_AT = datetime(2032, 2, 3, 12, 0, tzinfo=timezone.utc)


def _plan(tmp_path: Path, *, bank: int = 4980, freeze_authority: bool = True):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "aliases.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "toto.db").touch()
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4972,
        drawing_id=12024,
        ended_at=ENDED_AT,
        bank=bank,
        stake=30,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )
    if freeze_authority:
        _freeze_authoritative_drawing(plan, "a" * 64)
    return plan


def _coupon(index: int) -> str:
    symbols = "1X2"
    values = []
    for _ in range(15):
        index, remainder = divmod(index, 3)
        values.append(symbols[remainder])
    return "".join(values)


def _candidate(
    *,
    bank: int = 4980,
    stake: int = 30,
    drawing_fingerprint: str = "a" * 64,
) -> SchedulerPhaseResult:
    count = bank // stake
    rows = ["rank,coupon,gross_ev,net_ev"]
    for rank in range(1, count + 1):
        gross = 1.20 - rank / 100000
        rows.append(f"{rank},{_coupon(rank - 1)},{gross:.5f},{gross - 1:.5f}")
    package = ("\n".join(rows) + "\n").encode()
    return SchedulerPhaseResult.candidate_package(
        package,
        reason="validated paper candidate",
        effective_bank=count * stake,
        selected_count=count,
        selected_cost=count * stake,
        drawing_fingerprint=drawing_fingerprint,
        probability_input_sha256="b" * 64,
        source_captured_at=ENDED_AT - timedelta(minutes=45),
    )


class _Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


def _tick(plan, runner, clock):
    return execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=lambda seconds: setattr(
            clock, "current", clock.current + timedelta(seconds=seconds)
        ),
    )


def _operator_payload(plan):
    return json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )


def _upload_lines(path: Path, *, stake: int, expected_count: int) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == expected_count
    assert len(lines) == len(set(lines))
    for line in lines:
        fields = line.split("; ")
        assert fields[0] == str(stake)
        assert len(fields) == 16
        assert set(fields[1:]) <= {"1", "X", "2"}
    return lines


def _rewrite_checkpoint(plan, mutate):
    pointer_path = plan.output_dir / "last-known-good" / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    manifest_path = Path(pointer["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    from toto_ai.runner import scheduler as scheduler_module

    manifest["manifest_sha256"] = scheduler_module._sha256_bytes(
        scheduler_module._canonical_json_bytes(unsigned)
    )
    manifest_bytes = scheduler_module._canonical_json_bytes(manifest) + b"\n"
    manifest_path.write_bytes(manifest_bytes)
    pointer["manifest_sha256"] = scheduler_module._sha256_bytes(manifest_bytes)
    pointer_path.write_text(
        json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_4972_refresh_429_and_slow_final_deliver_lkg_before_t10(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.preflight_at)
    final_deadlines = []

    def runner(context):
        if context.scheduler_phase == "warmup":
            return _candidate()
        if context.scheduler_phase == "refresh":
            raise TotoBriefRequestError(
                "HTTP 429",
                endpoint="/drawing-info/12024",
                attempts=4,
                status_code=429,
                category="http",
            )
        if context.scheduler_phase == "final":
            assert context.phase_deadline is not None
            final_deadlines.append(context.phase_deadline)
            clock.current = context.phase_deadline
            raise TimeoutError("simulated slow final")
        return SchedulerPhaseResult.completed("diagnostic ok")

    assert _tick(plan, runner, clock) is None
    lkg_manifest = plan.output_dir / "last-known-good" / "current.json"
    assert lkg_manifest.is_file()
    early = _operator_payload(plan)
    early_upload = Path(early["coupon_path"])
    assert early["operator_status"] == "LAST_KNOWN_GOOD_DEGRADED"
    _upload_lines(early_upload, stake=30, expected_count=166)

    clock.current = plan.fallback_at
    assert _tick(plan, runner, clock) is None
    assert lkg_manifest.is_file()

    clock.current = plan.final_at
    assert _tick(plan, runner, clock) is None
    assert final_deadlines == [
        plan.actionable_publication_deadline
    ]
    # Availability is established by warmup and survives a failed final;
    # it does not depend on a retry acquiring the scheduler lock.
    after_final = _operator_payload(plan)
    assert after_final["coupon_path"] == str(early_upload)
    assert Path(after_final["coupon_path"]).is_file()

    clock.current = plan.retry_at
    result = _tick(plan, runner, clock)

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is not None and result.package_path.is_file()
    assert clock.current < plan.publish_deadline
    assert final_deadlines == [
        plan.actionable_publication_deadline,
        plan.actionable_publication_deadline,
    ]
    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["operator_status"] == "LAST_KNOWN_GOOD_DEGRADED"
    assert status["provenance"] == "LAST_KNOWN_GOOD"
    assert status["staleness_seconds"] > 0
    operator = _operator_payload(plan)
    assert operator["coupon_path"] == str(result.package_path)
    _upload_lines(result.package_path, stake=30, expected_count=166)
    assert not tuple(plan.output_dir.rglob(".bet-ready"))


def test_final_dns_outage_preserves_refresh_lkg_before_t10(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.fallback_at)
    dns_calls = 0

    def runner(context):
        nonlocal dns_calls
        if context.scheduler_phase == "refresh":
            return _candidate()
        if context.scheduler_phase == "final":
            dns_calls += 1
            raise TotoBriefRequestError(
                "TotoBrief request failed after 4 attempt(s): ConnectionError",
                endpoint=f"/drawing-info/{plan.drawing_id}",
                attempts=4,
                category="dns",
                original_transport_message="failed to resolve totobrief.com",
                exception_chain=(
                    "ConnectionError",
                    "MaxRetryError",
                    "NameResolutionError",
                    "gaierror",
                ),
            )
        return SchedulerPhaseResult.completed("diagnostic ok")

    assert _tick(plan, runner, clock) is None
    before_dns = _operator_payload(plan)
    package_path = Path(before_dns["coupon_path"])
    _upload_lines(package_path, stake=30, expected_count=166)

    clock.current = plan.final_at
    assert _tick(plan, runner, clock) is None
    after_final = _operator_payload(plan)
    assert after_final["operator_status"] == "LAST_KNOWN_GOOD_DEGRADED"
    assert after_final["coupon_path"] == str(package_path)

    clock.current = plan.retry_at
    result = _tick(plan, runner, clock)

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.package_path == package_path
    # The 300-second final-runtime floor suppresses the last retry that could
    # not finish before the actionable publication cutoff.
    assert dns_calls == 7
    assert clock.current < plan.publish_deadline
    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["operator_status"] == "LAST_KNOWN_GOOD_DEGRADED"
    assert status["provenance"] == "LAST_KNOWN_GOOD"
    assert not tuple(plan.output_dir.rglob(".bet-ready"))

    source_package_path = package_path.parent / "package.csv"
    assert source_package_path.is_file()
    clock.current = plan.publish_deadline
    assert _tick(plan, runner, clock) is None

    expired = _operator_payload(plan)
    assert expired["operator_status"] == "NO_BET"
    assert expired["coupon_path"] is None
    assert "expired at T-10" in expired["reason"]
    assert not package_path.exists()
    assert source_package_path.is_file()


def test_no_lkg_emits_early_no_bet_on_retry_failure(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.retry_at)

    def runner(context):
        assert context.phase_deadline == plan.actionable_publication_deadline
        clock.current = context.phase_deadline
        raise TimeoutError("simulated retry timeout")

    result = _tick(plan, runner, clock)

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.package_path is None
    assert clock.current < plan.publish_deadline
    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["operator_status"] == "NO_BET"
    assert "last-known-good" in status["reason"]


def test_fresh_final_atomically_upgrades_lkg_without_play(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.preflight_at)

    def runner(context):
        return _candidate()

    assert _tick(plan, runner, clock) is None
    before = json.loads(
        (plan.output_dir / "last-known-good" / "current.json").read_text()
    )

    clock.current = plan.final_at
    result = _tick(plan, runner, clock)

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    status = json.loads(result.status_path.read_text())
    assert status["operator_status"] == "FINAL_FRESH"
    assert status["provenance"] == "FINAL_FRESH"
    after = json.loads(
        (plan.output_dir / "last-known-good" / "current.json").read_text()
    )
    assert after["checkpoint_id"] != before["checkpoint_id"]
    operator = _operator_payload(plan)
    assert operator["operator_status"] == "FINAL_FRESH"
    _upload_lines(Path(operator["coupon_path"]), stake=30, expected_count=166)
    assert not tuple(plan.output_dir.rglob(".bet-ready"))


def test_late_completed_final_preserves_last_known_good(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.preflight_at)

    assert _tick(plan, lambda _context: _candidate(), clock) is None
    original = _load_last_known_good(plan)

    clock.current = plan.final_at

    def late_final(_context):
        clock.current = plan.actionable_publication_deadline + timedelta(seconds=1)
        return _candidate()

    result = _tick(plan, late_final, clock)

    assert result is not None
    assert result.package_path == original.path
    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["operator_status"] == "LAST_KNOWN_GOOD_DEGRADED"
    assert _operator_payload(plan)["coupon_path"] == str(original.path)


def test_candidate_cannot_initialize_its_own_drawing_authority(tmp_path: Path):
    import pytest

    plan = _plan(tmp_path, freeze_authority=False)
    clock = _Clock(plan.preflight_at)

    with pytest.raises(SchedulerIntegrityError):
        _tick(plan, lambda _context: _candidate(), clock)


def test_candidate_must_match_independent_drawing_authority(tmp_path: Path):
    import pytest

    plan = _plan(tmp_path)
    clock = _Clock(plan.preflight_at)

    with pytest.raises(SchedulerIntegrityError):
        _tick(
            plan,
            lambda _context: _candidate(drawing_fingerprint="f" * 64),
            clock,
        )


def test_lkg_rejects_tampered_upload(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = _Clock(plan.preflight_at)
    assert _tick(plan, lambda _context: _candidate(), clock) is None
    package = _load_last_known_good(plan)
    package.path.write_text("30; " + "; ".join(["1"] * 15) + "\n", encoding="utf-8")

    with __import__("pytest").raises(SchedulerIntegrityError):
        _load_last_known_good(plan)


def test_lkg_operator_package_respects_dynamic_bank(tmp_path: Path):
    plan = _plan(tmp_path, bank=9960)
    clock = _Clock(plan.preflight_at)

    assert _tick(plan, lambda _context: _candidate(bank=9960), clock) is None

    operator = _operator_payload(plan)
    assert operator["stake"] == 30
    assert operator["requested_bank"] == 9960
    assert operator["effective_bank"] == 9960
    assert operator["selected_count"] == 332
    assert operator["selected_cost"] == 9960
    _upload_lines(Path(operator["coupon_path"]), stake=30, expected_count=332)


def test_lkg_rejects_stale_source_foreign_fingerprint_and_budget_mismatch(
    tmp_path: Path,
):
    import pytest

    for case in ("stale", "fingerprint", "budget"):
        case_root = tmp_path / case
        case_root.mkdir()
        plan = _plan(case_root)
        clock = _Clock(plan.preflight_at)
        assert _tick(plan, lambda _context: _candidate(), clock) is None

        def mutate(manifest, *, case=case, plan=plan):
            if case == "stale":
                manifest["source_captured_at"] = (
                    (plan.preflight_at - timedelta(seconds=1))
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            elif case == "fingerprint":
                manifest["drawing_fingerprint"] = "f" * 64
            else:
                manifest["effective_bank"] = 4950

        _rewrite_checkpoint(plan, mutate)
        with pytest.raises(SchedulerIntegrityError):
            _load_last_known_good(plan)
