from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from toto_ai.external_odds.reviewed_schedule import (
    REVIEWED_SCHEDULE_PROVIDER,
    load_reviewed_schedule_catalog,
    revalidate_reviewed_catalog,
    reviewed_catalog_input_paths,
    select_reviewed_evidence,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
FINGERPRINT = "a" * 64


def _write_catalog(tmp_path: Path, mutate=None) -> Path:
    snapshots = []
    for name in ("official.json", "independent.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"fixture": name}), encoding="utf-8")
        snapshots.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    claims = [
        {
            "source_name": "ksi.is",
            "role": "official",
            "source_url": "https://www.ksi.is/fixture/1",
            "snapshot_path": snapshots[0][0],
            "snapshot_sha256": snapshots[0][1],
            "captured_at": "2026-07-29T11:30:00Z",
            "home_name": "KV Vesturbaer",
            "away_name": "Reynir Sandgerdi",
            "competition": "Iceland 3. Deild",
            "sport": "football",
            "gender_age_class": "men-senior",
            "starts_at": "2026-07-29T19:15:00Z",
            "status": "scheduled",
            "native_fixture_id": "7025551",
            "native_home_team_id": None,
            "native_away_team_id": None,
        },
        {
            "source_name": "sofascore.com",
            "role": "independent",
            "source_url": "https://www.sofascore.com/event/1",
            "snapshot_path": snapshots[1][0],
            "snapshot_sha256": snapshots[1][1],
            "captured_at": "2026-07-29T11:35:00Z",
            "home_name": "KV Vesturbaer",
            "away_name": "Reynir Sandgerdi",
            "competition": "Iceland 3. Deild",
            "sport": "football",
            "gender_age_class": "men-senior",
            "starts_at": "2026-07-29T19:15:00Z",
            "status": "scheduled",
            "native_fixture_id": "124",
            "native_home_team_id": None,
            "native_away_team_id": None,
        },
    ]
    payload = {
        "schema_version": 1,
        "catalog_id": "reviewed-4959",
        "generated_at": "2026-07-29T11:40:00Z",
        "records": [
            {
                "evidence_id": "ksi-sofascore-4959-9",
                "drawing_id": 11988,
                "drawing_number": 4959,
                "target_fingerprint": FINGERPRINT,
                "event_order": 8,
                "target_event_id": 998,
                "reviewer": "operator",
                "reviewed_at": "2026-07-29T11:40:00Z",
                "claims": claims,
            }
        ],
    }
    if mutate is not None:
        mutate(payload)
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return path


def test_load_valid_reviewed_catalog_is_deterministic(tmp_path: Path) -> None:
    path = _write_catalog(tmp_path)

    first = load_reviewed_schedule_catalog(
        path, evaluated_at=NOW, max_age=timedelta(hours=12)
    )
    second = load_reviewed_schedule_catalog(
        path, evaluated_at=NOW, max_age=timedelta(hours=12)
    )

    assert first == second
    assert first.semantic_hash == second.semantic_hash
    assert first.records[0].semantic_hash
    assert first.records[0].source_provider == REVIEWED_SCHEDULE_PROVIDER
    assert first.records[0].source_fixture_id is None
    assert first.records[0].schedule_only is True
    assert reviewed_catalog_input_paths(first) == (
        path.resolve(),
        (tmp_path / "independent.json").resolve(),
        (tmp_path / "official.json").resolve(),
    )


def test_revalidation_detects_snapshot_toctou_mutation(tmp_path: Path) -> None:
    path = _write_catalog(tmp_path)
    catalog = load_reviewed_schedule_catalog(
        path, evaluated_at=NOW, max_age=timedelta(hours=12)
    )
    (tmp_path / "official.json").write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot hash"):
        revalidate_reviewed_catalog(
            path,
            expected_catalog_hash=catalog.semantic_hash,
            evaluated_at=NOW + timedelta(minutes=1),
            max_age=timedelta(minutes=90),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_url", "http://example.test/fixture"),
        ("snapshot_path", "/tmp/snapshot.json"),
        ("status", "cancelled"),
        ("role", "other"),
    ],
)
def test_rejects_invalid_claim_fields(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][0].__setitem__(
            field, value
        ),
    )

    with pytest.raises(ValueError):
        load_reviewed_schedule_catalog(
            path, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("home_name", "Reynir Sandgerdi"),
        ("away_name", "KV Vesturbaer"),
        ("competition", "Iceland 2. Deild"),
        ("sport", "hockey"),
        ("gender_age_class", "women-senior"),
        ("starts_at", "2026-07-29T19:20:00Z"),
    ],
)
def test_rejects_claim_disagreement(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][1].__setitem__(
            field, value
        ),
    )

    with pytest.raises(ValueError, match="claims disagree"):
        load_reviewed_schedule_catalog(
            path, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


def test_rejects_one_source_and_duplicate_roles(tmp_path: Path) -> None:
    one = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0].__setitem__(
            "claims", payload["records"][0]["claims"][:1]
        ),
    )
    with pytest.raises(ValueError, match="official and independent"):
        load_reviewed_schedule_catalog(
            one, evaluated_at=NOW, max_age=timedelta(hours=12)
        )

    duplicate = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][1].__setitem__(
            "role", "official"
        ),
    )
    with pytest.raises(ValueError, match="official and independent"):
        load_reviewed_schedule_catalog(
            duplicate, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


def test_rejects_snapshot_escape_hash_mismatch_and_staleness(
    tmp_path: Path,
) -> None:
    escaped = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][0].__setitem__(
            "snapshot_path", "../outside.json"
        ),
    )
    with pytest.raises(ValueError, match="snapshot_path"):
        load_reviewed_schedule_catalog(
            escaped, evaluated_at=NOW, max_age=timedelta(hours=12)
        )

    mismatch = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][0].__setitem__(
            "snapshot_sha256", "0" * 64
        ),
    )
    with pytest.raises(ValueError, match="snapshot hash"):
        load_reviewed_schedule_catalog(
            mismatch, evaluated_at=NOW, max_age=timedelta(hours=12)
        )

    stale = _write_catalog(tmp_path)
    with pytest.raises(ValueError, match="stale"):
        load_reviewed_schedule_catalog(
            stale,
            evaluated_at=NOW + timedelta(hours=13),
            max_age=timedelta(hours=12),
        )


def test_rejects_future_capture_and_review_before_capture(tmp_path: Path) -> None:
    future = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0]["claims"][0].__setitem__(
            "captured_at", "2026-07-29T12:01:00Z"
        ),
    )
    with pytest.raises(ValueError, match="future"):
        load_reviewed_schedule_catalog(
            future, evaluated_at=NOW, max_age=timedelta(hours=12)
        )

    ordering = _write_catalog(
        tmp_path,
        lambda payload: payload["records"][0].__setitem__(
            "reviewed_at", "2026-07-29T11:00:00Z"
        ),
    )
    with pytest.raises(ValueError, match="reviewed_at"):
        load_reviewed_schedule_catalog(
            ordering, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


def test_rejects_unknown_and_duplicate_json_fields(tmp_path: Path) -> None:
    unknown = _write_catalog(
        tmp_path, lambda payload: payload.__setitem__("unknown", True)
    )
    with pytest.raises(ValueError, match="exact schema"):
        load_reviewed_schedule_catalog(
            unknown, evaluated_at=NOW, max_age=timedelta(hours=12)
        )

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":1,"schema_version":1,"catalog_id":"x",'
        '"generated_at":"2026-07-29T11:00:00Z","records":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_reviewed_schedule_catalog(
            duplicate, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


def test_rejects_duplicate_evidence_and_target_bindings(tmp_path: Path) -> None:
    def duplicate_record(payload):
        payload["records"].append(dict(payload["records"][0]))

    path = _write_catalog(tmp_path, duplicate_record)
    with pytest.raises(ValueError, match="unique"):
        load_reviewed_schedule_catalog(
            path, evaluated_at=NOW, max_age=timedelta(hours=12)
        )


def test_select_requires_exact_target_binding(tmp_path: Path) -> None:
    catalog = load_reviewed_schedule_catalog(
        _write_catalog(tmp_path),
        evaluated_at=NOW,
        max_age=timedelta(hours=12),
    )
    selected = select_reviewed_evidence(
        catalog,
        drawing_id=11988,
        drawing_number=4959,
        target_fingerprint=FINGERPRINT,
        event_order=8,
        target_event_id=998,
    )
    assert selected.evidence_id == "ksi-sofascore-4959-9"

    with pytest.raises(ValueError, match="exact reviewed evidence"):
        select_reviewed_evidence(
            catalog,
            drawing_id=11988,
            drawing_number=4959,
            target_fingerprint=FINGERPRINT,
            event_order=7,
            target_event_id=998,
        )
