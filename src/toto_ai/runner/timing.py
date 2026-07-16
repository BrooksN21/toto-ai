"""UTC-only runner timing state machine."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Literal

from toto_ai.runner.models import DrawingRunnerConfig

RunnerWindow = Literal["waiting", "final", "closed"]


@dataclass(frozen=True)
class RunnerSchedule:
    deadline: datetime
    final_starts_at: datetime
    safety_stops_at: datetime

    def __post_init__(self) -> None:
        _require_utc_datetime("deadline", self.deadline)
        _require_utc_datetime("final_starts_at", self.final_starts_at)
        _require_utc_datetime("safety_stops_at", self.safety_stops_at)
        if not self.final_starts_at < self.safety_stops_at < self.deadline:
            raise ValueError(
                "final_starts_at must be before safety_stops_at and deadline"
            )


def build_runner_schedule(
    deadline: datetime, config: DrawingRunnerConfig
) -> RunnerSchedule:
    _require_utc_datetime("deadline", deadline)
    if not isinstance(config, DrawingRunnerConfig):
        raise ValueError("config must be a DrawingRunnerConfig")
    return RunnerSchedule(
        deadline=deadline,
        final_starts_at=deadline - timedelta(minutes=config.final_lead_minutes),
        safety_stops_at=deadline - timedelta(minutes=config.safety_stop_minutes),
    )


def runner_window(schedule: RunnerSchedule, now: datetime) -> RunnerWindow:
    if not isinstance(schedule, RunnerSchedule):
        raise ValueError("schedule must be a RunnerSchedule")
    _require_utc_datetime("now", now)
    if now < schedule.final_starts_at:
        return "waiting"
    if now < schedule.safety_stops_at:
        return "final"
    return "closed"


def wait_for_final_window(
    schedule: RunnerSchedule,
    now: Callable[[], datetime],
    sleep: Callable[[float], object],
    progress_callback: Callable[[dict[str, str | float]], object] | None = None,
    maximum_sleep_seconds: float = 30.0,
) -> Literal["final", "closed"]:
    maximum_sleep = _require_positive_finite_seconds(maximum_sleep_seconds)

    while True:
        current_time = now()
        phase = runner_window(schedule, current_time)
        if phase != "waiting":
            return phase

        seconds_until_final = (
            schedule.final_starts_at - current_time
        ).total_seconds()
        sleep_seconds = min(maximum_sleep, seconds_until_final)
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "waiting",
                    "seconds_until_final": seconds_until_final,
                    "sleep_seconds": sleep_seconds,
                }
            )
        sleep(sleep_seconds)


def _require_utc_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _require_positive_finite_seconds(value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
        or value <= 0
    ):
        raise ValueError("maximum_sleep_seconds must be finite and positive")
    return float(value)
