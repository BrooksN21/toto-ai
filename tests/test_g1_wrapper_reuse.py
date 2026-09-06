import shlex
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from toto_ai.sports_stats import final_hybrid_sidecar as sidecar


def fixture(monkeypatch, tmp_path):
    plan_path, sports, python = (
        tmp_path / n for n in ("plan.json", "sports.json", "python")
    )
    for path in (plan_path, sports, python):
        path.write_text("{}")
    plan = SimpleNamespace(
        project_root=tmp_path,
        output_dir=tmp_path / "scheduler",
        plan_id="a" * 16,
        operational_cutoff=datetime(2026, 9, 6, 15, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(sidecar, "load_scheduler_plan", lambda _: plan)
    monkeypatch.setattr(sidecar, "_validate_parallel_authorization", lambda *a: {})
    kwargs = dict(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports,
        python_command=python,
    )
    first = sidecar.prepare_parallel_sidecar_artifacts(**kwargs)
    return plan, kwargs, first


def command(path):
    return shlex.split(path.read_text().splitlines()[3][len("exec ") :])


def replace_command(path, tokens):
    lines = path.read_text().splitlines()
    lines[3] = "exec " + shlex.join(tokens)
    path.write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("migrate", [False, True])
@pytest.mark.parametrize("legacy_authorization", [False, True])
def test_reprepare_preserves_opt_in_and_frozen_input(
    monkeypatch, tmp_path, enabled, migrate, legacy_authorization
):
    plan, kwargs, first = fixture(monkeypatch, tmp_path)
    tokens = command(first.wrapper_path)
    if legacy_authorization:
        authorization = first.root / sidecar.PARALLEL_AUTHORIZATION_FILENAME
        authorization.write_text("{}")
        tokens += ["--parallel-authorization", str(authorization)]
    if enabled:
        tokens.append("--g1-refinement")
    replace_command(first.wrapper_path, tokens)
    if migrate:
        venv = tmp_path / ".venv/bin/python"
        venv.parent.mkdir(parents=True)
        venv.write_text("synthetic")
    later = tmp_path / "later-sports.json"
    later.write_text("{}")
    kwargs["sports_artifact_path"] = later
    plan_before = Path(kwargs["scheduler_plan_path"]).read_bytes()
    second = sidecar.prepare_parallel_sidecar_artifacts(**kwargs)
    first_reuse = second.wrapper_path.read_bytes()
    third = sidecar.prepare_parallel_sidecar_artifacts(**kwargs)
    final = command(third.wrapper_path)
    assert second.reused and third.reused
    assert final.count("--g1-refinement") == int(enabled)
    assert str(first.sports_artifact_path) in final and str(later) not in final
    assert "--parallel-authorization" not in final
    assert third.wrapper_path.read_bytes() == first_reuse
    assert Path(kwargs["scheduler_plan_path"]).read_bytes() == plan_before
    if migrate:
        assert final[0] == str(venv)


@pytest.mark.parametrize("position", [4, 8, 14])
def test_standalone_opt_in_is_accepted_between_option_pairs(
    monkeypatch, tmp_path, position
):
    _, kwargs, first = fixture(monkeypatch, tmp_path)
    tokens = command(first.wrapper_path)
    tokens.insert(position, "--g1-refinement")
    replace_command(first.wrapper_path, tokens)
    result = sidecar.prepare_parallel_sidecar_artifacts(**kwargs)
    assert command(result.wrapper_path).count("--g1-refinement") == 1


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_g1",
        "unknown_flag",
        "unknown_pair",
        "explicit_boolean_value",
        "duplicate_plan",
        "missing_value",
        "plan",
        "output",
        "wait",
        "runtime",
        "authorization",
        "sports_outside_project",
        "module",
    ],
)
def test_invalid_opt_in_or_other_binding_fails_closed(monkeypatch, tmp_path, fault):
    _, kwargs, first = fixture(monkeypatch, tmp_path)
    tokens = command(first.wrapper_path) + ["--g1-refinement"]
    if fault == "duplicate_g1":
        tokens.append("--g1-refinement")
    elif fault == "unknown_flag":
        tokens[-1] = "--g1-unknown"
    elif fault == "unknown_pair":
        tokens += ["--unknown", "value"]
    elif fault == "explicit_boolean_value":
        tokens.append("true")
    elif fault == "duplicate_plan":
        tokens += ["--scheduler-plan", str(kwargs["scheduler_plan_path"])]
    elif fault == "missing_value":
        tokens.remove("900")
    elif fault == "module":
        tokens[2] = "other.module"
    else:
        option = {
            "plan": "--scheduler-plan",
            "output": "--output-root",
            "wait": "--wait-seconds",
            "runtime": "--minimum-runtime-seconds",
            "sports_outside_project": "--sports-artifact",
        }.get(fault)
        if fault == "authorization":
            tokens += ["--parallel-authorization", str(tmp_path / "wrong-auth.json")]
        elif fault == "sports_outside_project":
            outside = tmp_path.parent / "outside-sports.json"
            outside.write_text("{}")
            tokens[tokens.index(option) + 1] = str(outside)
        else:
            tokens[tokens.index(option) + 1] = "wrong"
    replace_command(first.wrapper_path, tokens)
    protected = {
        p: p.read_bytes()
        for p in (
            first.wrapper_path,
            first.launch_agent_path,
            Path(kwargs["scheduler_plan_path"]),
        )
    }
    with pytest.raises(ValueError):
        sidecar.prepare_parallel_sidecar_artifacts(**kwargs)
    assert all(p.read_bytes() == before for p, before in protected.items())
