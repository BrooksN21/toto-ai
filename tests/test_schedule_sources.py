from __future__ import annotations

from datetime import timedelta

import pytest

from tests.test_mixed_provider_preparation import (
    EVALUATED_AT,
    _catalog,
    _target,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.reviewed_schedule import (
    load_reviewed_schedule_catalog,
)
from toto_ai.external_odds.schedule_sources import (
    ReviewedCatalogScheduleSource,
    ScheduleSourceRegistry,
)
from toto_ai.external_odds.team_registry import DrawingEventPinRecord


class _Source:
    source_name = "source"

    def revalidate_pins(self, pins, *, target, evaluated_at):
        return ()


def _reviewed_pin(evidence_hash: str) -> DrawingEventPinRecord:
    target = _target()
    return DrawingEventPinRecord(
        id=1,
        drawing_id=target.drawing_id,
        drawing_fingerprint=target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
        target_event_id="5014",
        event_order=14,
        provider="api-sports",
        canonical_home_team_id=1,
        canonical_away_team_id=2,
        provider_home_team_id=None,
        provider_away_team_id=None,
        provider_fixture_id=None,
        starts_at="2026-07-29T18:00:00+00:00",
        collection_id=None,
        provenance={
            "evidence_id": "reviewed-evidence-1",
            "evidence_hash": evidence_hash,
        },
        pin_hash="p" * 64,
        status="valid",
        created_at=EVALUATED_AT.isoformat(),
        invalidated_at=None,
        invalidation_reason=None,
        pin_set_id="pinset",
        source_provider="reviewed-schedule",
        source_fixture_id=None,
        reviewed_evidence_id="reviewed-evidence-1",
        source_identity_hash="s" * 64,
        schedule_only=True,
    )


def test_schedule_source_registry_rejects_duplicate_and_unknown_sources():
    with pytest.raises(ValueError, match="unique"):
        ScheduleSourceRegistry((_Source(), _Source()))

    with pytest.raises(ValueError, match="unknown schedule source"):
        ScheduleSourceRegistry((_Source(),)).require("missing")


def test_reviewed_source_revalidates_exact_evidence_without_fixture_id(
    tmp_path,
):
    target = _target()
    catalog_path = _catalog(tmp_path, target)
    catalog = load_reviewed_schedule_catalog(
        catalog_path,
        evaluated_at=EVALUATED_AT,
        max_age=timedelta(hours=12),
    )
    source = ReviewedCatalogScheduleSource(
        catalog_path,
        expected_catalog_hash=catalog.semantic_hash,
    )

    result = source.revalidate_pins(
        (_reviewed_pin(catalog.records[0].semantic_hash),),
        target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert len(result) == 1
    assert result[0].matched is True
    assert result[0].identity_valid is True
    assert result[0].evidence_id == "reviewed-evidence-1"


def test_reviewed_source_fails_closed_when_snapshot_changes(tmp_path):
    target = _target()
    catalog_path = _catalog(tmp_path, target)
    catalog = load_reviewed_schedule_catalog(
        catalog_path,
        evaluated_at=EVALUATED_AT,
        max_age=timedelta(hours=12),
    )
    (tmp_path / "official.json").write_text("changed", encoding="utf-8")
    source = ReviewedCatalogScheduleSource(
        catalog_path,
        expected_catalog_hash=catalog.semantic_hash,
    )

    result = source.revalidate_pins(
        (_reviewed_pin(catalog.records[0].semantic_hash),),
        target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert len(result) == 1
    assert result[0].matched is False
    assert result[0].identity_valid is False
    assert "snapshot hash" in (result[0].reason or "")
