"""Independent review of exact reconstructed candidate, not applied main code."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import cache_review_fixture as fixture
import pytest

from toto_ai.sports_stats import goal_probe_collection as candidate

BASE = datetime(2026, 8, 27, 8, tzinfo=timezone.utc)


def ensure(root, output, seconds):
    return candidate.ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=root / "data/raw",
        output_root=output,
        api_key="synthetic-review-key",
        request_budget=3,
        project_root=root,
        captured_at=BASE + timedelta(seconds=seconds),
    )


@pytest.mark.parametrize("mode", ["source_failed", "exception"])
def test_recovered_provider_can_retry_after_later_cooldown(monkeypatch, tmp_path, mode):
    """Required unattended recovery; fails on the submitted permanent claim."""
    output = fixture._cache_fixture(tmp_path)
    first_calls = fixture._cache_refresh_stub(monkeypatch, tmp_path, mode=mode)
    with pytest.raises(ValueError):
        ensure(tmp_path, output, 900)
    assert len(first_calls) == 1
    recovered_calls = fixture._cache_refresh_stub(monkeypatch, tmp_path)
    recovered = ensure(tmp_path, output, 3600)
    assert len(recovered_calls) == 1
    assert recovered.captured_at == BASE + timedelta(seconds=3600)
    assert not recovered.reused


@pytest.mark.parametrize("status,eligible", [
    ("collected", 0), ("collected", 10), ("collected", 15), ("partial_conflicts", 10),
])
def test_valid_cache_is_reused_without_relabeling_time(
    monkeypatch, tmp_path, status, eligible,
):
    output = fixture._cache_fixture(tmp_path, failed=False, eligible=eligible)
    marker_path = output / "current.json"
    marker = json.loads(marker_path.read_text())
    report_path = tmp_path / marker["schedule_report_path"]
    report = json.loads(report_path.read_text())
    report["providers"]["goal-api-v1"]["status"] = status
    report_path.write_text(json.dumps(report))
    marker["schedule_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    marker_path.write_text(json.dumps(marker))
    calls = fixture._cache_refresh_stub(monkeypatch, tmp_path)
    reused = ensure(tmp_path, output, 3600)
    assert reused.reused and reused.captured_at == BASE
    assert reused.sports_eligible_count == eligible and not calls


def test_cooldown_exact_boundary_immutability_and_budget(monkeypatch, tmp_path):
    output = fixture._cache_fixture(tmp_path)
    paths = [
        output / "current.json",
        *list((output / "captures/original").glob("*.json")),
    ]
    original = {path: path.read_bytes() for path in paths}
    calls = fixture._cache_refresh_stub(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="cooldown"):
        ensure(tmp_path, output, 899.999)
    assert not calls
    fresh = ensure(tmp_path, output, 900)
    reused = ensure(tmp_path, output, 3600)
    assert len(calls) == 1 and calls[0]["client"]["request_budget"] == 3
    assert fresh.captured_at == reused.captured_at == BASE + timedelta(seconds=900)
    assert reused.reused and not fresh.reused
    assert all(path.read_bytes() == data for path, data in original.items())


def test_hash_corruption_is_not_retry_permission(monkeypatch, tmp_path):
    output = fixture._cache_fixture(tmp_path)
    calls = fixture._cache_refresh_stub(monkeypatch, tmp_path)
    (output / "captures/original/coverage-summary.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        ensure(tmp_path, output, 3600)
    assert not calls
