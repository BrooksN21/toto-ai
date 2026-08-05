from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from toto_ai.analytics.api_inspector import DrawingReference
from toto_ai.api.client import TotoBriefClient
from toto_ai.collector.sync import Collector, DetailSyncResult, SummaryPageResult

DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS = 60.0


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
    detail_cache_max_age_seconds: float = (
        DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS
    ),
    storage_root: str | Path = ".",
) -> OpenDrawingSyncResult:
    """Perform the minimum TotoBrief morning synchronization.

    Exactly one page-list request is made. All page metadata is committed, the
    exact open drawing is selected only from that fresh response, and its
    detail is loaded only from an operationally fresh validated cache when
    available or fetched once otherwise. The short preparation cache window
    prevents a long-lived raw cache from becoming the probability evidence
    later compared with the runner's fresh drawing snapshot.
    """
    if (
        not isinstance(detail_cache_max_age_seconds, int | float)
        or isinstance(detail_cache_max_age_seconds, bool)
        or detail_cache_max_age_seconds < 0
        or detail_cache_max_age_seconds
        > DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS
    ):
        raise ValueError(
            "detail_cache_max_age_seconds for active preparation must be between "
            f"0 and {DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS:g}"
        )
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


def synchronize_drawing_payload(
    payload: Mapping[str, object],
    *,
    fetched_at: datetime,
    session_factory: sessionmaker[Session],
    expected_drawing_id: int,
    expected_drawing_number: int,
) -> DetailSyncResult:
    """Persist one already captured exact detail without any API request."""
    parsed_at = fetched_at.astimezone(timezone.utc)
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("captured payload fetched_at must be timezone-aware")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("captured drawing payload data must be a mapping")
    if (
        data.get("id") != expected_drawing_id
        or data.get("number") != expected_drawing_number
    ):
        raise ValueError("captured drawing payload identity mismatch")
    deadline = _parse_deadline(data.get("ended_at"))
    if parsed_at > deadline:
        raise ValueError("captured drawing payload is after the deadline")
    collector = Collector(
        TotoBriefClient(), session_factory, now=lambda: parsed_at
    )
    return collector.synchronize_payload(
        dict(payload),
        drawing_summary={
            "id": expected_drawing_id,
            "number": expected_drawing_number,
            "ended_at": deadline.isoformat(),
            "status": data.get("status"),
        },
        source="atomic-final",
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
    nearest_deadline = min(item[0] for item in candidates)
    nearest = tuple(
        item for item in candidates if item[0] == nearest_deadline
    )
    if len(nearest) != 1:
        identities = ",".join(
            str(item[1]) for item in sorted(nearest, key=lambda item: item[1])
        )
        raise ValueError(
            "ambiguous nearest playable drawings on fresh API page one: "
            f"{identities}"
        )
    deadline, drawing_id, selected = nearest[0]
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
