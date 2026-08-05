from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.analytics.api_inspector import resolve_drawing_reference
from toto_ai.api.client import TotoBriefClient
from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.drawing import resolve_open_drawing_from_api
from toto_ai.external_odds.api_sports import APISportsClient
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import load_ready_drawing_pins
from toto_ai.sports_stats.api_sports import APISportsFootballStatsProvider
from toto_ai.sports_stats.collection import collect_sports_stats
from toto_ai.sports_stats.domain import SportsStatsRunSnapshot
from toto_ai.sports_stats.reports import write_sports_stats_reports
from toto_ai.sports_stats.storage import save_sports_stats_snapshot


def collect_and_store_sports_stats(
    *,
    db: str,
    open_drawing: bool,
    drawing_id: int | None,
    drawing_number: int | None,
    history_size: int,
    report_dir: str,
    cache_root: str,
    raw_cache_dir: str,
    env_file: str,
    historical_as_of: datetime | None,
    now: datetime | None = None,
    totobrief_client: TotoBriefClient | None = None,
    provider_client: APISportsClient | None = None,
) -> tuple[SportsStatsRunSnapshot, tuple[Path, Path, Path]]:
    selectors = sum(
        (open_drawing, drawing_id is not None, drawing_number is not None)
    )
    if selectors != 1:
        raise ValueError(
            "choose exactly one of --open, --drawing-id, or --drawing-number"
        )
    if open_drawing and historical_as_of is not None:
        raise ValueError("--open cannot be combined with --historical-as-of")
    observed_at = now or datetime.now(timezone.utc)
    _utc("now", observed_at)
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    if open_drawing:
        client = totobrief_client or TotoBriefClient()
        reference = resolve_open_drawing_from_api(client, now=observed_at)
        payload = client.drawing_info(reference.drawing_id)
        target_fetched_at = observed_at
    else:
        with session_factory() as session:
            reference = resolve_drawing_reference(
                session,
                drawing_id=drawing_id,
                number=drawing_number,
            )
        if historical_as_of is None:
            client = totobrief_client or TotoBriefClient()
            payload = client.drawing_info(reference.drawing_id)
            target_fetched_at = observed_at
        else:
            raw_root = Path(raw_cache_dir).resolve()
            if not raw_root.is_dir():
                raise ValueError(
                    f"drawing detail cache is missing: {raw_root}"
                )
            record = load_drawing_detail_cache(
                reference.drawing_id,
                cache_dir=raw_root,
                max_age_seconds=None,
                now=historical_as_of,
                allowed_root=raw_root,
            )
            if record.fetched_at > historical_as_of:
                raise ValueError(
                    "historical drawing detail evidence was captured after as-of"
                )
            payload = record.payload
            target_fetched_at = record.fetched_at
    target = parse_target_drawing(payload, fetched_at=target_fetched_at)
    if target.drawing_id != reference.drawing_id:
        raise ValueError("TotoBrief drawing identity changed")
    if (
        reference.number is not None
        and target.drawing_number is not None
        and target.drawing_number != reference.number
    ):
        raise ValueError("TotoBrief drawing number changed")
    if historical_as_of is None and observed_at >= target.deadline:
        raise ValueError("prospective collection is after the drawing deadline")
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    pins = load_ready_drawing_pins(
        session_factory,
        drawing_id=target.drawing_id,
        drawing_fingerprint=fingerprint,
        provider="api-sports",
    )
    if provider_client is None:
        api_key = load_api_sports_key(env_file)
        provider_client = APISportsClient(
            api_key,
            cache_dir=Path(cache_root),
            stop_at=target.deadline if historical_as_of is None else None,
        )
    provider = APISportsFootballStatsProvider(provider_client)

    def clock() -> datetime:
        return datetime.now(timezone.utc) if now is None else observed_at

    snapshot = collect_sports_stats(
        target,
        pins,
        provider,
        history_size=history_size,
        now=clock,
        historical_as_of=historical_as_of,
    )
    snapshot = save_sports_stats_snapshot(session_factory, snapshot)
    paths = write_sports_stats_reports(snapshot, report_dir=report_dir)
    return snapshot, paths


def load_api_sports_key(env_file: str | Path = ".env") -> str:
    environment_value = os.environ.get("API_SPORTS_KEY", "").strip()
    if environment_value:
        return environment_value
    path = Path(env_file)
    if not path.is_file():
        raise ValueError("API_SPORTS_KEY is required in environment or secure .env")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("sports-stat env file permissions must be 0600 or stricter")
    key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if separator and name.strip() == "API_SPORTS_KEY":
            candidate = value.strip()
            if candidate:
                key = candidate
    if key is None:
        raise ValueError("API_SPORTS_KEY is required in environment or secure .env")
    return key


def parse_historical_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("--historical-as-of must be an ISO UTC datetime") from error
    _utc("historical_as_of", parsed)
    return parsed.astimezone(timezone.utc)


def _utc(name: str, value: Any) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
