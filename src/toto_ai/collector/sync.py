from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.api.client import TotoBriefClient
from toto_ai.api.detail_cache import (
    DEFAULT_DETAIL_CACHE_MAX_AGE_SECONDS,
    DrawingDetailCacheRecord,
    is_zero_pool_bootstrap_payload,
    load_drawing_detail_cache,
    validate_drawing_detail_payload,
    write_drawing_detail_cache,
)
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.collector.lifecycle import (
    RawArchive,
    finished_drawing_is_current,
    import_archived_detail,
    validate_full_detail_payload,
)
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.totobrief_time import parse_totobrief_timestamp


@dataclass(frozen=True)
class DetailSyncResult:
    drawing_id: int
    status: str
    source: str | None = None
    cache_age_seconds: float | None = None
    events_saved: int = 0
    quotes_saved: int = 0
    error: str | None = None
    payload: dict[str, Any] | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class SummaryPageResult:
    page: int
    drawings: tuple[dict[str, Any], ...]
    inserted: int
    updated: int


@dataclass(frozen=True)
class SyncResult:
    pages_fetched: int = 0
    drawings_seen: int = 0
    drawings_saved: int = 0
    drawings_updated: int = 0
    events_saved: int = 0
    quotes_saved: int = 0
    details_deferred: int = 0
    detail_results: tuple[DetailSyncResult, ...] = ()


class Collector:
    """Resumable TotoBrief drawing synchronization.

    Page-list metadata is committed before any detail request. Detail writes
    are idempotent upserts, and a fresh validated raw cache can recover a
    missing detail without another network request.
    """

    def __init__(
        self,
        client: TotoBriefClient,
        session_factory: sessionmaker[Session],
        *,
        raw_cache_dir: str | Path | None = None,
        detail_cache_max_age_seconds: float = (
            DEFAULT_DETAIL_CACHE_MAX_AGE_SECONDS
        ),
        storage_root: str | Path = ".",
        raw_archive_dir: str | Path | None = None,
        now: Any | None = None,
    ) -> None:
        self.client = client
        self.session_factory = session_factory
        self.raw_cache_dir = (
            Path(raw_cache_dir) if raw_cache_dir is not None else None
        )
        self.detail_cache_max_age_seconds = detail_cache_max_age_seconds
        self.storage_root = Path(storage_root)
        self.raw_archive_dir = (
            Path(raw_archive_dir)
            if raw_archive_dir is not None
            else (
                Path(raw_cache_dir) / "archive"
                if raw_cache_dir is not None
                else None
            )
        )
        self.now = now or (lambda: datetime.now(timezone.utc))

    def sync(
        self,
        name: str = "baltbet-main",
        progress: Any | None = None,
        *,
        max_pages: int | None = None,
    ) -> SyncResult:
        pages_fetched = 0
        drawings_seen = 0
        drawings_saved = 0
        drawings_updated = 0
        events_saved = 0
        quotes_saved = 0
        details_deferred = 0
        detail_results: list[DetailSyncResult] = []
        page = 1
        task_id = None

        if max_pages is not None and (type(max_pages) is not int or max_pages < 1):
            raise ValueError("max_pages must be a positive integer or None")
        if progress is not None:
            task_id = progress.add_task("Collecting drawings", total=max_pages)

        while max_pages is None or page <= max_pages:
            page_result = self.sync_summary_page(name=name, page=page)
            pages_fetched += 1
            drawings = page_result.drawings
            drawings_updated += page_result.updated

            if not drawings:
                break

            drawings_seen += len(drawings)
            for drawing_summary in drawings:
                drawing_id = drawing_summary["id"]
                if progress is not None and task_id is not None:
                    progress.update(
                        task_id,
                        description=f"Synchronizing drawing {drawing_id}",
                    )
                if not self.drawing_needs_detail(drawing_id):
                    continue
                detail = self.sync_drawing_detail(
                    drawing_id,
                    drawing_summary=drawing_summary,
                    prefer_cache=True,
                )
                detail_results.append(detail)
                if detail.status == "deferred":
                    details_deferred += 1
                    continue
                drawings_saved += 1
                events_saved += detail.events_saved
                quotes_saved += detail.quotes_saved

            if progress is not None and task_id is not None:
                progress.advance(task_id)
            page += 1

        if progress is not None and task_id is not None:
            progress.update(
                task_id,
                description="Collection complete",
                completed=pages_fetched,
            )

        return SyncResult(
            pages_fetched=pages_fetched,
            drawings_seen=drawings_seen,
            drawings_saved=drawings_saved,
            drawings_updated=drawings_updated,
            events_saved=events_saved,
            quotes_saved=quotes_saved,
            details_deferred=details_deferred,
            detail_results=tuple(detail_results),
        )

    def sync_summary_page(
        self,
        *,
        name: str = "baltbet-main",
        page: int = 1,
    ) -> SummaryPageResult:
        payload = self.client.drawings(name=name, page=page)
        raw_drawings = payload.get("data", [])
        if not isinstance(raw_drawings, list):
            raise ValueError("TotoBrief drawings payload data must be a list")
        drawings: list[dict[str, Any]] = []
        for raw in raw_drawings:
            if not isinstance(raw, dict) or type(raw.get("id")) is not int:
                raise ValueError("TotoBrief drawing summary is malformed")
            drawings.append(raw)
        inserted, updated = self._upsert_drawing_summaries(drawings, name=name)
        return SummaryPageResult(
            page=page,
            drawings=tuple(drawings),
            inserted=inserted,
            updated=updated,
        )

    def sync_drawing_detail(
        self,
        drawing_id: int,
        *,
        drawing_summary: dict[str, Any] | None = None,
        prefer_cache: bool = False,
        force: bool = False,
        strict_summary: bool = False,
    ) -> DetailSyncResult:
        if type(drawing_id) is not int or drawing_id <= 0:
            raise ValueError("drawing_id must be a positive integer")
        if not force and not self.drawing_needs_detail(drawing_id):
            return DetailSyncResult(drawing_id, "current", source="sqlite")

        cache_error: str | None = None
        if prefer_cache:
            cached, cache_error = self._load_cache(drawing_id)
            if cached is not None:
                try:
                    _validate_detail_matches_summary(
                        cached.payload,
                        drawing_summary,
                        strict=strict_summary,
                        now=self.now(),
                    )
                    _validate_cache_lifecycle(
                        cached.payload,
                        drawing_summary,
                    )
                except ValueError as error:
                    cache_error = _safe_error(error)
                else:
                    return self._persist_detail(
                        cached.payload,
                        drawing_summary=drawing_summary,
                        source=f"cache:{cached.source}",
                        cache_age_seconds=cached.age_seconds,
                    )

        try:
            payload = self.client.drawing_info(drawing_id)
            if _summary_or_payload_is_finished(payload, drawing_summary):
                validate_full_detail_payload(
                    payload,
                    expected_drawing_id=drawing_id,
                )
            else:
                try:
                    validate_drawing_detail_payload(
                        payload,
                        expected_drawing_id=drawing_id,
                    )
                except ValueError:
                    if not is_zero_pool_bootstrap_payload(
                        payload,
                        expected_drawing_id=drawing_id,
                    ):
                        raise
                    _validate_detail_matches_summary(
                        payload,
                        drawing_summary,
                        strict=strict_summary,
                        now=self.now(),
                    )
                    return DetailSyncResult(
                        drawing_id=drawing_id,
                        status="deferred",
                        source="network-not-ready",
                        error="TotoBrief pool probabilities are not ready",
                        payload=payload,
                        reason_code="totobrief_pool_not_ready",
                    )
            _validate_detail_matches_summary(
                payload,
                drawing_summary,
                strict=strict_summary,
                now=self.now(),
            )
            if self.raw_cache_dir is not None:
                try:
                    write_drawing_detail_cache(
                        payload,
                        drawing_id=drawing_id,
                        cache_dir=self.raw_cache_dir,
                        fetched_at=self.now(),
                        source="collector-network",
                        allowed_root=self.storage_root,
                    )
                except ValueError:
                    # The operational cache requires useful pool/BK triples.
                    # Incomplete finished payloads are still preserved in the
                    # append-only archive and reconciled later.
                    pass
        except (
            KeyError,
            OSError,
            TotoBriefRequestError,
            TypeError,
            ValueError,
            requests.RequestException,
        ) as error:
            network_error = _safe_error(error)
        else:
            return self._persist_detail(
                payload,
                drawing_summary=drawing_summary,
                source="network",
            )

        if not prefer_cache:
            cached, cache_error = self._load_cache(drawing_id)
            if cached is not None:
                try:
                    _validate_detail_matches_summary(
                        cached.payload,
                        drawing_summary,
                        strict=strict_summary,
                        now=self.now(),
                    )
                    _validate_cache_lifecycle(
                        cached.payload,
                        drawing_summary,
                    )
                except ValueError as error:
                    cache_error = _safe_error(error)
                else:
                    return self._persist_detail(
                        cached.payload,
                        drawing_summary=drawing_summary,
                        source=f"cache:{cached.source}",
                        cache_age_seconds=cached.age_seconds,
                    )

        reasons = [f"network={network_error}"]
        if cache_error is not None:
            reasons.append(f"cache={cache_error}")
        elif self.raw_cache_dir is None:
            reasons.append("cache=disabled")
        return DetailSyncResult(
            drawing_id=drawing_id,
            status="deferred",
            error="; ".join(reasons),
        )

    def drawing_needs_detail(self, drawing_id: int) -> bool:
        with self.session_factory() as session:
            drawing = session.get(Drawing, drawing_id)
            if drawing is None:
                return True
            if drawing.status == "finished":
                return not finished_drawing_is_current(session, drawing_id)
            event_orders = session.scalars(
                select(Event.event_order).where(Event.drawing_id == drawing_id)
            ).all()
            if len(event_orders) != 15 or set(event_orders) != set(range(15)):
                return True
            quote_rows = session.execute(
                select(
                    Quote.event_order,
                    Quote.pool_win_1,
                    Quote.pool_draw,
                    Quote.pool_win_2,
                    Quote.bk_win_1,
                    Quote.bk_draw,
                    Quote.bk_win_2,
                ).where(Quote.drawing_id == drawing_id)
            ).all()
            if len(quote_rows) != 15 or {
                row.event_order for row in quote_rows
            } != set(range(15)):
                return True
            return any(
                not _stored_quote_row_is_complete(row)
                for row in quote_rows
            )

    def synchronize_payload(
        self,
        payload: dict[str, Any],
        *,
        drawing_summary: dict[str, Any],
        source: str,
    ) -> DetailSyncResult:
        """Persist an already obtained exact detail without transport access."""
        return self._persist_detail(
            payload,
            drawing_summary=drawing_summary,
            source=source,
        )

    def _load_cache(
        self,
        drawing_id: int,
    ) -> tuple[DrawingDetailCacheRecord | None, str | None]:
        if self.raw_cache_dir is None:
            return None, None
        try:
            return (
                load_drawing_detail_cache(
                    drawing_id,
                    cache_dir=self.raw_cache_dir,
                    max_age_seconds=self.detail_cache_max_age_seconds,
                    now=self.now(),
                    allowed_root=self.storage_root,
                ),
                None,
            )
        except (OSError, TypeError, ValueError) as error:
            return None, _safe_error(error)

    def _persist_detail(
        self,
        payload: dict[str, Any],
        *,
        drawing_summary: dict[str, Any] | None,
        source: str,
        cache_age_seconds: float | None = None,
    ) -> DetailSyncResult:
        if _summary_or_payload_is_finished(payload, drawing_summary):
            validate_full_detail_payload(
                payload,
                expected_drawing_id=payload["data"]["id"],
            )
        else:
            validate_drawing_detail_payload(
                payload,
                expected_drawing_id=payload["data"]["id"],
            )
        drawing_id = payload["data"]["id"]
        if self.raw_archive_dir is not None:
            captured_at = self.now()
            archive = RawArchive(self.raw_archive_dir).archive(
                payload,
                captured_at=captured_at,
                source=source,
                lifecycle_status=str(
                    (drawing_summary or {}).get("status")
                    or payload["data"].get("status")
                    or "unknown"
                ),
                source_endpoint=f"/drawing-info/{drawing_id}",
            )
            imported = import_archived_detail(
                self.session_factory,
                archive,
            )
            # The page summary is newer than a cache payload. Apply only
            # monotonic drawing-level fields after the RAW-bound import.
            if drawing_summary:
                self._upsert_drawing_summaries(
                    [drawing_summary],
                    name=str(
                        drawing_summary.get("name")
                        or payload["data"].get("name")
                        or "baltbet-main"
                    ),
                )
            events_saved = imported.events_created
            quotes_saved = imported.quotes_created
        else:
            events_saved, quotes_saved = self._save_drawing(
                drawing_summary=drawing_summary or {"id": drawing_id},
                drawing_info=payload["data"],
            )
        return DetailSyncResult(
            drawing_id=drawing_id,
            status="synchronized",
            source=source,
            cache_age_seconds=cache_age_seconds,
            events_saved=events_saved,
            quotes_saved=quotes_saved,
            payload=payload,
        )

    def _upsert_drawing_summaries(
        self,
        drawings: list[dict[str, Any]],
        *,
        name: str,
    ) -> tuple[int, int]:
        inserted = 0
        updated = 0
        with self.session_factory.begin() as session:
            for summary in drawings:
                drawing_id = summary["id"]
                drawing = session.get(Drawing, drawing_id)
                was_new = drawing is None
                if drawing is None:
                    drawing = Drawing(id=drawing_id)
                    session.add(drawing)
                    inserted += 1
                changed = _apply_drawing_fields(drawing, summary, default_name=name)
                if changed and not was_new:
                    updated += 1
        return inserted, updated

    def _save_drawing(
        self,
        drawing_summary: dict[str, Any],
        drawing_info: dict[str, Any],
    ) -> tuple[int, int]:
        # Page-list metadata was fetched most recently and must not be rolled
        # back by an older but still fresh detail cache (notably status).
        drawing_data = drawing_info | drawing_summary
        events = drawing_info.get("events") or []
        events_saved = 0
        quotes_saved = 0

        with self.session_factory.begin() as session:
            drawing = session.get(Drawing, drawing_data["id"])
            if drawing is None:
                drawing = Drawing(id=drawing_data["id"])
                session.add(drawing)
            _apply_drawing_fields(drawing, drawing_data)

            for event_data in events:
                event_order = event_data.get("order")
                event = session.scalar(
                    select(Event)
                    .where(Event.drawing_id == drawing_data["id"])
                    .where(Event.event_order == event_order)
                )
                if event is None:
                    event = Event(
                        drawing_id=drawing_data["id"],
                        event_order=event_order,
                    )
                    session.add(event)
                    events_saved += 1
                for field in (
                    "name",
                    "championship",
                    "sport",
                    "result",
                    "score",
                ):
                    if field in event_data:
                        setattr(event, field, event_data.get(field))

                quotes = event_data.get("quotes")
                if not quotes:
                    continue
                quote = session.scalar(
                    select(Quote)
                    .where(Quote.drawing_id == drawing_data["id"])
                    .where(Quote.event_order == event_order)
                )
                if quote is None:
                    quote = Quote(
                        drawing_id=drawing_data["id"],
                        event_order=event_order,
                    )
                    session.add(quote)
                    quotes_saved += 1
                for field in (
                    "pool_win_1",
                    "pool_draw",
                    "pool_win_2",
                    "bk_win_1",
                    "bk_draw",
                    "bk_win_2",
                    "pin_win_1",
                    "pin_draw",
                    "pin_win_2",
                    "norm_win_1",
                    "norm_draw",
                    "norm_win_2",
                ):
                    if field in quotes:
                        setattr(quote, field, quotes.get(field))

        return events_saved, quotes_saved

    def saved_drawing_ids(self) -> set[int]:
        with self.session_factory() as session:
            return set(session.scalars(select(Drawing.id)).all())


def _apply_drawing_fields(
    drawing: Drawing,
    data: dict[str, Any],
    *,
    default_name: str | None = None,
) -> bool:
    changed = False
    mapping = {
        "number": "number",
        "name": "name",
        "status": "status",
        "pool_sum": "pool_sum",
        "jackpot": "jackpot",
        "started_at": "started_at",
        "ended_at": "ended_at",
    }
    for source, target in mapping.items():
        if source not in data:
            continue
        value = data.get(source)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if target in {"pool_sum", "jackpot"} and value == 0:
            if getattr(drawing, target) not in (None, 0):
                continue
        if target == "status":
            ranks = {None: 0, "expected": 1, "active": 2, "finished": 3}
            if ranks.get(value, 0) < ranks.get(drawing.status, 0):
                continue
        if getattr(drawing, target) != value:
            setattr(drawing, target, value)
            changed = True
    if drawing.name is None and default_name is not None:
        drawing.name = default_name
        changed = True
    return changed


def _safe_error(error: BaseException) -> str:
    if isinstance(error, requests.RequestException):
        # Raw requests errors can embed full URLs and query strings. Normal
        # TotoBriefClient paths already wrap them, but custom/test clients must
        # not turn collector diagnostics into a secret-bearing fallback.
        return type(error).__name__
    message = str(error).strip()
    if not message:
        message = type(error).__name__
    return message[:500]


def _stored_quote_row_is_complete(row: Any) -> bool:
    values = tuple(row)[1:]
    if any(
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
        for value in values
    ):
        return False
    return sum(float(value) for value in values[:3]) > 0 and sum(
        float(value) for value in values[3:]
    ) > 0


def _summary_or_payload_is_finished(
    payload: dict[str, Any],
    drawing_summary: dict[str, Any] | None,
) -> bool:
    return (
        (drawing_summary or {}).get("status") == "finished"
        or payload.get("data", {}).get("status") == "finished"
    )


def _validate_cache_lifecycle(
    payload: dict[str, Any],
    drawing_summary: dict[str, Any] | None,
) -> None:
    if (
        drawing_summary is not None
        and drawing_summary.get("status") == "finished"
        and payload.get("data", {}).get("status") != "finished"
    ):
        raise ValueError(
            "active/expected detail cache cannot satisfy a finished drawing"
        )


def _validate_detail_matches_summary(
    payload: dict[str, Any],
    drawing_summary: dict[str, Any] | None,
    *,
    strict: bool = False,
    now: datetime | None = None,
) -> None:
    if drawing_summary is None:
        return
    data = payload["data"]
    if data.get("id") != drawing_summary.get("id"):
        raise ValueError("drawing detail id does not match page summary")
    expected_number = drawing_summary.get("number")
    if (
        strict or expected_number is not None
    ) and data.get("number") != expected_number:
        raise ValueError("drawing detail number does not match page summary")
    expected_deadline = drawing_summary.get("ended_at")
    if expected_deadline is not None:
        community = str(
            data.get("name") or drawing_summary.get("name") or ""
        ).strip() or None
        if _parse_aware_datetime(
            data.get("ended_at"), community=community
        ) != _parse_aware_datetime(expected_deadline, community=community):
            raise ValueError("drawing detail ended_at does not match page summary")
    if strict:
        expected_status = drawing_summary.get("status")
        if expected_status not in {"active", "expected"}:
            raise ValueError("page summary status is not playable")
        if data.get("status") != expected_status:
            raise ValueError("drawing detail status does not match page summary")
        current = now or datetime.now(timezone.utc)
        deadline = _parse_aware_datetime(
            data.get("ended_at"),
            community=str(data.get("name") or "").strip() or None,
        )
        if deadline <= current.astimezone(timezone.utc):
            raise ValueError("drawing detail deadline is not in the future")


def _parse_aware_datetime(
    value: Any,
    *,
    community: str | None = None,
) -> datetime:
    try:
        return parse_totobrief_timestamp(
            value,
            community=community,
            field_name="drawing detail deadline",
        )
    except ValueError as error:
        raise ValueError(
            "drawing detail deadline must be a timezone-aware timestamp"
        ) from error
