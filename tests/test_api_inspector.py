import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.api_inspector import (
    compare_raw_json_to_db_model,
    inspect_json_paths,
    resolve_drawing_reference,
    save_raw_response,
)
from toto_ai.db.models import Base, Drawing


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Drawing(
                    id=11935,
                    number=4938,
                    name="baltbet-main",
                    status="finished",
                ),
                Drawing(
                    id=11936,
                    number=4939,
                    name="baltbet-main",
                    status="active",
                    ended_at="2026-07-09T10:00:00Z",
                ),
                Drawing(
                    id=11937,
                    number=4940,
                    name="baltbet-main",
                    status="active",
                    ended_at="2026-07-09T11:00:00Z",
                ),
                Drawing(
                    id=11938,
                    number=4941,
                    name="baltbet-main",
                    status="expected",
                    ended_at="2026-07-09T13:00:00Z",
                ),
                Drawing(
                    id=11939,
                    number=4942,
                    name="baltbet-main",
                    status="active",
                    ended_at="2026-07-09T14:00:00Z",
                ),
                Drawing(
                    id=11934,
                    number=4937,
                    name="baltbet-main",
                    status="finished",
                ),
            ]
        )
        session.commit()
        yield session

    engine.dispose()


def sample_payload():
    return {
        "data": {
            "id": 4875,
            "number": 15,
            "name": "baltbet-main",
            "extra_field": "not stored",
            "events": [
                {
                    "id": 10,
                    "order": 0,
                    "name": "Team A - Team B",
                    "score": "2:1",
                    "result": "win_1",
                    "quotes": {
                        "pool_win_1": 0.5,
                        "pool_draw": 0.3,
                        "pool_win_2": 0.2,
                        "api_only_quote": 123,
                    },
                },
                {
                    "late_only": True,
                    "quotes": {
                        "late_quote": 7,
                    },
                },
            ],
        }
    }


def test_inspect_json_paths_flattens_nested_dicts_and_arrays():
    rows = inspect_json_paths(sample_payload())
    by_path = {row["path"]: row for row in rows}

    assert by_path["data"]["type"] == "object"
    assert by_path["data.id"] == {
        "path": "data.id",
        "type": "int",
        "sample": 4875,
    }
    assert by_path["data.events[]"]["type"] == "array"
    assert by_path["data.events[].id"] == {
        "path": "data.events[].id",
        "type": "int",
        "sample": 10,
    }
    assert by_path["data.events[].quotes.pool_win_1"] == {
        "path": "data.events[].quotes.pool_win_1",
        "type": "float",
        "sample": 0.5,
    }
    assert by_path["data.events[].late_only"] == {
        "path": "data.events[].late_only",
        "type": "bool",
        "sample": True,
    }
    assert by_path["data.events[].quotes.late_quote"] == {
        "path": "data.events[].quotes.late_quote",
        "type": "int",
        "sample": 7,
    }


def test_save_raw_response_writes_complete_json(tmp_path):
    path = save_raw_response(sample_payload(), drawing_id=4875, output_dir=tmp_path)

    assert path == tmp_path / "drawing_4875.json"
    assert json.loads(path.read_text()) == sample_payload()


def test_compare_raw_json_to_db_model_reports_unstored_and_missing_paths():
    diff = compare_raw_json_to_db_model(sample_payload())

    assert "data.extra_field" in diff["json_not_stored"]
    assert "data.events[].id" in diff["json_not_stored"]
    assert "data.events[].quotes.api_only_quote" in diff["json_not_stored"]
    assert "drawings.id" in diff["stored_fields"]
    assert "events.event_order" in diff["stored_fields"]
    assert "quotes.pool_win_1" in diff["stored_fields"]
    assert "data.status" in diff["missing_mappings"]
    assert "data.events[].sport" in diff["missing_mappings"]


def test_resolve_drawing_reference_by_number_uses_local_database(session):
    reference = resolve_drawing_reference(session, number=4938)

    assert reference.drawing_id == 11935
    assert reference.number == 4938
    assert reference.community == "baltbet-main"
    assert reference.status == "finished"


def test_resolve_drawing_reference_latest_finished_uses_latest_finished_baltbet(
    session,
):
    reference = resolve_drawing_reference(session, latest_finished=True)

    assert reference.drawing_id == 11935
    assert reference.number == 4938
    assert reference.community == "baltbet-main"
    assert reference.status == "finished"


def test_resolve_drawing_reference_live_uses_locked_active_or_expected_baltbet(session):
    reference = resolve_drawing_reference(
        session,
        live=True,
        now="2026-07-09T12:00:00Z",
    )

    assert reference.drawing_id == 11937
    assert reference.number == 4940
    assert reference.community == "baltbet-main"
    assert reference.status == "active"


def test_resolve_drawing_reference_open_uses_future_ended_playable_baltbet(session):
    reference = resolve_drawing_reference(
        session,
        open=True,
        now="2026-07-09T12:00:00Z",
    )

    assert reference.drawing_id == 11938
    assert reference.number == 4941
    assert reference.community == "baltbet-main"
    assert reference.status == "expected"


def test_resolve_drawing_reference_open_never_uses_past_ended_drawing(session):
    reference = resolve_drawing_reference(
        session,
        open=True,
        now="2026-07-09T13:30:00Z",
    )

    assert reference.drawing_id == 11939
    assert reference.ended_at == "2026-07-09T14:00:00Z"


def test_resolve_drawing_reference_requires_one_selector(session):
    with pytest.raises(ValueError, match="Use exactly one"):
        resolve_drawing_reference(session, live=True, open=True)


def test_resolve_drawing_reference_keeps_drawing_id_for_debugging(session):
    reference = resolve_drawing_reference(session, drawing_id=99999)

    assert reference.drawing_id == 99999
    assert reference.number is None
    assert reference.community is None
    assert reference.status is None
