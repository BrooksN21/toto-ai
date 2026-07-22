import json
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.api.detail_cache import (
    load_drawing_detail_cache,
    write_drawing_detail_cache,
)

NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


def payload(drawing_id=11970):
    return {
        "data": {
            "id": drawing_id,
            "number": 4952,
            "ended_at": "2026-07-22T16:00:00Z",
            "events": [
                {
                    "id": 1000 + order,
                    "order": order,
                    "name": f"A {order} - B {order}",
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


def test_detail_cache_records_hash_source_and_freshness(tmp_path):
    written = write_drawing_detail_cache(
        payload(),
        drawing_id=11970,
        cache_dir=tmp_path,
        fetched_at=NOW,
        source="test-network",
        allowed_root=tmp_path,
    )

    loaded = load_drawing_detail_cache(
        11970,
        cache_dir=tmp_path,
        now=NOW + timedelta(seconds=45),
        max_age_seconds=60,
        allowed_root=tmp_path,
    )

    assert loaded.payload == payload()
    assert loaded.payload_sha256 == written.payload_sha256
    assert loaded.source == "test-network"
    assert loaded.metadata_source == "sidecar"
    assert loaded.age_seconds == 45


def test_wrong_drawing_cache_is_rejected(tmp_path):
    (tmp_path / "drawing_11970.json").write_text(json.dumps(payload(99999)))

    with pytest.raises(ValueError, match="does not match"):
        load_drawing_detail_cache(
            11970,
            cache_dir=tmp_path,
            now=NOW,
            allowed_root=tmp_path,
        )


def test_missing_sidecar_is_rejected_even_for_fresh_raw_payload(tmp_path):
    write_drawing_detail_cache(
        payload(),
        drawing_id=11970,
        cache_dir=tmp_path,
        fetched_at=NOW,
        source="test-network",
        allowed_root=tmp_path,
    )
    (tmp_path / "drawing_11970.meta.json").unlink()

    with pytest.raises(ValueError, match="sidecar is missing"):
        load_drawing_detail_cache(
            11970,
            cache_dir=tmp_path,
            now=NOW,
            max_age_seconds=12 * 60 * 60,
            allowed_root=tmp_path,
        )


def test_torn_payload_sidecar_pair_is_rejected(tmp_path):
    write_drawing_detail_cache(
        payload(),
        drawing_id=11970,
        cache_dir=tmp_path,
        fetched_at=NOW,
        source="test-network",
        allowed_root=tmp_path,
    )
    changed = payload()
    changed["data"]["events"][0]["name"] = "Changed - Pair"
    (tmp_path / "drawing_11970.json").write_text(json.dumps(changed))

    with pytest.raises(ValueError, match="hash mismatch"):
        load_drawing_detail_cache(
            11970,
            cache_dir=tmp_path,
            now=NOW,
            allowed_root=tmp_path,
        )


def test_one_event_partial_detail_is_rejected_before_cache_write(tmp_path):
    partial = payload()
    partial["data"]["events"] = partial["data"]["events"][:1]

    with pytest.raises(ValueError, match="exactly 15"):
        write_drawing_detail_cache(
            partial,
            drawing_id=11970,
            cache_dir=tmp_path,
            fetched_at=NOW,
            source="test-network",
            allowed_root=tmp_path,
        )

    assert not (tmp_path / "drawing_11970.json").exists()


def test_detail_cache_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        write_drawing_detail_cache(
            payload(),
            drawing_id=11970,
            cache_dir=link,
            fetched_at=NOW,
            source="test-network",
            allowed_root=tmp_path,
        )
