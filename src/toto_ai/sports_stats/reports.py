from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

from toto_ai.sports_stats.domain import (
    FootballEventFeatureSnapshot,
    SportsStatsRunSnapshot,
    canonical_json,
)


def write_sports_stats_reports(
    snapshot: SportsStatsRunSnapshot,
    *,
    report_dir: str | Path = "reports/sports-stats",
) -> tuple[Path, Path, Path]:
    drawing = snapshot.drawing_number or snapshot.drawing_id
    directory = Path(report_dir) / str(drawing)
    stem = f"sports_stats_{drawing}_{snapshot.run_id[:12]}"
    json_path = directory / f"{stem}.json"
    csv_path = directory / f"{stem}.csv"
    markdown_path = directory / f"{stem}.md"
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        json_path,
        json.dumps(
            _report_payload(snapshot),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    _atomic_csv(csv_path, tuple(_event_row(event) for event in snapshot.events))
    _atomic_text(markdown_path, _markdown(snapshot))
    return json_path, csv_path, markdown_path


def _report_payload(snapshot: SportsStatsRunSnapshot) -> dict[str, Any]:
    return {
        "mode": "AUDIT ONLY",
        "package_influence": "NONE",
        "fallback": "MARKET ONLY",
        "snapshot": json.loads(canonical_json(snapshot)),
    }


def _event_row(event: FootballEventFeatureSnapshot) -> dict[str, object]:
    home = event.home_window
    away = event.away_window
    return {
        "event_order": event.event_order + 1,
        "event_id": event.event_id,
        "sport": event.sport,
        "status": event.status,
        "missing_reasons": "|".join(event.missing_reasons),
        "provider_fixture_id": event.provider_fixture_id or "",
        "league_id": event.league_id or "",
        "season": event.season or "",
        "captured_at": event.captured_at.isoformat(),
        "as_of": event.as_of.isoformat(),
        "deadline": event.deadline.isoformat(),
        "target_starts_at": event.target_starts_at.isoformat(),
        "home_team_id": event.provider_home_team_id or "",
        "away_team_id": event.provider_away_team_id or "",
        "home_history_available": home is not None,
        "away_history_available": away is not None,
        "home_fixture_count": "" if home is None else home.fixture_count,
        "away_fixture_count": "" if away is None else away.fixture_count,
        "home_wdl": "" if home is None else f"{home.wins}-{home.draws}-{home.losses}",
        "away_wdl": "" if away is None else f"{away.wins}-{away.draws}-{away.losses}",
        "home_gf_ga": "" if home is None else f"{home.goals_for}-{home.goals_against}",
        "away_gf_ga": "" if away is None else f"{away.goals_for}-{away.goals_against}",
        "home_side_wdl": (
            ""
            if home is None
            else f"{home.home_wins}-{home.home_draws}-{home.home_losses}"
        ),
        "away_side_wdl": (
            ""
            if away is None
            else f"{away.away_wins}-{away.away_draws}-{away.away_losses}"
        ),
        "home_rest_days": "" if home is None else home.rest_days,
        "away_rest_days": "" if away is None else away.rest_days,
        "home_standing_rank": (
            "" if event.home_standing is None else event.home_standing.rank
        ),
        "away_standing_rank": (
            "" if event.away_standing is None else event.away_standing.rank
        ),
        "source_fetched_at": "|".join(
            source.fetched_at.isoformat() for source in event.source_evidence
        ),
        "source_request_fingerprints": "|".join(
            source.request_fingerprint for source in event.source_evidence
        ),
        "feature_sha256": event.feature_sha256,
    }


def _markdown(snapshot: SportsStatsRunSnapshot) -> str:
    drawing = snapshot.drawing_number or snapshot.drawing_id
    lines = [
        f"# Sports statistics audit — drawing {drawing}",
        "",
        "- mode: **AUDIT ONLY**",
        "- package influence: **NONE**",
        "- fallback: **MARKET ONLY**",
        f"- run: `{snapshot.run_id}`",
        f"- captured_at: `{snapshot.captured_at.isoformat()}`",
        f"- as_of: `{snapshot.as_of.isoformat()}`",
        f"- deadline: `{snapshot.deadline.isoformat()}`",
        f"- status: **{snapshot.status}**",
        (
            "- coverage: "
            f"complete={snapshot.complete_count}, partial={snapshot.partial_count}, "
            f"missing={snapshot.missing_count}, "
            f"unsupported={snapshot.unsupported_count}"
        ),
        f"- requests/cache hits: {snapshot.requests_made}/{snapshot.cache_hits}",
        "",
        (
            "| # | Status | History H | History A | W-D-L H | W-D-L A | "
            "Rest H | Rest A | Standing H | Standing A | Missing |"
        ),
        "|---:|---|---:|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for event in snapshot.events:
        home = event.home_window
        away = event.away_window
        home_history = "" if home is None else str(home.fixture_count)
        away_history = "" if away is None else str(away.fixture_count)
        home_wdl = (
            "" if home is None else f"{home.wins}-{home.draws}-{home.losses}"
        )
        away_wdl = (
            "" if away is None else f"{away.wins}-{away.draws}-{away.losses}"
        )
        home_rest = "" if home is None else str(home.rest_days)
        away_rest = "" if away is None else str(away.rest_days)
        home_standing = (
            "" if event.home_standing is None else str(event.home_standing.rank)
        )
        away_standing = (
            "" if event.away_standing is None else str(event.away_standing.rank)
        )
        lines.append(
            f"| {event.event_order + 1} | {event.status} | {home_history} | "
            f"{away_history} | {home_wdl} | {away_wdl} | {home_rest} | "
            f"{away_rest} | {home_standing} | {away_standing} | "
            f"{', '.join(event.missing_reasons) or '-'} |"
        )
    lines.extend(
        [
            "",
            "Sports evidence is diagnostic only and is not used by probabilities, "
            "briefs, packages, scheduler decisions, PLAY, or betting markers.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_text(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError("sports-stat report requires event rows")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            writer = csv.DictWriter(output, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
