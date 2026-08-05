import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import typer
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db


def target_payload(deadline):
    return {
        "data": {
            "id": 11970,
            "number": 4952,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": deadline.isoformat(),
            "pool_sum": 1000,
            "jackpot": 100,
            "events": [
                {
                    "id": 30_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "championship": "World. Friendly",
                    "sport": "football",
                    "start_at": None,
                    "quotes": {
                        "pool_win_1": 34,
                        "pool_draw": 33,
                        "pool_win_2": 33,
                        "bk_win_1": 34,
                        "bk_draw": 33,
                        "bk_win_2": 33,
                    },
                }
                for order in range(15)
            ],
        }
    }


class PageOnlyClient:
    def __init__(self, payload):
        self.payload = payload
        self.page_calls = 0
        self.detail_calls = 0

    def drawings(self, name="baltbet-main", page=1):
        self.page_calls += 1
        data = self.payload["data"]
        return {
            "data": [
                {
                    "id": data["id"],
                    "number": data["number"],
                    "name": name,
                    "status": data["status"],
                    "ended_at": data["ended_at"],
                }
            ]
        }

    def drawing_info(self, drawing_id):
        self.detail_calls += 1
        raise AssertionError(f"unexpected detail request {drawing_id}")


def prepared_result(target, *, fingerprint: str):
    """Return the complete preparation-result contract used by CLI tests."""
    return SimpleNamespace(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        drawing_fingerprint=fingerprint,
        provider="api-sports",
        status="ready",
        mapped_count=15,
        external_coverage_count=15,
        baseline_only_event_orders=(),
        unresolved_event_orders=(),
        eligibility=SimpleNamespace(status="playable"),
        schedule_diagnostics=(),
    )


def test_sync_prepare_cli_uses_one_page_and_cached_detail(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    payload = target_payload(now + timedelta(days=1))
    write_drawing_detail_cache(
        payload,
        drawing_id=11970,
        cache_dir=tmp_path / "raw",
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    fake_client = PageOnlyClient(payload)
    monkeypatch.setattr(cli, "TotoBriefClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(cli, "seed_reviewed_alias_config", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "load_local_schedule", lambda *_a, **_k: ())
    monkeypatch.setattr(
        cli,
        "prepare_drawing",
        lambda target, *_a, **_k: prepared_result(
            target,
            fingerprint="a" * 64,
        ),
    )
    schedule = tmp_path / "schedule.json"
    schedule.write_text("{}")
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"version":1,"aliases":{}}')

    result = CliRunner().invoke(
        cli.app,
        [
            "sync-prepare",
            "--open",
            "--db",
            str(tmp_path / "toto.db"),
            "--raw-cache-dir",
            str(tmp_path / "raw"),
            "--schedule-cache",
            str(schedule),
            "--aliases",
            str(aliases),
            "--totobrief-rate-state",
            str(tmp_path / "rate.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output.splitlines()[-1])
    assert output["status"] == "ready"
    assert output["mapped_count"] == 15
    assert output["totobrief_detail_source"] == "cache:inspect-api"
    assert fake_client.page_calls == 1
    assert fake_client.detail_calls == 0


def test_sync_prepare_help_exposes_rate_and_cache_controls():
    result = CliRunner().invoke(cli.app, ["sync-prepare", "--help"])
    command = typer.main.get_command(cli.app).commands["sync-prepare"]
    option_names = {
        option
        for parameter in command.params
        for option in getattr(parameter, "opts", ())
    }

    assert result.exit_code == 0
    assert "--totobrief-min-interval" in option_names
    assert "--totobrief-max-retries" in option_names
    assert "--detail-cache-max-age-seconds" in option_names
    assert "--sync-only" in option_names
    assert "--expected-drawing-number" in option_names


def test_sync_prepare_expected_number_mismatch_stops_before_detail_or_prepare(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    payload = target_payload(now + timedelta(days=1))
    fake_client = PageOnlyClient(payload)
    monkeypatch.setattr(cli, "TotoBriefClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(
        cli,
        "prepare_drawing",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("mismatch must stop before preparation")
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "sync-prepare",
            "--open",
            "--expected-drawing-number",
            "4953",
            "--db",
            str(tmp_path / "toto.db"),
            "--raw-cache-dir",
            str(tmp_path / "raw"),
            "--totobrief-rate-state",
            str(tmp_path / "rate.json"),
        ],
    )

    assert result.exit_code == 2
    assert "expected drawing 4953" in result.output
    assert "selected 4952" in result.output
    assert fake_client.page_calls == 1
    assert fake_client.detail_calls == 0


def test_sync_prepare_expected_number_match_is_idempotent(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    payload = target_payload(now + timedelta(days=1))
    write_drawing_detail_cache(
        payload,
        drawing_id=11970,
        cache_dir=tmp_path / "raw",
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    fake_client = PageOnlyClient(payload)
    monkeypatch.setattr(cli, "TotoBriefClient", lambda **_kwargs: fake_client)

    arguments = [
        "sync-prepare",
        "--open",
        "--sync-only",
        "--expected-drawing-number",
        "4952",
        "--db",
        str(tmp_path / "toto.db"),
        "--raw-cache-dir",
        str(tmp_path / "raw"),
        "--totobrief-rate-state",
        str(tmp_path / "rate.json"),
    ]
    first = CliRunner().invoke(cli.app, arguments)
    second = CliRunner().invoke(cli.app, arguments)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert fake_client.page_calls == 2
    assert fake_client.detail_calls == 0


def test_prepare_drawing_uses_synced_local_cache_without_totobrief_client(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=1)
    payload = target_payload(deadline)
    raw_cache = tmp_path / "raw"
    write_drawing_detail_cache(
        payload,
        drawing_id=11970,
        cache_dir=raw_cache,
        fetched_at=now,
        source="morning-sync",
        allowed_root=tmp_path,
    )
    db = tmp_path / "toto.db"
    engine = init_db(db)
    factory = get_session_factory(engine)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11970,
                number=4952,
                name="baltbet-main",
                status="active",
                ended_at=deadline.isoformat(),
            )
        )
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("TotoBriefClient must not be constructed")
        ),
    )
    monkeypatch.setattr(cli, "seed_reviewed_alias_config", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "load_local_schedule", lambda *_a, **_k: ())
    monkeypatch.setattr(
        cli,
        "prepare_drawing",
        lambda target, *_a, **_k: prepared_result(
            target,
            fingerprint="b" * 64,
        ),
    )
    schedule = tmp_path / "schedule.json"
    schedule.write_text("{}")
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"version":1,"aliases":{}}')

    result = CliRunner().invoke(
        cli.app,
        [
            "prepare-drawing",
            "--drawing-id",
            "11970",
            "--db",
            str(db),
            "--raw-cache-dir",
            str(raw_cache),
            "--schedule-cache",
            str(schedule),
            "--aliases",
            str(aliases),
        ],
    )

    assert result.exit_code == 0, result.output
    engine.dispose()


def test_prepare_drawing_explicit_operational_cache_requires_sidecar(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    cache_path = tmp_path / "raw" / "drawing_11970.json"
    cache_path.parent.mkdir()
    cache_path.write_text(
        json.dumps(target_payload(now + timedelta(days=1))),
        encoding="utf-8",
    )
    schedule = tmp_path / "schedule.json"
    schedule.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        cli.app,
        [
            "prepare-drawing",
            "--drawing-id",
            "11970",
            "--db",
            str(tmp_path / "toto.db"),
            "--target-cache",
            str(cache_path),
            "--schedule-cache",
            str(schedule),
        ],
    )

    assert result.exit_code == 2
    assert "metadata sidecar is missing" in result.output


def test_sync_prepare_sync_only_never_writes_preparation_or_requires_api_key(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(timezone.utc)
    payload = target_payload(now + timedelta(days=1))
    write_drawing_detail_cache(
        payload,
        drawing_id=11970,
        cache_dir=tmp_path / "raw",
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    fake_client = PageOnlyClient(payload)
    monkeypatch.setattr(cli, "TotoBriefClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(
        cli,
        "seed_reviewed_alias_config",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("sync-only must not seed preparation aliases")
        ),
    )
    monkeypatch.setattr(
        cli,
        "prepare_drawing",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("sync-only must not write preparation or pins")
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "sync-prepare",
            "--open",
            "--sync-only",
            "--db",
            str(tmp_path / "toto.db"),
            "--raw-cache-dir",
            str(tmp_path / "raw"),
            "--totobrief-rate-state",
            str(tmp_path / "rate.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output.splitlines()[-1])
    assert output["status"] == "synchronized"
    assert output["preparation_written"] is False
    assert fake_client.page_calls == 1
    assert fake_client.detail_calls == 0
