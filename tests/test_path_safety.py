from pathlib import Path

import pytest

import toto_ai.path_safety as path_safety
from toto_ai.path_safety import (
    ArtifactPublicationTransaction,
    probe_writable_directory,
    validate_output_paths,
)


def test_output_paths_reject_lexical_aliases_of_each_other(tmp_path: Path) -> None:
    first = tmp_path / "reports" / "artifact.json"
    lexical_alias = tmp_path / "reports" / "nested" / ".." / "artifact.json"

    with pytest.raises(ValueError, match="lexically distinct"):
        validate_output_paths((first, lexical_alias))


def test_output_paths_reject_symlink_aliases_of_each_other(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"existing artifact")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.symlink_to(target)
    second.symlink_to(target)

    with pytest.raises(ValueError, match="symlink-distinct"):
        validate_output_paths((first, second))

    assert target.read_bytes() == b"existing artifact"
    assert first.is_symlink()
    assert second.is_symlink()


def test_output_paths_reject_lexical_and_resolved_cache_descendants(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    report_alias = tmp_path / "reports"
    report_alias.symlink_to(cache_root, target_is_directory=True)

    with pytest.raises(ValueError, match="protected roots"):
        validate_output_paths(
            (report_alias / "artifact.json",),
            protected_roots=(cache_root,),
        )


def test_writability_probe_does_not_replace_existing_file(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"protected")

    with pytest.raises(OSError):
        probe_writable_directory(blocked)

    assert blocked.read_bytes() == b"protected"


def test_transaction_entry_cleans_partial_backup_on_base_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"original")

    def interrupt_backup(_source, target):
        target.write(b"partial")
        raise KeyboardInterrupt("backup interrupted")

    monkeypatch.setattr(path_safety.shutil, "copyfileobj", interrupt_backup)

    with pytest.raises(KeyboardInterrupt, match="backup interrupted"):
        with ArtifactPublicationTransaction((artifact,)):
            pytest.fail("publication body must not start")

    assert artifact.read_bytes() == b"original"
    assert tuple(tmp_path.glob(".*.txn.bak.tmp")) == ()
