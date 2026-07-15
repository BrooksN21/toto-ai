from __future__ import annotations

import csv
from dataclasses import fields
from pathlib import Path

import pytest

from tests.test_external_odds_audit import _collection, _snapshot_session_factory
from toto_ai.external_odds.audit import CoverageMetrics, audit_external_coverage
from toto_ai.external_odds.reports import write_external_coverage_reports

FALLBACK_REASONS = (
    "fewer than 3 eligible bookmakers: stale prices",
    "fewer than 3 eligible bookmakers: missing outcomes",
    "fewer than 3 eligible bookmakers: duplicate bookmaker market",
    "fewer than 3 eligible bookmakers: not full-time three-way",
    "fewer than 3 eligible bookmakers: not regulation three-way",
    "fewer than 3 eligible bookmakers",
    "quota reserve reached",
    "provider odds failure: unavailable",
)


def test_disposition_csv_contains_all_15_rows_and_required_evidence(tmp_path):
    csv_path, _ = write_external_coverage_reports(_report_audit(), tmp_path)

    with csv_path.open(newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)

    disposition_rows = [row for row in rows if row["row_type"] == "disposition"]
    assert len(disposition_rows) == 15
    assert [int(row["event_order"]) for row in disposition_rows] == list(range(15))
    assert {
        "collection_id",
        "drawing_id",
        "drawing_number",
        "event_order",
        "sport",
        "league",
        "match_status",
        "provider_event_id",
        "probability_source",
        "eligible_bookmaker_count",
        "fallback_reason",
        "requests_made",
    } <= set(reader.fieldnames or ())
    assert [row["fallback_reason"] for row in disposition_rows[:8]] == [
        *FALLBACK_REASONS[:7],
        "provider odds failure",
    ]
    assert disposition_rows[5]["eligible_bookmaker_count"] == "2"
    assert disposition_rows[8]["provider_event_id"] == "provider-1-8"
    assert {row["requests_made"] for row in disposition_rows} == {"16"}


def test_aggregate_csv_has_complete_metrics_and_deterministic_scope_order(tmp_path):
    audit = _report_audit()
    csv_path, _ = write_external_coverage_reports(audit, tmp_path)

    with csv_path.open(newline="") as source:
        reader = csv.DictReader(source)
        aggregate_rows = [
            row for row in reader if row["row_type"] == "aggregate"
        ]

    metric_fields = {field.name for field in fields(CoverageMetrics)}
    assert metric_fields <= set(reader.fieldnames or ())
    assert all(
        all(row[field_name] != "" for field_name in metric_fields)
        for row in aggregate_rows
    )
    assert [(row["scope"], row["name"]) for row in aggregate_rows] == [
        ("overall", "all"),
        ("sport", "football"),
        ("sport", "hockey"),
        ("league", "League 0"),
        ("league", "League 1"),
        ("league", "League 2"),
        ("drawing", "5001"),
    ]
    overall = aggregate_rows[0]
    assert overall["consensus_1_count"] == "8"
    assert overall["consensus_2_count"] == "8"
    assert overall["consensus_3_count"] == "7"
    assert overall["usable_consensus_count"] == "7"
    assert overall["stale_count"] == "1"
    assert overall["semantic_count"] == "3"
    assert overall["incomplete_market_count"] == "1"
    assert overall["quota_count"] == "1"
    assert overall["provider_error_count"] == "1"
    assert overall["fallback_count"] == "8"


def test_markdown_contains_all_scope_metrics_thresholds_and_disclaimers(tmp_path):
    _, markdown_path = write_external_coverage_reports(_report_audit(), tmp_path)

    report = markdown_path.read_text()
    table_header = (
        "| Scope | Target | Explicit | Unique Match | Missing | Ambiguous | "
        "Unknown Sport | Consensus >=1 | Consensus >=2 | Consensus >=3 | "
        "Usable Consensus | Stale | Semantic | Incomplete Market | Quota | "
        "Provider Error | Fallback |"
    )
    for section in (
        "## Configuration",
        "## Provenance and Quota",
        "## Gate",
        "## Overall Metrics",
        "## Sport Metrics",
        "## League Metrics",
        "## Fallback Reason Counts",
        "## Drawing Metrics",
    ):
        assert section in report
    assert report.count(table_header) == 3
    assert "| football |" in report
    assert "| hockey |" in report
    assert "| League 0 |" in report
    assert "| 5001 |" in report
    assert "- gate sample floor: 30 drawings and 450 events" in report
    assert "- unique match threshold: 80%" in report
    assert "- usable consensus threshold: 70%" in report
    assert "- coverage is not probability quality" in report
    assert "- coverage is not profitability evidence" in report
    assert "- stale: 1" in report
    assert "- semantic: 3" in report
    assert "- incomplete market: 1" in report


def test_atomic_writer_restores_pair_and_cleans_temps_on_base_exception(
    monkeypatch,
    tmp_path,
):
    csv_path, markdown_path = write_external_coverage_reports(
        _report_audit(),
        tmp_path,
    )
    csv_path.write_bytes(b"previous csv\n")
    markdown_path.write_bytes(b"previous markdown\n")
    original_replace = Path.replace
    final_replace_count = 0

    def interrupt_second_final_replace(source, target):
        nonlocal final_replace_count
        if Path(target) in {csv_path, markdown_path}:
            final_replace_count += 1
            if final_replace_count == 2:
                raise KeyboardInterrupt("publication interrupted")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", interrupt_second_final_replace)

    with pytest.raises(KeyboardInterrupt, match="publication interrupted"):
        write_external_coverage_reports(_report_audit(), tmp_path)

    assert csv_path.read_bytes() == b"previous csv\n"
    assert markdown_path.read_bytes() == b"previous markdown\n"
    assert set(tmp_path.iterdir()) == {csv_path, markdown_path}


def test_repeat_write_is_byte_identical(tmp_path):
    audit = _report_audit()
    first_paths = write_external_coverage_reports(audit, tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first_paths)

    second_paths = write_external_coverage_reports(audit, tmp_path)

    assert tuple(path.read_bytes() for path in second_paths) == first_bytes


def _report_audit():
    return audit_external_coverage(
        _snapshot_session_factory(
            (
                _collection(
                    1,
                    FALLBACK_REASONS,
                    fallback_bookmaker_counts=(0, 0, 0, 0, 0, 2, 0, 0),
                ),
            )
        ),
        last=1,
        minimum_bookmakers=3,
    )
