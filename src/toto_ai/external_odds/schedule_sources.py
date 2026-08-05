from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.reviewed_schedule import (
    REVIEWED_SCHEDULE_PROVIDER,
    revalidate_reviewed_catalog,
    select_reviewed_evidence,
)
from toto_ai.external_odds.team_registry import DrawingEventPinRecord


@dataclass(frozen=True)
class SchedulePinRevalidation:
    event_order: int
    source_provider: str
    matched: bool
    fresh: bool
    identity_valid: bool
    status_valid: bool
    evidence_id: str | None
    evidence_hash: str | None
    reason: str | None


class ScheduleSource(Protocol):
    source_name: str

    def revalidate_pins(
        self,
        pins: Sequence[DrawingEventPinRecord],
        *,
        target: TargetDrawing,
        evaluated_at: datetime,
    ) -> tuple[SchedulePinRevalidation, ...]: ...


class ScheduleSourceRegistry:
    def __init__(self, sources: Sequence[ScheduleSource]) -> None:
        names = tuple(source.source_name for source in sources)
        if len(set(names)) != len(names):
            raise ValueError("schedule source names must be unique")
        self._sources = dict(zip(names, sources, strict=True))

    def require(self, source_name: str) -> ScheduleSource:
        try:
            return self._sources[source_name]
        except KeyError as error:
            raise ValueError(f"unknown schedule source: {source_name}") from error


class ReviewedCatalogScheduleSource:
    source_name = REVIEWED_SCHEDULE_PROVIDER

    def __init__(
        self,
        catalog_path: Path,
        *,
        expected_catalog_hash: str,
        max_age: timedelta = timedelta(minutes=90),
    ) -> None:
        self._catalog_path = Path(catalog_path)
        self._expected_catalog_hash = expected_catalog_hash
        self._max_age = max_age

    def revalidate_pins(
        self,
        pins: Sequence[DrawingEventPinRecord],
        *,
        target: TargetDrawing,
        evaluated_at: datetime,
    ) -> tuple[SchedulePinRevalidation, ...]:
        selected = tuple(
            pin
            for pin in pins
            if pin.effective_source_provider == self.source_name
        )
        if not selected:
            return ()
        try:
            catalog = revalidate_reviewed_catalog(
                self._catalog_path,
                expected_catalog_hash=self._expected_catalog_hash,
                evaluated_at=evaluated_at,
                max_age=self._max_age,
            )
        except (OSError, TypeError, ValueError) as error:
            reason = str(error) or type(error).__name__
            return tuple(
                SchedulePinRevalidation(
                    event_order=pin.event_order,
                    source_provider=self.source_name,
                    matched=False,
                    fresh=False,
                    identity_valid=False,
                    status_valid=False,
                    evidence_id=pin.reviewed_evidence_id,
                    evidence_hash=None,
                    reason=reason,
                )
                for pin in selected
            )
        results = []
        for pin in selected:
            event = target.events[pin.event_order]
            try:
                evidence = select_reviewed_evidence(
                    catalog,
                    drawing_id=target.drawing_id,
                    drawing_number=target.drawing_number or 0,
                    target_fingerprint=pin.drawing_fingerprint,
                    event_order=pin.event_order,
                    target_event_id=event.event_id,
                )
                expected_hash = pin.provenance.get("evidence_hash")
                if pin.reviewed_evidence_id != evidence.evidence_id:
                    raise ValueError("reviewed evidence ID changed")
                if expected_hash != evidence.semantic_hash:
                    raise ValueError("reviewed evidence semantic hash changed")
                if (
                    pin.source_fixture_id is not None
                    or pin.provider_fixture_id is not None
                ):
                    raise ValueError("reviewed pin contains synthetic fixture identity")
                if pin.starts_at != evidence.starts_at.isoformat():
                    raise ValueError("reviewed fixture start changed")
                if evidence.starts_at < target.deadline:
                    raise ValueError("reviewed fixture starts before drawing deadline")
            except (IndexError, TypeError, ValueError) as error:
                results.append(
                    SchedulePinRevalidation(
                        event_order=pin.event_order,
                        source_provider=self.source_name,
                        matched=False,
                        fresh=True,
                        identity_valid=False,
                        status_valid=False,
                        evidence_id=pin.reviewed_evidence_id,
                        evidence_hash=None,
                        reason=str(error) or type(error).__name__,
                    )
                )
                continue
            results.append(
                SchedulePinRevalidation(
                    event_order=pin.event_order,
                    source_provider=self.source_name,
                    matched=True,
                    fresh=True,
                    identity_valid=True,
                    status_valid=True,
                    evidence_id=evidence.evidence_id,
                    evidence_hash=evidence.semantic_hash,
                    reason=None,
                )
            )
        return tuple(results)
