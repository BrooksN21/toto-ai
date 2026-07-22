from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from toto_ai.analytics.api_inspector import DrawingReference
from toto_ai.api.client import TotoBriefClient
from toto_ai.collector.sync import Collector, DetailSyncResult, SummaryPageResult


@dataclass(frozen=True)
class OpenDrawingSyncResult:
    reference: DrawingReference
    summary_page: SummaryPageResult
    detail: DetailSyncResult

    @property
    def ready(self) -> bool:
        return self.detail.status == "synchronized" and self.detail.payload is not None


def synchronize_open_drawing(
    client: TotoBriefClient,
    session_factory: sessionmaker[Session],
    *,
    now: datetime,
    community: str = "baltbet-main",
    expected_drawing_number: int | None = None,
    raw_cache_dir: str | Path = "data/raw",
    detail_cache_max_age_seconds: float = 12 * 60 * 60,
    storage_root: str | Path = ".",
) -> OpenDrawingSyncResult:
    """Perform the minimum TotoBrief morning synchronization.

    Exactly one page-list request is made. All page metadata is committed, the
    exact open drawing is selected only from that fresh response, and its
    detail is loaded from a fresh validated cache when available or fetched
    once otherwise.
    """
    collector = Collector(
        client,
        session_factory,
        raw_cache_dir=raw_cache_dir,
        detail_cache_max_age_seconds=detail_cache_max_age_seconds,
        storage_root=storage_root,
        now=lambda: now,
    )
    summary_page = collector.sync_summary_page(name=community, page=1)
    reference, summary = _select_open_from_page(
        summary_page.drawings,
        now=now,
        community=community,
    )
    if expected_drawing_number is not None:
        if type(expected_drawing_number) is not int or expected_drawing_number <= 0:
            raise ValueError("expected_drawing_number must be a positive integer")
        if reference.number != expected_drawing_number:
            selected = "none" if reference.number is None else str(reference.number)
            raise ValueError(
                f"expected drawing {expected_drawing_number}, selected {selected} "
                "from fresh API page one"
            )
    detail = collector.sync_drawing_detail(
        reference.drawing_id,
        drawing_summary=summary,
        prefer_cache=True,
        force=True,
        strict_summary=True,
    )
    return OpenDrawingSyncResult(
        reference=reference,
        summary_page=summary_page,
        detail=detail,
    )


def _select_open_from_page(
    drawings: tuple[dict[str, object], ...],
    *,
    now: datetime,
    community: str,
) -> tuple[DrawingReference, dict[str, object]]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("open drawing selection time must be timezone-aware")
    current = now.astimezone(timezone.utc)
    candidates: list[tuple[datetime, int, dict[str, object]]] = []
    for row in drawings:
        if row.get("status") not in {"active", "expected"}:
            continue
        drawing_id = row.get("id")
        if type(drawing_id) is not int:
            raise ValueError("playable page-one drawing id must be an integer")
        deadline = _parse_deadline(row.get("ended_at"))
        if deadline <= current:
            continue
        candidates.append((deadline, drawing_id, row))
    if not candidates:
        raise ValueError(
            f"No playable {community} drawing was found on fresh API page one"
        )
    deadline, drawing_id, selected = min(candidates, key=lambda item: item[:2])
    number = selected.get("number")
    if number is not None and type(number) is not int:
        raise ValueError("playable page-one drawing number must be an integer or null")
    status = selected.get("status")
    return (
        DrawingReference(
            drawing_id=drawing_id,
            number=number,
            community=community,
            status=str(status),
            ended_at=deadline.isoformat(),
        ),
        selected,
    )


def _parse_deadline(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("playable page-one drawing deadline is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("playable page-one drawing deadline is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("playable page-one drawing deadline must be timezone-aware")
    return parsed.astimezone(timezone.utc)
