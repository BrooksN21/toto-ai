"""Opt-in context-local cooperative deadlines; no default policy/candidate cuts."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class RuntimeDeadlineExceeded(TimeoutError):
    pass


@dataclass
class RuntimeBudget:
    deadline: float | None = None
    progress: Callable[[dict], None] | None = None
    started: float = field(default_factory=time.perf_counter)
    cpu_started: float = field(default_factory=time.process_time)
    phase: str = "validation"
    phase_started: float = field(default_factory=time.perf_counter)
    phase_cpu_started: float = field(default_factory=time.process_time)
    last_emitted: float = -math.inf
    counters: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.deadline is not None and not math.isfinite(self.deadline):
            raise ValueError("runtime deadline must be finite")

    def check(self, stage: str, *, force: bool = False, **counts) -> None:
        now, cpu = time.perf_counter(), time.process_time()
        expired = self.deadline is not None and now >= self.deadline
        self.counters.update(counts)
        if self.progress is not None and (
            force or expired or now - self.last_emitted >= 5
        ):
            self.progress(
                {
                    "phase": self.phase,
                    "stage": stage,
                    "wall_seconds": now - self.started,
                    "cpu_seconds": cpu - self.cpu_started,
                    "phase_wall_seconds": now - self.phase_started,
                    "phase_cpu_seconds": cpu - self.phase_cpu_started,
                    "remaining_seconds": (
                        None if self.deadline is None else max(0.0, self.deadline - now)
                    ),
                    "status": "DEADLINE_EXCEEDED" if expired else "RUNNING",
                    "counts": dict(self.counters),
                }
            )
            self.last_emitted = now
        if expired:
            raise RuntimeDeadlineExceeded(
                f"comparison deadline exceeded: {self.phase}/{stage}"
            )

    def enter(self, name: str) -> None:
        self.check("completed", force=True)
        self.phase = name
        self.phase_started, self.phase_cpu_started = (
            time.perf_counter(),
            time.process_time(),
        )
        self.counters = {}
        self.check("started", force=True)


_RUNTIME: ContextVar[RuntimeBudget | None] = ContextVar("ev_runtime", default=None)


def current_runtime() -> RuntimeBudget | None:
    return _RUNTIME.get()


def checkpoint(stage: str, **counts) -> None:
    budget = _RUNTIME.get()
    if budget is not None:
        budget.check(stage, **counts)


def phase(name: str) -> None:
    budget = _RUNTIME.get()
    if budget is not None:
        budget.enter(name)


@contextmanager
def runtime_scope(budget: RuntimeBudget) -> Iterator[RuntimeBudget]:
    parent = _RUNTIME.get()
    if parent is not None and parent.deadline is not None:
        budget.deadline = min(
            parent.deadline,
            budget.deadline if budget.deadline is not None else math.inf,
        )
    token = _RUNTIME.set(budget)
    try:
        yield budget
    finally:
        _RUNTIME.reset(token)
