"""Crash-publication review probes; only synthetic temporary files."""

from pathlib import Path

import cache_review_fixture as fixture
import pytest

from toto_ai.sports_stats import goal_probe_collection as candidate


@pytest.mark.parametrize("interrupted_file", ["attempt.json", "outcome.json"])
def test_interrupted_metadata_publication_can_recover(
    monkeypatch, tmp_path, interrupted_file,
):
    output = fixture._cache_fixture(tmp_path)
    fixture._cache_refresh_stub(monkeypatch, tmp_path, mode="exception")
    real_open = Path.open
    interrupted = False

    def crash_open(path, mode="r", *args, **kwargs):
        nonlocal interrupted
        stream = real_open(path, mode, *args, **kwargs)
        if not interrupted and path.name == interrupted_file and mode in {"xb", "wb"}:
            interrupted = True
            stream.close()
            raise KeyboardInterrupt("crash after create before write")
        return stream

    with monkeypatch.context() as crash:
        crash.setattr(Path, "open", crash_open)
        with pytest.raises(KeyboardInterrupt):
            fixture._ensure_cached(tmp_path, output, 15, request_budget=3)
    assert interrupted
    calls = fixture._cache_refresh_stub(monkeypatch, tmp_path)
    result = fixture._ensure_cached(tmp_path, output, 45, request_budget=3)
    assert len(calls) == 1 and not result.reused
    status = candidate.goal_probe_failure_status(ValueError("integrity"))
    assert status["retryable"] is False
