from __future__ import annotations

import csv
import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from toto_ai.external_odds.collection import (
    EXTERNAL_CONSENSUS,
    ExternalBookmakerQuoteRecord,
    ExternalCollectionSnapshot,
    ExternalEventDispositionRecord,
)
from toto_ai.external_odds.consensus import devig_decimal_prices
from toto_ai.external_odds.domain import OutcomeTriplet
from toto_ai.external_odds.the_odds_api import CreditState, RequestEvidence

ACTIVATION_STATUS = "NOT_ACTIVATED"
_CSV_FIELDS = (
    "event_order",
    "target_event_id",
    "sport",
    "championship",
    "home_team",
    "away_team",
    "match_status",
    "match_orientation",
    "provider_event_id",
    "provider_event_source_endpoint",
    "provider_event_request_fingerprint",
    "provider_event_fetched_at",
    "bk_probability_1",
    "bk_probability_x",
    "bk_probability_2",
    "onexbet_probability_1",
    "onexbet_probability_x",
    "onexbet_probability_2",
    "pinnacle_probability_1",
    "pinnacle_probability_x",
    "pinnacle_probability_2",
    "consensus_probability_1",
    "consensus_probability_x",
    "consensus_probability_2",
    "eligible_bookmaker_count",
    "odds_age_hours",
    "fallback_reason",
    "activation_status",
)


@dataclass(frozen=True)
class TheOddsShadowReportPaths:
    json_path: Path
    csv_path: Path
    markdown_path: Path


def load_the_odds_api_key(env_file: str | Path = ".env") -> str:
    environment_value = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if environment_value:
        return environment_value

    path = Path(env_file)
    if path.is_symlink() or not path.is_file():
        raise ValueError("THE_ODDS_API_KEY is required")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077 or not mode & stat.S_IRUSR:
        raise ValueError("The Odds API env file must have mode 0600 or stricter")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise ValueError("THE_ODDS_API_KEY is required") from None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.removeprefix("export ").strip() != "THE_ODDS_API_KEY":
            continue
        resolved = value.strip()
        if len(resolved) >= 2 and resolved[0] == resolved[-1] and resolved[0] in {
            "'",
            '"',
        }:
            resolved = resolved[1:-1]
        if resolved:
            return resolved
    raise ValueError("THE_ODDS_API_KEY is required")


def write_the_odds_shadow_reports(
    snapshot: ExternalCollectionSnapshot,
    *,
    request_evidence: tuple[RequestEvidence, ...],
    credit_state: CreditState,
    credits_spent: int,
    report_dir: str | Path,
) -> TheOddsShadowReportPaths:
    if snapshot.provider != "the-odds-api":
        raise ValueError("shadow reports require a the-odds-api collection")
    if snapshot.event_count != 15 or len(snapshot.events) != 15:
        raise ValueError("shadow reports require exactly 15 event dispositions")
    drawing_label = (
        str(snapshot.drawing_number)
        if snapshot.drawing_number is not None
        else f"id-{snapshot.drawing_id}"
    )
    target_dir = Path(report_dir) / drawing_label
    stem = f"the_odds_api_shadow_{snapshot.collection_id}"
    paths = TheOddsShadowReportPaths(
        json_path=target_dir / f"{stem}.json",
        csv_path=target_dir / f"{stem}.csv",
        markdown_path=target_dir / f"{stem}.md",
    )
    event_rows = tuple(_event_report(event) for event in snapshot.events)
    payload = {
        "schema_version": 1,
        "activation_status": ACTIVATION_STATUS,
        "actionable": False,
        "production_probability_changed": False,
        "package_selection_changed": False,
        "drawing_id": snapshot.drawing_id,
        "drawing_number": snapshot.drawing_number,
        "collection_id": snapshot.collection_id,
        "provider": snapshot.provider,
        "fetched_at": snapshot.fetched_at,
        "target_fetched_at": snapshot.target_fetched_at,
        "deadline": snapshot.deadline,
        "target_fingerprint": snapshot.target_fingerprint,
        "requests_made": snapshot.requests_made,
        "cache_hits": snapshot.cache_hits,
        "credits_spent": credits_spent,
        "credit_state": asdict(credit_state) | {"limit": credit_state.limit},
        "requests": tuple(_request_report(item) for item in request_evidence),
        "events": event_rows,
    }
    _atomic_text(
        paths.json_path,
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
    )
    _write_csv(paths.csv_path, event_rows)
    _atomic_text(paths.markdown_path, _markdown_report(payload))
    return paths


def _event_report(event: ExternalEventDispositionRecord) -> dict[str, object]:
    bk = _bk_probabilities(event)
    onexbet = _bookmaker_probabilities(event, "onexbet")
    pinnacle = _bookmaker_probabilities(event, "pinnacle")
    consensus = (
        (event.probability_1, event.probability_x, event.probability_2)
        if event.probability_source == EXTERNAL_CONSENSUS
        else None
    )
    return {
        "event_order": event.event_order + 1,
        "target_event_id": event.target_event_id,
        "sport": event.sport,
        "championship": event.championship,
        "home_team": event.home_team,
        "away_team": event.away_team,
        "starts_at": event.starts_at,
        "provider_starts_at": event.provider_starts_at,
        "match_status": event.match_status,
        "match_orientation": event.match_orientation,
        "match_reason": event.match_reason,
        "provider_event_id": event.provider_event_id,
        "provider_event_source_endpoint": event.provider_event_source_endpoint,
        "provider_event_request_fingerprint": (
            event.provider_event_request_fingerprint
        ),
        "provider_event_fetched_at": event.provider_event_fetched_at,
        "provider_event_payload_hash": event.provider_event_payload_hash,
        "bk_probabilities": bk,
        "onexbet_probabilities": onexbet,
        "pinnacle_probabilities": pinnacle,
        "eligible_consensus_probabilities": consensus,
        "eligible_bookmaker_count": event.eligible_bookmaker_count,
        "bookmaker_quote_count": len(event.bookmaker_quotes),
        "odds_age_hours": event.odds_age_hours,
        "probability_source": event.probability_source,
        "fallback_reason": event.fallback_reason,
        "payload_hash": event.payload_hash,
        "activation_status": ACTIVATION_STATUS,
    }


def _bk_probabilities(event: ExternalEventDispositionRecord) -> OutcomeTriplet | None:
    values = (
        event.target_bk_probability_1,
        event.target_bk_probability_x,
        event.target_bk_probability_2,
    )
    if all(value is not None for value in values):
        return tuple(float(value) for value in values)  # type: ignore[return-value]
    if event.probability_source != EXTERNAL_CONSENSUS:
        return event.probability_1, event.probability_x, event.probability_2
    return None


def _bookmaker_probabilities(
    event: ExternalEventDispositionRecord,
    bookmaker_id: str,
) -> OutcomeTriplet | None:
    matches = tuple(
        quote
        for quote in event.bookmaker_quotes
        if quote.bookmaker_id == bookmaker_id and quote.eligible == 1
    )
    if len(matches) != 1:
        return None
    quote = matches[0]
    prices = _complete_prices(quote)
    if prices is None:
        return None
    probabilities = devig_decimal_prices(prices)
    if event.match_orientation == "reversed":
        return probabilities[2], probabilities[1], probabilities[0]
    if event.match_orientation not in {"same", "none"}:
        return None
    return probabilities


def _complete_prices(
    quote: ExternalBookmakerQuoteRecord,
) -> tuple[float, float, float] | None:
    values = (quote.home_price, quote.draw_price, quote.away_price)
    if any(value is None for value in values):
        return None
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _request_report(evidence: RequestEvidence) -> dict[str, object]:
    return {
        "endpoint": evidence.endpoint,
        "params": evidence.params,
        "request_fingerprint": evidence.request_fingerprint,
        "response_hash": evidence.response_hash,
        "fetched_at": evidence.fetched_at.isoformat(),
        "credit_remaining": evidence.credit_remaining,
        "credit_used": evidence.credit_used,
        "credit_cost": evidence.credit_cost,
        "cache_hit": evidence.cache_hit,
    }


def _write_csv(path: Path, events: tuple[dict[str, object], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for event in events:
                writer.writerow(_csv_event(event))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _csv_event(event: dict[str, object]) -> dict[str, object]:
    row = {field: event.get(field) for field in _CSV_FIELDS}
    _set_probability_columns(row, "bk", event.get("bk_probabilities"))
    _set_probability_columns(row, "onexbet", event.get("onexbet_probabilities"))
    _set_probability_columns(row, "pinnacle", event.get("pinnacle_probabilities"))
    _set_probability_columns(
        row,
        "consensus",
        event.get("eligible_consensus_probabilities"),
    )
    return row


def _set_probability_columns(
    row: dict[str, object],
    prefix: str,
    probabilities: object,
) -> None:
    values = probabilities if isinstance(probabilities, tuple) else (None,) * 3
    for suffix, value in zip(("1", "x", "2"), values, strict=True):
        row[f"{prefix}_probability_{suffix}"] = value


def _markdown_report(payload: dict[str, object]) -> str:
    credit = payload["credit_state"]
    assert isinstance(credit, dict)
    lines = [
        "# The Odds API shadow report",
        "",
        f"- Activation: **{ACTIVATION_STATUS}**",
        "- Actionable: **no**",
        "- Production probability/package changed: **no**",
        f"- Drawing: `{payload['drawing_number']}` (`{payload['drawing_id']}`)",
        f"- Collection: `{payload['collection_id']}`",
        f"- Requests: `{payload['requests_made']}`; cache hits: "
        f"`{payload['cache_hits']}`; credits spent: `{payload['credits_spent']}`",
        f"- Credits remaining: `{credit.get('remaining')}`",
        "",
        "| # | Match | Disposition | BK | 1xBet | Pinnacle | Consensus | Fallback |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    events = payload["events"]
    assert isinstance(events, tuple)
    for item in events:
        assert isinstance(item, dict)
        lines.append(
            "| {event_order} | {home_team} — {away_team} | "
            "{match_status}/{match_orientation} | {bk} | {onexbet} | "
            "{pinnacle} | {consensus} | {fallback} |".format(
                **item,
                bk=_format_probabilities(item["bk_probabilities"]),
                onexbet=_format_probabilities(item["onexbet_probabilities"]),
                pinnacle=_format_probabilities(item["pinnacle_probabilities"]),
                consensus=_format_probabilities(
                    item["eligible_consensus_probabilities"]
                ),
                fallback=item["fallback_reason"] or "—",
            )
        )
    return "\n".join(lines) + "\n"


def _format_probabilities(value: object) -> str:
    if not isinstance(value, tuple):
        return "—"
    return "/".join(f"{float(item):.1%}" for item in value)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            _write(output, content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write(output: TextIO, content: str) -> None:
    output.write(content)
