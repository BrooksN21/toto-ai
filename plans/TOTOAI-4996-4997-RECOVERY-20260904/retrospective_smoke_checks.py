"""Read-only production binding checks; never regenerate historical packages."""

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

RUNNER = (
    Path(__file__).resolve().parents[2]
    / "reports/research/4996-postmortem-automation/run-retrospective-12096.py"
)


def api_plan():
    api = runpy.run_path(str(RUNNER), run_name="retrospective_test")
    plan = api["load_plan"](RUNNER.with_name("retrospective-plan-12096.json"))
    return api, plan


def test_minimal_historical_smoke_fixture_is_now_rejected(tmp_path):
    api, plan = api_plan()
    report = {k: plan[k] for k in ("drawing_id", "drawing_number", "plan_id")}
    report.update(
        schema_version=2,
        quality_v2_reproduced_exactly=True,
        automatic_wagering=False,
        operator_compatible=False,
        strategies={n: {} for n in ("quality-v2", "sports-v2", "quality-v3", "robust")},
    )
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        api["validate_replay_report"](path, plan)


def test_complete_primary_uses_real_frozen_producer_binding():
    api, plan = api_plan()
    bindings = api["verify_bindings"](plan)
    state = api["validate_primary_state"](plan, bindings)
    assert state["status"] == "complete"
    assert (
        state["package_sha256"]
        == "f227a5374aba05c758a8d15cf4d4c06b8989f52cf54eced672c371a4d592b27d"
    )
    assert state["package_sha256"] != plan["issued_operator_package"]["package_sha256"]
    plan["primary_post_draw_plan_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="plan SHA-256"):
        api["validate_primary_state"](plan, bindings)


def test_current_report_idempotent_and_resigned_wrong_inputs_rejected(tmp_path):
    api, plan = api_plan()
    path = Path(plan["replay_output_dir"]) / "historical-hybrid-replay.json"
    original = path.read_bytes()
    for _ in range(2):
        report = api["validate_replay_report"](path, plan)
        assert path.read_bytes() == original
    report["inputs"]["final_input_sha256"] = "0" * 64
    report.pop("report_sha256")
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    bad = tmp_path / "stale.json"
    bad.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        api["validate_replay_report"](bad, plan)


def test_missing_report_fails_closed_without_regeneration(tmp_path, monkeypatch):
    api, plan = api_plan()
    plan["replay_output_dir"] = str(tmp_path / "missing")
    plan["status_file"] = str(tmp_path / "status.json")
    main = api["main"]
    g = main.__globals__
    monkeypatch.setitem(g, "load_plan", lambda _: plan)
    monkeypatch.setitem(
        g, "database_status", lambda *args: {"event_count": 15, "terminal_count": 15}
    )
    monkeypatch.setattr(sys, "argv", ["runner", "--plan", "unused"])
    assert main() == 1
    status = json.loads((tmp_path / "status.json").read_text())
    assert "regeneration requires exact-result-bound" in status["blocker"]
    assert not (tmp_path / "missing").exists()
