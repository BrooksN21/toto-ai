from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_external_odds_audit import _collection
from toto_ai.cli import app
from toto_ai.external_odds.the_odds_shadow import (
    load_the_odds_api_key,
    write_the_odds_shadow_reports,
)

runner = CliRunner()


def test_key_loader_reads_secure_env_without_exposing_value(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=value\nTHE_ODDS_API_KEY=secret-key\n", encoding="utf-8")
    env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert load_the_odds_api_key(env_file) == "secret-key"


def test_key_loader_rejects_permissive_env_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("THE_ODDS_API_KEY=secret-key\n", encoding="utf-8")
    env_file.chmod(0o644)

    with pytest.raises(ValueError, match="0600"):
        load_the_odds_api_key(env_file)


def test_shadow_reports_show_separate_bookmaker_views_and_not_activated(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.collection import (
        ExternalBookmakerQuoteRecord,
        ExternalMarketProvenanceRecord,
    )
    from toto_ai.external_odds.the_odds_api import CreditState, RequestEvidence

    source = ExternalMarketProvenanceRecord(
        updated_at="2026-08-13T17:50:00+00:00",
        fetched_at="2026-08-13T17:55:00+00:00",
        payload_hash="market-hash",
        home_price=2.0,
        draw_price=3.5,
        away_price=4.0,
    )
    quotes = (
        ExternalBookmakerQuoteRecord(
            bookmaker_id="onexbet",
            market_name="1X2",
            updated_at=source.updated_at,
            fetched_at=source.fetched_at,
            payload_hash=source.payload_hash,
            home_price=2.0,
            draw_price=3.5,
            away_price=4.0,
            eligible=1,
            rejection_reason=None,
            source_count=1,
            source_provenance=(source,),
        ),
        ExternalBookmakerQuoteRecord(
            bookmaker_id="pinnacle",
            market_name="1X2",
            updated_at=source.updated_at,
            fetched_at=source.fetched_at,
            payload_hash="pinnacle-hash",
            home_price=2.1,
            draw_price=3.4,
            away_price=3.8,
            eligible=1,
            rejection_reason=None,
            source_count=1,
            source_provenance=(source,),
        ),
    )
    base = _collection(1, ())
    snapshot = replace(
        base,
        provider="the-odds-api",
        events=(replace(base.events[0], bookmaker_quotes=quotes), *base.events[1:]),
    )
    evidence = (
        RequestEvidence(
            endpoint="/v4/sports/soccer_epl/odds",
            params=(("markets", "h2h"), ("regions", "eu")),
            request_fingerprint="request-hash",
            response_hash="response-hash",
            fetched_at=source_time(),
            credit_remaining=499,
            credit_used=1,
            credit_cost=1,
            cache_hit=False,
        ),
    )

    paths = write_the_odds_shadow_reports(
        snapshot,
        request_evidence=evidence,
        credit_state=CreditState(499, 1, 1),
        credits_spent=1,
        report_dir=tmp_path,
    )

    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    csv_text = paths.csv_path.read_text(encoding="utf-8")
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert payload["activation_status"] == "NOT_ACTIVATED"
    assert payload["events"][0]["onexbet_probabilities"] is not None
    assert payload["events"][0]["pinnacle_probabilities"] is not None
    assert payload["requests"][0]["credit_cost"] == 1
    assert "onexbet_probability_1" in csv_text
    assert "Pinnacle" in markdown
    assert "NOT_ACTIVATED" in markdown


def source_time():
    from datetime import datetime, timezone

    return datetime(2026, 8, 13, 17, 55, tzinfo=timezone.utc)


def test_shadow_cli_requires_key_before_provider_construction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import toto_ai.cli as cli

    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    monkeypatch.setattr(
        cli,
        "load_the_odds_api_key",
        lambda _path: (_ for _ in ()).throw(ValueError("THE_ODDS_API_KEY is required")),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "TheOddsAPIClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("provider must not be constructed")
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "collect-the-odds-api-shadow",
            "--open",
            "--db",
            str(tmp_path / "toto.db"),
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code != 0
    assert "THE_ODDS_API_KEY" in result.output
    assert "provider must not" not in result.output


def test_shadow_cli_is_hard_labeled_not_activated(monkeypatch, tmp_path: Path) -> None:
    import toto_ai.cli as cli

    snapshot = replace(_collection(1, ()), provider="the-odds-api")
    captured: dict[str, object] = {}

    class FakeProvider:
        request_evidence = ()
        credits_spent = 0
        credit_state = type(
            "CreditState",
            (),
            {"remaining": 500, "used": 0, "last_cost": 0, "limit": 500},
        )()

        def __init__(self, key, **kwargs):
            captured["key"] = key
            captured.update(kwargs)

    monkeypatch.setattr(cli, "load_the_odds_api_key", lambda _path: "secret-key")
    monkeypatch.setattr(cli, "TheOddsAPIClient", FakeProvider)
    monkeypatch.setattr(cli, "init_db", lambda _path: "engine")
    monkeypatch.setattr(cli, "get_session_factory", lambda _engine: "factory")
    monkeypatch.setattr(cli, "load_aliases", lambda _path: {})
    monkeypatch.setattr(cli, "TotoBriefClient", lambda: "totobrief")
    monkeypatch.setattr(
        cli,
        "collect_open_external_odds",
        lambda *args, **kwargs: snapshot,
    )
    monkeypatch.setattr(
        cli,
        "write_the_odds_shadow_reports",
        lambda *args, **kwargs: type(
            "Paths",
            (),
            {
                "json_path": tmp_path / "shadow.json",
                "csv_path": tmp_path / "shadow.csv",
                "markdown_path": tmp_path / "shadow.md",
            },
        )(),
    )

    result = runner.invoke(
        app,
        [
            "collect-the-odds-api-shadow",
            "--open",
            "--db",
            str(tmp_path / "toto.db"),
            "--report-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "NOT_ACTIVATED" in result.output
    assert "secret-key" not in result.output
    assert captured["key"] == "secret-key"
