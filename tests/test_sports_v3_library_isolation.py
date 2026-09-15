"""Stage A: reviewed library imports are inert; production does not opt into V3."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "v3_probability",
    "v3_draw_calibration",
    "v3_probability_features",
    "v3_feature_disposition",
    "v3_f4",
    "v3_f4_gate",
    "v3_f4_metrics",
    "v3_generation",
    "v3_research_safety",
)

GUARDED_IMPORT = r"""
import importlib
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
modules = json.loads(sys.argv[2])
mode = sys.argv[3]
sys.path.insert(0, str(root / "src"))
sys.dont_write_bytecode = True
denied = []

def audit(event, args):
    blocked = event.startswith(("subprocess.", "os.exec", "os.spawn"))
    blocked |= event in {"os.system", "os.fork", "os.forkpty", "sqlite3.connect"}
    blocked |= event.startswith("socket.")
    if event == "open":
        path, mode, flags = args
        blocked |= (
            isinstance(path, (str, bytes))
            and Path(os.fsdecode(path)).name == ".env"
        )
        blocked |= isinstance(mode, str) and any(c in mode for c in "wax+")
        blocked |= isinstance(flags, int) and bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
    if blocked:
        denied.append(event)
        raise PermissionError("inert import forbids " + event)

sys.addaudithook(audit)
names = ["toto_ai.sports_stats." + name for name in modules]
if mode == "library":
    for name in names:
        module = importlib.import_module(name)
        expected = root / "src" / (name.replace(".", "/") + ".py")
        assert Path(module.__file__).resolve() == expected
    forbidden = {
        "toto_ai.cli", "toto_ai.runner.scheduler",
        "toto_ai.sports_stats.final_hybrid_comparison",
        "toto_ai.sports_stats.v3_parallel",
    }
    assert not forbidden.intersection(sys.modules), forbidden.intersection(sys.modules)
else:
    for name in (
        "toto_ai.cli", "toto_ai.runner.scheduler",
        "toto_ai.sports_stats.final_hybrid_comparison",
    ):
        importlib.import_module(name)
    loaded = set(names).intersection(sys.modules)
    assert not loaded, loaded
# urllib3 may probe IPv6 by opening a local socket during import. PermissionError
# denies that known capability probe; actual connect/bind/DNS/DB/write/spawn fails.
assert not [event for event in denied if event != "socket.__new__"], denied
print(json.dumps({"mode": mode, "inert": True, "denied": denied}))
"""


@pytest.mark.parametrize("name", MODULES)
def test_library_source_is_present_in_this_checkout(name):
    assert (ROOT / "src" / "toto_ai" / "sports_stats" / f"{name}.py").is_file()


@pytest.mark.parametrize("mode", ["library", "production"])
def test_guarded_import_does_not_activate_library_or_run_io(mode):
    import json

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            GUARDED_IMPORT,
            str(ROOT),
            json.dumps(MODULES),
            mode,
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        },
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["inert"] is True
