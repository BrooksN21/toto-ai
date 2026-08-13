from __future__ import annotations

import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "postmortem"
    / "drawing_4973_unbound_package.json"
)


def test_drawing_4973_unbound_package_remains_non_actionable_regression():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert payload["drawing_number"] == 4973
    assert payload["classification"] == "unbound_post_t10_research_evidence"
    assert payload["actionable"] is False
    assert payload["scheduler_bound"] is False
    assert payload["archived"] is False
    assert payload["settled"] is False
    assert payload["created_at"] > payload["t_minus_10"]
    assert payload["package_bytes_sha256"] == (
        "0c223dd72250ea702e98b664444ecf6aef845958b8701d42bbdc1809623dbfbd"
    )
    assert sum(payload["hit_distribution"].values()) == payload["coupon_count"]
    assert payload["cost"] == payload["coupon_count"] * payload["stake"]
    assert payload["best_hits"] == 7
    assert payload["hit_10_plus"] == 0
    assert payload["hit_13_plus"] == 0
    assert payload["hit_14_plus"] == 0
    assert payload["hit_15"] == 0


def test_drawing_4973_canonical_paper_candidate_also_missed_all_prize_tiers():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    canonical = payload["canonical_quality_v2_paper_candidate"]

    assert canonical["top_level_decision"] == "NO BET"
    assert canonical["coupon_count"] == 166
    assert sum(canonical["hit_distribution"].values()) == 166
    assert canonical["best_hits"] == 8
    assert canonical["hit_10_plus"] == 0
    assert canonical["hit_13_plus"] == 0
