"""Pure synthetic reviewed captures; numerical 90-minute and scope contracts."""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from toto_ai.sports_stats import v3_probability_features as adapter

_spec = importlib.util.spec_from_file_location(
    "o1_test_fixtures", Path(__file__).with_name("test_sports_v3_family_evidence.py")
)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


def inputs(*, scoped=True, status="AFTER_PEN", bad_ft=False, late=False):
    target = fixtures._target()
    scope = {"gender": "male", "age_group": "adult", "squad_type": "first"}
    target.update(
        scope={s: scope if scoped else {} for s in ("home", "away")},
        league_id=101,
        season=2019,
    )
    sources = {}
    for side in ("home", "away"):
        rows = [
            fixtures._match(
                side,
                identity=f"{side}-{i}",
                kickoffUtc=f"2020-02-{10 + i:02}T12:00:00+00:00",
                matchStatus=status,
                homeTeamScore="7",
                awayTeamScore="4",
                homeTeamFtScore=None if bad_ft else "1",
                awayTeamFtScore="1",
                **scope,
            )
            for i in range(3)
        ]
        sources[side] = [
            fixtures._source(
                side,
                rows,
                **({"fetched_at": "2020-02-20T12:00:00+00:00"} if late else {}),
            )
        ]
    result = fixtures._inputs(target, sources)
    result.pop("cutoff_evidence")
    return dict(
        **result,
        drawing_number=10,
        bk_probabilities=[0.4, 0.3, 0.3],
        deadline="2020-02-20T18:00:00+00:00",
    )


def test_reuses_28_features_with_regulation_scores_and_separate_o1_lineage():
    row = adapter.build_v3_predictors(**inputs())
    assert row["features"]["home_rolling_ppg"] == 1.0
    assert row["features"]["home_rolling_goals_for_per_game"] == 1.0
    assert row["features"]["home_recency_ppg"] == 1.0
    assert row["features"]["home_independent_opponent_ppg"] is None
    assert row["features"]["home_standings_rank"] is None
    assert row["scope_verified"] is True
    assert row["o1_lineage_hash"]
    assert row["o1_strict_eligibility"] is False
    assert row["evaluation_authorized"] is False
    assert row == adapter.build_v3_predictors(**inputs())


def test_missing_ft_is_not_reconstructed_and_finished_retains_score():
    bad = adapter.build_v3_predictors(**inputs(bad_ft=True))
    assert bad["prior_counts"] == [0, 0]
    assert bad["features"]["home_rolling_ppg"] is None
    assert any("REGULATION_SCORE" in reason for reason in bad["missing_reasons"])
    finished = adapter.build_v3_predictors(**inputs(status="FINISHED", bad_ft=True))
    assert finished["features"]["home_rolling_goals_for_per_game"] == 7


def test_unknown_scope_and_late_source_do_not_promote_o1():
    unknown = adapter.build_v3_predictors(**inputs(scoped=False))
    assert unknown["scope_verified"] is False
    late = adapter.build_v3_predictors(**inputs(late=True))
    assert late["source_rejected"] is True
    assert any("post-as_of" in reason for reason in late["missing_reasons"])


def test_unreviewed_or_tampered_target_is_rejected():
    arguments = inputs()
    with pytest.raises(ValueError, match="reviewed reference"):
        adapter.build_v3_predictors(**{**arguments, "reviewed_refs": ()})
    event = arguments["event"]
    with pytest.raises(ValueError, match="binding"):
        adapter.build_v3_predictors(
            **{**arguments, "event": type(event)(event.path, event.content + b" ")}
        )


@pytest.mark.parametrize("status", ["AFTER_ET", "AFTER_PEN"])
@pytest.mark.parametrize("bad", [None, "", True, -1, 1.5, "1-1", [], {}])
def test_ambiguous_ft_never_uses_aggregate(status, bad):
    with pytest.raises(ValueError):
        adapter.regulation_score(
            {
                "matchStatus": status,
                "homeTeamFtScore": bad,
                "awayTeamFtScore": "0",
                "homeTeamScore": "9",
                "awayTeamScore": "1",
            }
        )


def test_raw_train_artifact_infer_end_to_end():
    from toto_ai.sports_stats import v3_probability as v3

    def derived(draw, order):
        base = inputs(status="FINISHED")
        target = fixtures.json.loads(base["event"].content)
        target.update(
            event_order=order,
            target_event_id=f"{draw}-{order}",
            drawing_id=900000 + draw,
        )
        for key in ("as_of", "kickoff", "final_captured_at"):
            target[key] = (
                datetime.fromisoformat(target[key]) + timedelta(days=draw)
            ).isoformat()
        sources = {}
        for side in ("home", "away"):
            rows = []
            for i in range(3):
                rows.append(
                    fixtures._match(
                        side,
                        identity=f"{side}-{i}",
                        homeTeamScore=order % 3,
                        kickoffUtc=f"2020-02-{10 + i:02}T12:00:00+00:00",
                        **target["scope"][side],
                    )
                )
            sources[side] = [fixtures._source(side, rows, fetched_at=target["as_of"])]
        arguments = fixtures._inputs(target, sources)
        arguments.pop("cutoff_evidence")
        return adapter.build_v3_predictors(
            **arguments,
            drawing_number=draw,
            bk_probabilities=[0.4, 0.3, 0.3],
            deadline=target["kickoff"],
        )

    records = []
    for draw in (1, 2, 3):
        for order in range(15):
            row = derived(draw, order)
            records.append(
                {
                    "features": row,
                    "label": {
                        "drawing_number": draw,
                        "event_id": row["event_id"],
                        "outcome": order % 3,
                        "snapshot_sha256": "c" * 64,
                        "available_at": (
                            datetime.fromisoformat(row["kickoff"]) + timedelta(hours=3)
                        ).isoformat(),
                    },
                }
            )
    target = derived(10, 2)
    model = v3.train_v3(
        records, target_drawing=10, prediction_as_of=target["as_of"], variant="A4"
    )
    result = v3.infer_v3(v3.load_model(v3.canonical_json(model)), target)
    assert model["status"] == "TRAINED_EXPERIMENTAL"
    assert result["status"] == "PREDICTED_EXPERIMENTAL"
    assert result["probabilities"] != target["bk_probabilities"]
    assert (
        result["reliability"] < 0.2
    )  # Unknown independent histories/standings retained.


def test_consistent_duplicate_captures_preserve_earliest_availability():
    first = {
        "event_id": "same",
        "kickoff": datetime.fromisoformat("2020-01-01T00:00:00+00:00"),
        "home_goals": 1,
        "available_at": datetime.fromisoformat("2020-01-02T00:00:00+00:00"),
    }
    second = {
        **first,
        "available_at": datetime.fromisoformat("2020-01-03T00:00:00+00:00"),
    }
    assert adapter._merge([second, first]) == [first]
    with pytest.raises(ValueError, match="conflicting"):
        adapter._merge([first, {**second, "home_goals": 2}])
