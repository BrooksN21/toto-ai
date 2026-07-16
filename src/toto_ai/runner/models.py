"""Immutable runner configuration and pinned target records."""

import re
from dataclasses import dataclass

from toto_ai.ev.models import EVConfig, EVMode, validate_config_bank
from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint

_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class DrawingRunnerConfig:
    bank: int
    stake: int = 30
    mode: EVMode = "playable"
    final_lead_minutes: int = 20
    safety_stop_minutes: int = 5

    def __post_init__(self) -> None:
        validate_config_bank(self.bank, self.stake)
        if self.mode not in ("research", "playable"):
            raise ValueError("mode must be research or playable")
        _require_positive_int("final_lead_minutes", self.final_lead_minutes)
        _require_positive_int("safety_stop_minutes", self.safety_stop_minutes)
        if self.final_lead_minutes <= self.safety_stop_minutes:
            raise ValueError("final lead must be greater than safety stop")

    @property
    def ev_config(self) -> EVConfig:
        return EVConfig(bank=self.bank, stake=self.stake, mode=self.mode)


@dataclass(frozen=True)
class PinnedDrawing:
    target: TargetDrawing
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetDrawing):
            raise ValueError("target must be a TargetDrawing")
        if not isinstance(self.fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(
            self.fingerprint
        ):
            raise ValueError("fingerprint must be a lowercase SHA-256 hex digest")
        expected_fingerprint = target_fingerprint(
            self.target.drawing_id,
            self.target.drawing_number,
            self.target.deadline,
            self.target.events,
        )
        if self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match target")


def pin_drawing(target: TargetDrawing) -> PinnedDrawing:
    if not isinstance(target, TargetDrawing):
        raise ValueError("target must be a TargetDrawing")
    return PinnedDrawing(
        target=target,
        fingerprint=target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
    )


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
