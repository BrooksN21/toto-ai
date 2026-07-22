from __future__ import annotations

import os
from pathlib import Path


def resolve_contained_path(
    path: str | Path,
    *,
    allowed_root: str | Path = ".",
) -> Path:
    """Resolve a path below one real, symlink-free operational root."""
    root = Path(allowed_root).absolute()
    _reject_symlink_chain(root)
    if not root.is_dir():
        raise ValueError(f"operational root is not a directory: {root}")
    root_resolved = root.resolve(strict=True)

    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        candidate.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError("operational path escapes the allowed root") from error
    _reject_symlink_chain(candidate, stop_at=root_resolved)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(
            "operational path resolves outside the allowed root"
        ) from error
    return resolved


def prepare_contained_parent(
    path: str | Path,
    *,
    allowed_root: str | Path = ".",
) -> Path:
    resolved = resolve_contained_path(path, allowed_root=allowed_root)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolve_contained_path(resolved, allowed_root=allowed_root)


def fsync_directory(path: str | Path) -> None:
    descriptor = os.open(Path(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_symlink_chain(path: Path, *, stop_at: Path | None = None) -> None:
    cursor = path
    chain: list[Path] = []
    while True:
        chain.append(cursor)
        if stop_at is not None and cursor == stop_at:
            break
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for component in reversed(chain):
        if component.is_symlink():
            raise ValueError(f"symlink path component is not allowed: {component}")
