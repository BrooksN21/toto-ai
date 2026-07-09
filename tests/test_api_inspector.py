import json

from toto_ai.analytics.api_inspector import (
    compare_raw_json_to_db_model,
    inspect_json_paths,
    save_raw_response,
)


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
