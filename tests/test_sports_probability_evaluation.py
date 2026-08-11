from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.sports_stats.evaluation import (
    ShadowEvaluationRecord,
    evaluate_shadow_records,
)

UTC = timezone.utc


def _record(
    index: int,
    *,
    event_order: int = 0,
    actual: str = "1",
    bk=(0.45, 0.30, 0.25),
    sports=(0.60, 0.25, 0.15),
    blend=(0.55, 0.27, 0.18),
    sports_used: bool = True,
    validation_failures=(),
):
    return ShadowEvaluationRecord(
        drawing_id=100 + index,
        drawing_number=5000 + index,
        event_order=event_order,
        as_of=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        actual=actual,
        bk_probabilities=bk,
        sports_probabilities=sports,
        candidate_blend_probabilities=blend,
        sports_used=sports_used,
        fallback_reason=None if sports_used else "sports_history_missing",
        validation_failures=validation_failures,
    )


def test_evaluator_reports_three_models_and_remains_not_activated():
    result = evaluate_shadow_records(
        tuple(
            _record(index, event_order=event_order)
            for index in range(30)
            for event_order in range(15)
        ),
        minimum_drawings=30,
        minimum_events=450,
        minimum_sports_coverage=0.70,
        calibration_tolerance=0.02,
    )

    assert result.status == "NOT_ACTIVATED"
    assert result.drawing_count == 30
    assert result.event_count == 450
    assert result.sports_coverage_count == 450
    assert result.fallback_count == 0
    assert result.metrics["candidate_blend"].log_loss < result.metrics["bk"].log_loss
    assert result.metrics["candidate_blend"].brier < result.metrics["bk"].brier
    assert result.activation_gate.passed is True
    assert result.activation_gate.status == "PASS_REVIEW_REQUIRED"


def test_activation_gate_fails_closed_for_small_or_invalid_sample():
    records = tuple(
        _record(index, event_order=event_order)
        for index in range(2)
        for event_order in range(15)
    )
    records += (
        _record(
            2,
            sports_used=False,
            validation_failures=("drawing_fingerprint_mismatch",),
        ),
    )

    result = evaluate_shadow_records(
        records,
        minimum_drawings=30,
        minimum_events=450,
        minimum_sports_coverage=0.70,
        calibration_tolerance=0.02,
    )

    assert result.status == "NOT_ACTIVATED"
    assert result.activation_gate.passed is False
    assert "minimum_drawings_not_met" in result.activation_gate.reasons
    assert "minimum_events_not_met" in result.activation_gate.reasons
    assert "validation_failure" in result.activation_gate.reasons


@pytest.mark.parametrize(
    "overrides",
    (
        {"minimum_drawings": 29},
        {"minimum_events": 449},
        {"minimum_sports_coverage": 0.699},
        {"minimum_sports_coverage": float("nan")},
        {"minimum_sports_coverage": 1.001},
        {"calibration_tolerance": 0.0201},
    ),
)
def test_activation_policy_cannot_be_weakened(overrides):
    with pytest.raises(ValueError, match="activation policy"):
        evaluate_shadow_records((_record(1),), **overrides)


def test_ordinary_missing_sports_data_is_coverage_fallback_not_integrity_failure():
    records = tuple(
        _record(index, event_order=event_order)
        for index in range(30)
        for event_order in range(15)
    )
    ordinary_fallback = _record(0, event_order=0, sports_used=False)

    result = evaluate_shadow_records((ordinary_fallback, *records[1:]))

    assert result.fallback_count == 1
    assert result.validation_failure_count == 0
    assert "validation_failure" not in result.activation_gate.reasons


@pytest.mark.parametrize(
    "failure",
    (
        "source_after_as_of",
        "orientation_mismatch",
        "orientation_missing",
        "drawing_fingerprint_mismatch",
        "authoritative_target_unavailable",
    ),
)
def test_event_integrity_fallback_blocks_activation(failure):
    records = tuple(
        _record(index, event_order=event_order)
        for index in range(30)
        for event_order in range(15)
    )
    bad = _record(
        0,
        event_order=0,
        sports_used=False,
        validation_failures=(failure,),
    )
    records = (bad, *records[1:])

    result = evaluate_shadow_records(records)

    assert result.activation_gate.passed is False
    assert "validation_failure" in result.activation_gate.reasons


def test_chronology_is_strict_and_future_or_duplicate_events_are_rejected():
    first = _record(1)
    duplicate = _record(1)

    try:
        evaluate_shadow_records((first, duplicate))
    except ValueError as error:
        assert "duplicate drawing/event" in str(error)
    else:
        raise AssertionError("duplicate chronological event was accepted")
