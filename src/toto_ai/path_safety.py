"""Filesystem guards for deterministic report publication."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


def validate_output_paths(
    output_paths: Iterable[str | Path],
    *,
    protected_paths: Iterable[str | Path] = (),
    protected_roots: Iterable[str | Path] = (),
) -> tuple[Path, ...]:
    """Reject lexical and symlink-resolved output collisions."""
    outputs = _paths(output_paths, "output paths")
    if not outputs:
        raise ValueError("output paths must not be empty")
    protected = _paths(protected_paths, "protected paths")
    roots = _paths(protected_roots, "protected roots")

    output_lexical = tuple(_lexical(path) for path in outputs)
    output_resolved = tuple(path.resolve(strict=False) for path in outputs)
    if len(set(output_lexical)) != len(outputs):
        raise ValueError("output paths must be lexically distinct")
    if len(set(output_resolved)) != len(outputs):
        raise ValueError("output paths must be symlink-distinct")

    protected_lexical = {_lexical(path) for path in protected}
    protected_resolved = {path.resolve(strict=False) for path in protected}
    root_lexical = tuple(_lexical(path) for path in roots)
    root_resolved = tuple(path.resolve(strict=False) for path in roots)

    for output, lexical, resolved in zip(
        outputs,
        output_lexical,
        output_resolved,
        strict=True,
    ):
        if output.exists() and output.is_dir():
            raise ValueError("an output path is an existing directory")
        if lexical in protected_lexical or resolved in protected_resolved:
            raise ValueError("output paths must not collide with protected inputs")
        if any(_within(lexical, root) for root in root_lexical) or any(
            _within(resolved, root) for root in root_resolved
        ):
            raise ValueError("output paths must not be inside protected roots")
    return outputs


def probe_writable_directory(path: str | Path) -> Path:
    """Verify that a directory can create and remove a private file."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise OSError(f"not a directory: {directory}")
    descriptor, name = tempfile.mkstemp(prefix=".toto-write-probe-", dir=directory)
    os.close(descriptor)
    Path(name).unlink()
    return directory


@dataclass(frozen=True)
class _ArtifactSnapshot:
    path: Path
    existed: bool
    backup: Path | None


class ArtifactPublicationTransaction:
    """Restore every candidate artifact if publication raises BaseException."""

    def __init__(self, output_paths: Iterable[str | Path]) -> None:
        self._paths = _paths(output_paths, "output paths")
        self._snapshots: tuple[_ArtifactSnapshot, ...] = ()
        self._entered = False
        self._committed = False

    def __enter__(self) -> ArtifactPublicationTransaction:
        token = secrets.token_hex(16)
        snapshots = []
        try:
            for path in self._paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                existed = path.exists() or path.is_symlink()
                backup = None
                if existed:
                    if path.is_dir():
                        raise ValueError("artifact path must not be a directory")
                    backup = path.with_name(f".{path.name}.{token}.txn.bak.tmp")
                snapshots.append(_ArtifactSnapshot(path, existed, backup))
                if backup is not None:
                    with path.open("rb") as source, backup.open("xb") as target:
                        shutil.copyfileobj(source, target)
        except BaseException:
            for snapshot in snapshots:
                if snapshot.backup is not None:
                    snapshot.backup.unlink(missing_ok=True)
            raise
        self._snapshots = tuple(snapshots)
        self._entered = True
        return self

    @property
    def committed(self) -> bool:
        return self._committed

    def commit(self) -> None:
        if not self._entered:
            raise RuntimeError("publication transaction has not started")
        self._committed = True
        self._cleanup_backups()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if self._committed:
            self._cleanup_backups()
            return False
        if exc_type is None:
            self._rollback()
            raise RuntimeError("publication transaction exited without commit")
        self._rollback()
        return False

    def _rollback(self) -> None:
        for snapshot in self._snapshots:
            try:
                if snapshot.existed:
                    assert snapshot.backup is not None
                    os.replace(snapshot.backup, snapshot.path)
                else:
                    snapshot.path.unlink(missing_ok=True)
            except BaseException:
                # Preserve the publication exception; cleanup is best effort.
                pass
        self._cleanup_backups()

    def _cleanup_backups(self) -> None:
        for snapshot in self._snapshots:
            if snapshot.backup is None:
                continue
            try:
                snapshot.backup.unlink(missing_ok=True)
            except BaseException:
                # Once committed, an interrupted cleanup is still success.
                pass


def _paths(values: Iterable[str | Path], label: str) -> tuple[Path, ...]:
    try:
        return tuple(Path(value) for value in values)
    except TypeError as error:
        raise ValueError(f"{label} must contain filesystem paths") from error


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
