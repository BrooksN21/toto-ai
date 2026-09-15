"""Independent idempotent-ack fsync failure probe; no live inputs."""

import pytest

from toto_ai.sports_stats import goal_probe_collection as candidate


def test_existing_record_sync_error_propagates_without_overwrite(monkeypatch, tmp_path):
    root = tmp_path / "output"
    path = root / "attempts/000001/outcome.json"
    content = b'{"synthetic":true}\n'
    candidate._publish_retry_record(path, content, durable_root=root)
    observed = []

    def fail_sync(fd):
        observed.append(fd)
        raise OSError("independent same-record directory failure")

    monkeypatch.setattr(candidate.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="same-record directory failure"):
        candidate._publish_retry_record(path, content, durable_root=root)
    assert len(observed) == 1
    assert path.read_bytes() == content
