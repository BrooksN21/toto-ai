from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest

from toto_ai.external_odds.domain import TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.runner import (
    DrawingRunnerConfig,
    PinnedDrawing,
    RunnerSchedule,
    build_runner_schedule,
    pin_drawing,
    runner_window,
    wait_for_final_window,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 16, 15, tzinfo=UTC)
T_MINUS_21 = DEADLINE - timedelta(minutes=21)
T_MINUS_20 = DEADLINE - timedelta(minutes=20)


def _target(*, fetched_at: datetime = T_MINUS_21) -> TargetDrawing:
    events = tuple(
        TargetEvent(
            drawing_id=11953,
            drawing_number=4945,
            event_id=1000 + event_order,
            event_order=event_order,
            sport="football",
            championship="Test Championship",
            starts_at=DEADLINE + timedelta(hours=event_order),
            deadline=DEADLINE,
            home_team=f"Home {event_order}",
            away_team=f"Away {event_order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.2, 0.3, 0.5),
        )
        for event_order in range(15)
    )
    return TargetDrawing(
        drawing_id=11953,
        drawing_number=4945,
        deadline=DEADLINE,
        fetched_at=fetched_at,
        events=events,
    )


def _schedule() -> RunnerSchedule:
    return build_runner_schedule(DEADLINE, DrawingRunnerConfig(bank=4980, stake=30))


def test_runner_config_is_immutable_and_exposes_playable_ev_config():
    config = DrawingRunnerConfig(bank=4980, stake=30)

    assert config.ev_config.bank == 4980
    assert config.ev_config.stake == 30
    assert config.ev_config.mode == "playable"
    with pytest.raises(AttributeError):
        config.bank = 6000


@pytest.mark.parametrize("bank", [True, False, 4980.0, 0, -30, 5000])
def test_runner_config_rejects_invalid_bank(bank):
    with pytest.raises(ValueError):
        DrawingRunnerConfig(bank=bank)


@pytest.mark.parametrize("stake", [True, False, 30.0, 0, -30])
def test_runner_config_rejects_invalid_stake(stake):
    with pytest.raises(ValueError):
        DrawingRunnerConfig(bank=4980, stake=stake)


@pytest.mark.parametrize("mode", ["", "PLAYABLE", "invalid", True, None])
def test_runner_config_rejects_invalid_mode(mode):
    with pytest.raises(ValueError, match="mode"):
        DrawingRunnerConfig(bank=4980, mode=mode)


@pytest.mark.parametrize("value", [True, False, 20.0, 0, -1])
def test_runner_config_rejects_invalid_final_lead_minutes(value):
    with pytest.raises(ValueError, match="final_lead_minutes"):
        DrawingRunnerConfig(bank=4980, final_lead_minutes=value)


@pytest.mark.parametrize("value", [True, False, 5.0, 0, -1])
def test_runner_config_rejects_invalid_safety_stop_minutes(value):
    with pytest.raises(ValueError, match="safety_stop_minutes"):
        DrawingRunnerConfig(bank=4980, safety_stop_minutes=value)


@pytest.mark.parametrize(("final_lead", "safety_stop"), [(5, 5), (4, 5)])
def test_runner_config_requires_final_lead_after_safety_stop(final_lead, safety_stop):
    with pytest.raises(ValueError, match="final lead"):
        DrawingRunnerConfig(
            bank=4980,
            final_lead_minutes=final_lead,
            safety_stop_minutes=safety_stop,
        )


def test_pin_drawing_uses_deterministic_target_fingerprint_without_fetch_time():
    target = _target()
    later_target = replace(target, fetched_at=target.fetched_at + timedelta(seconds=1))

    first = pin_drawing(target)
    second = pin_drawing(later_target)

    assert first == PinnedDrawing(
        target=target,
        fingerprint=target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
    )
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize("fingerprint", ["", "a" * 63, "A" * 64, "g" * 64, 123])
def test_pinned_drawing_rejects_malformed_fingerprint(fingerprint):
    with pytest.raises(ValueError, match="fingerprint"):
        PinnedDrawing(target=_target(), fingerprint=fingerprint)


def test_pinned_drawing_requires_a_target_drawing():
    with pytest.raises(ValueError, match="target"):
        PinnedDrawing(target=object(), fingerprint="a" * 64)


def test_build_runner_schedule_uses_utc_deadline_and_exact_offsets():
    config = DrawingRunnerConfig(
        bank=4980,
        final_lead_minutes=20,
        safety_stop_minutes=5,
    )

    schedule = build_runner_schedule(DEADLINE, config)

    assert schedule == RunnerSchedule(
        deadline=DEADLINE,
        final_starts_at=DEADLINE - timedelta(minutes=20),
        safety_stops_at=DEADLINE - timedelta(minutes=5),
    )


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 7, 16, 15),
        datetime(2026, 7, 16, 18, tzinfo=timezone(timedelta(hours=3))),
    ],
)
def test_schedule_and_window_reject_non_utc_datetimes(value):
    with pytest.raises(ValueError, match="UTC"):
        build_runner_schedule(value, DrawingRunnerConfig(bank=4980))
    with pytest.raises(ValueError, match="UTC"):
        runner_window(_schedule(), value)


def test_runner_schedule_rejects_inconsistent_boundaries():
    with pytest.raises(ValueError, match="final_starts_at"):
        RunnerSchedule(
            deadline=DEADLINE,
            final_starts_at=DEADLINE,
            safety_stops_at=DEADLINE - timedelta(minutes=5),
        )


def test_runner_window_uses_exact_t20_and_t5_boundaries():
    config = DrawingRunnerConfig(bank=4980, stake=30)
    schedule = build_runner_schedule(DEADLINE, config)

    assert runner_window(schedule, DEADLINE - timedelta(minutes=21)) == "waiting"
    assert runner_window(schedule, DEADLINE - timedelta(minutes=20)) == "final"
    assert (
        runner_window(schedule, DEADLINE - timedelta(minutes=5, microseconds=1))
        == "final"
    )
    assert runner_window(schedule, DEADLINE - timedelta(minutes=5)) == "closed"


def test_wait_rechecks_wall_clock_and_never_sleeps_past_final_window():
    schedule = _schedule()
    times = iter((T_MINUS_21, T_MINUS_20))
    sleeps = []
    updates = []

    result = wait_for_final_window(
        schedule,
        now=lambda: next(times),
        sleep=sleeps.append,
        progress_callback=updates.append,
        maximum_sleep_seconds=60.0,
    )

    assert result == "final"
    assert sleeps == [60.0]
    assert updates[0]["phase"] == "waiting"


def test_wait_clamps_sleep_to_the_final_window_boundary():
    schedule = _schedule()
    times = iter((DEADLINE - timedelta(minutes=20, seconds=30), T_MINUS_20))
    sleeps = []

    result = wait_for_final_window(
        schedule,
        now=lambda: next(times),
        sleep=sleeps.append,
        maximum_sleep_seconds=60.0,
    )

    assert result == "final"
    assert sleeps == [30.0]


def test_wait_rechecks_wall_clock_after_sleep_and_stops_closed():
    schedule = _schedule()
    times = iter((T_MINUS_21, DEADLINE - timedelta(minutes=5)))
    sleeps = []

    result = wait_for_final_window(
        schedule,
        now=lambda: next(times),
        sleep=sleeps.append,
        maximum_sleep_seconds=60.0,
    )

    assert result == "closed"
    assert sleeps == [60.0]


@pytest.mark.parametrize("current_time", [T_MINUS_20, DEADLINE - timedelta(minutes=5)])
def test_wait_does_not_sleep_when_already_final_or_closed(current_time):
    sleeps = []

    assert (
        wait_for_final_window(
            _schedule(),
            now=lambda: current_time,
            sleep=sleeps.append,
        )
        == ("final" if current_time == T_MINUS_20 else "closed")
    )
    assert sleeps == []


@pytest.mark.parametrize("maximum_sleep_seconds", [0, -1.0, nan, inf])
def test_wait_rejects_non_positive_or_non_finite_maximum_sleep(maximum_sleep_seconds):
    with pytest.raises(ValueError, match="maximum_sleep_seconds"):
        wait_for_final_window(
            _schedule(),
            now=lambda: T_MINUS_20,
            sleep=lambda _: None,
            maximum_sleep_seconds=maximum_sleep_seconds,
        )
