import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toto_ai.cli import app


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "data" / "schedule-evidence"
    reviews = root / "reviews"
    snapshots = root / "snapshots"
    reviews.mkdir(parents=True)
    snapshots.mkdir()
    ledger = root / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-31T09:00:00Z",
                "observations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    snapshot_rows = (
        {
            "drawing_number": 4992,
            "event_order": 6,
            "target_event_id": 180353,
            "target_home_team": "Home FC",
            "target_away_team": "Away FC",
            "home_name": "Home FC",
            "away_name": "Away FC",
            "starts_at": "2026-08-31T12:00:00Z",
            "source_provider": "alpha-v1",
        },
        {
            "drawing_number": 4992,
            "event_order": 6,
            "target_event_id": 180353,
            "target_home_team": "Home FC",
            "target_away_team": "Away FC",
            "home_name": "Home FC",
            "away_name": "Away FC",
            "starts_at": "2026-08-31T12:00:00Z",
            "source_provider": "beta-v1",
        },
    )
    snapshot_paths = []
    for index, row in enumerate(snapshot_rows, start=1):
        path = snapshots / f"source-{index}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        snapshot_paths.append(path)
    review_payload = {
        "schema_version": 1,
        "target": {
            "drawing_id": 12083,
            "drawing_number": 4992,
            "event_order": 6,
            "target_event_id": 180353,
            "sport": "football",
            "championship": "Test league",
            "home_team": "Home FC",
            "away_team": "Away FC",
        },
        "observation": {
            "observation_id": "prepared-review-test-1",
            "sport": "football",
            "gender_age_class": "men-senior",
            "competition_aliases": ["Test league"],
            "home_entity": "Home FC",
            "home_aliases": ["Home FC"],
            "away_entity": "Away FC",
            "away_aliases": ["Away FC"],
            "starts_at": "2026-08-31T12:00:00Z",
            "status": "scheduled",
            "conditional": False,
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-08-31T10:10:00Z",
        },
        "sources": [
            {
                "source_name": "Alpha",
                "role": "independent",
                "source_url": "https://alpha.test/event/1",
                "snapshot": snapshot_paths[0].name,
                "snapshot_sha256": _sha(snapshot_paths[0]),
                "home_team": "Home FC",
                "away_team": "Away FC",
                "starts_at": "2026-08-31T12:00:00Z",
                "status": "scheduled",
                "captured_at": "2026-08-31T10:00:00Z",
            },
            {
                "source_name": "Beta",
                "role": "independent",
                "source_url": "https://beta.test/event/2",
                "snapshot": snapshot_paths[1].name,
                "snapshot_sha256": _sha(snapshot_paths[1]),
                "home_team": "Home FC",
                "away_team": "Away FC",
                "starts_at": "2026-08-31T12:00:00Z",
                "status": "not_started",
                "captured_at": "2026-08-31T10:01:00Z",
            },
        ],
    }
    review = reviews / "prepared.json"
    review.write_text(json.dumps(review_payload), encoding="utf-8")
    return {
        "ledger": ledger,
        "reviews": reviews,
        "snapshots": snapshots,
        "snapshot_paths": snapshot_paths,
        "review": review,
        "payload": review_payload,
    }


def _arguments(fixture: dict[str, object], *, apply: bool = False) -> list[str]:
    result = [
        "schedule-evidence-review",
        "--review",
        str(fixture["review"]),
        "--review-sha256",
        _sha(fixture["review"]),
        "--ledger",
        str(fixture["ledger"]),
        "--reviews-dir",
        str(fixture["reviews"]),
        "--snapshots-dir",
        str(fixture["snapshots"]),
    ]
    if apply:
        result.append("--apply")
    return result


def _rewrite_review(fixture: dict[str, object], payload: dict[str, object]) -> None:
    fixture["review"].write_text(json.dumps(payload), encoding="utf-8")


def test_review_defaults_to_dry_run_without_mutation(tmp_path):
    fixture = _fixture(tmp_path)
    before = fixture["ledger"].read_bytes()
    result = CliRunner().invoke(app, _arguments(fixture))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "validated_dry_run"
    assert fixture["ledger"].read_bytes() == before


def test_review_apply_is_idempotent(tmp_path):
    fixture = _fixture(tmp_path)
    first = CliRunner().invoke(app, _arguments(fixture, apply=True))
    assert first.exit_code == 0, first.output
    applied = fixture["ledger"].read_bytes()
    second = CliRunner().invoke(app, _arguments(fixture, apply=True))
    assert second.exit_code == 0, second.output
    assert json.loads(second.output)["status"] == "already_present"
    assert fixture["ledger"].read_bytes() == applied
    assert len(json.loads(applied)["observations"]) == 1


@pytest.mark.parametrize(
    ("kind", "mutate"),
    [
        ("snapshot", lambda row: row["sources"][0].update(snapshot_sha256="0" * 64)),
        (
            "domain",
            lambda row: row["sources"][1].update(source_url="https://alpha.test/2"),
        ),
        (
            "time",
            lambda row: row["sources"][1].update(starts_at="2026-08-31T13:00:00Z"),
        ),
        ("team", lambda row: row["sources"][1].update(home_team="Wrong FC")),
        ("status", lambda row: row["sources"][1].update(status="finished")),
    ],
)
def test_review_rejects_invalid_evidence(tmp_path, kind, mutate):
    fixture = _fixture(tmp_path)
    payload = deepcopy(fixture["payload"])
    mutate(payload)
    _rewrite_review(fixture, payload)
    before = fixture["ledger"].read_bytes()
    result = CliRunner().invoke(app, _arguments(fixture))
    assert result.exit_code == 22, (kind, result.output)
    assert fixture["ledger"].read_bytes() == before


def test_review_rejects_invalid_document_hash(tmp_path):
    fixture = _fixture(tmp_path)
    arguments = _arguments(fixture)
    arguments[arguments.index("--review-sha256") + 1] = "0" * 64
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 22


def test_status_reports_counts_hashes_and_unresolved_exit(tmp_path):
    fixture = _fixture(tmp_path)
    assert CliRunner().invoke(app, _arguments(fixture, apply=True)).exit_code == 0
    arguments = [
        "schedule-evidence-status",
        "--ledger",
        str(fixture["ledger"]),
        "--reviews-dir",
        str(fixture["reviews"]),
        "--snapshots-dir",
        str(fixture["snapshots"]),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["reviewed_count"] == payload["consensus_count"] == 1
    assert payload["unresolved_count"] == 0
    assert payload["ledger_sha256"] == _sha(fixture["ledger"])
    orphan = fixture["snapshots"] / "orphan.json"
    orphan.write_text(
        json.dumps(
            {
                "drawing_number": 4992,
                "event_order": 7,
                "target_event_id": 180354,
                "home_name": "Other Home",
                "away_name": "Other Away",
                "starts_at": "2026-08-31T13:00:00Z",
                "source_provider": "orphan-v1",
            }
        )
    )
    unresolved = CliRunner().invoke(app, arguments)
    assert unresolved.exit_code == 21
    assert json.loads(unresolved.output)["unresolved_count"] == 1


def test_verify_rejects_corrupted_ledger_and_snapshot(tmp_path):
    fixture = _fixture(tmp_path)
    assert CliRunner().invoke(app, _arguments(fixture, apply=True)).exit_code == 0
    arguments = [
        "schedule-evidence-verify",
        "--ledger",
        str(fixture["ledger"]),
        "--reviews-dir",
        str(fixture["reviews"]),
        "--snapshots-dir",
        str(fixture["snapshots"]),
    ]
    fixture["snapshot_paths"][0].write_text("corrupted", encoding="utf-8")
    snapshot_result = CliRunner().invoke(app, arguments)
    assert snapshot_result.exit_code == 20

    other = _fixture(tmp_path / "other")
    other["ledger"].write_text("{broken", encoding="utf-8")
    ledger_result = CliRunner().invoke(
        app,
        [
            "schedule-evidence-verify",
            "--ledger",
            str(other["ledger"]),
            "--reviews-dir",
            str(other["reviews"]),
            "--snapshots-dir",
            str(other["snapshots"]),
        ],
    )
    assert ledger_result.exit_code == 20


def test_status_skips_arabic_and_hindi_aliases_with_diagnostic(tmp_path):
    fixture = _fixture(tmp_path)
    for index, (home, away) in enumerate(
        (("الهلال", "النصر"), ("मोहन बागान", "ईस्ट बंगाल")), start=20
    ):
        (fixture["snapshots"] / f"unsupported-{index}.json").write_text(
            json.dumps(
                {
                    "drawing_number": 4993,
                    "event_order": index,
                    "target_event_id": 200000 + index,
                    "home_name": home,
                    "away_name": away,
                    "starts_at": "2026-09-01T12:00:00Z",
                    "source_provider": f"provider-{index}",
                }
            ),
            encoding="utf-8",
        )
    result = CliRunner().invoke(
        app,
        [
            "schedule-evidence-status",
            "--ledger",
            str(fixture["ledger"]),
            "--reviews-dir",
            str(fixture["reviews"]),
            "--snapshots-dir",
            str(fixture["snapshots"]),
        ],
    )
    assert result.exit_code == 21, result.output
    assert json.loads(result.output)["unsupported_alias_count"] >= 2


@pytest.mark.parametrize(
    ("first_name", "first_url", "second_name", "second_url", "accepted"),
    [
        ("Alpha", "https://api.alpha.test/1", "Beta", "https://alpha.test/2", False),
        (
            "Same Publisher",
            "https://alpha.test/1",
            "Same Publisher",
            "https://beta.test/2",
            False,
        ),
        (
            "GOAL API",
            "https://api.goal-api.com/1",
            "TheSportsDB",
            "https://www.thesportsdb.com/2",
            True,
        ),
        (
            "MLSZ",
            "https://adatbank.mlsz.hu/1",
            "Szeged club",
            "https://szeged-grosicsakademia.hu/2",
            True,
        ),
    ],
)
def test_review_uses_conservative_publisher_independence(
    tmp_path, first_name, first_url, second_name, second_url, accepted
):
    fixture = _fixture(tmp_path)
    payload = deepcopy(fixture["payload"])
    payload["sources"][0].update(source_name=first_name, source_url=first_url)
    payload["sources"][1].update(source_name=second_name, source_url=second_url)
    _rewrite_review(fixture, payload)
    result = CliRunner().invoke(app, _arguments(fixture))
    assert result.exit_code == (0 if accepted else 22), result.output


def _process_command(fixture):
    return [sys.executable, "-m", "toto_ai.cli", *_arguments(fixture, apply=True)]


def test_concurrent_apply_is_locked_and_never_loses_updates(tmp_path):
    fixture = _fixture(tmp_path)
    identical = [
        subprocess.Popen(
            _process_command(fixture), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(2)
    ]
    assert [process.wait(timeout=30) for process in identical] == [0, 0]
    assert len(json.loads(fixture["ledger"].read_text())["observations"]) == 1

    other = _fixture(tmp_path / "different")
    second_payload = deepcopy(other["payload"])
    second_payload["observation"]["observation_id"] = "prepared-review-test-2"
    second_payload["target"]["event_order"] = 7
    second_payload["target"]["target_event_id"] = 180354
    second_review = other["reviews"] / "prepared-2.json"
    second_review.write_text(json.dumps(second_payload), encoding="utf-8")
    second = dict(other)
    second["review"] = second_review
    processes = [
        subprocess.Popen(
            _process_command(item), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for item in (other, second)
    ]
    assert [process.wait(timeout=30) for process in processes] == [0, 0]
    loaded = json.loads(other["ledger"].read_text())
    assert {row["observation_id"] for row in loaded["observations"]} == {
        "prepared-review-test-1",
        "prepared-review-test-2",
    }
