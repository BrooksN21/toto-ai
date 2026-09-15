"""Generated data stay local without hiding plans or unfinished source work."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD_PLAN = "plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906"
CURRENT_PLAN = "plans/TOTOAI-RESUME-20260915"


def is_ignored(path):
    result = subprocess.run(
        [str(ROOT / "scripts/project-git"), "check-ignore", "--no-index", "--stdin"],
        input=path + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=10,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return bool(result.stdout.strip())


@pytest.mark.parametrize(
    "path",
    [
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY/pytest/test_case0/toto.db",
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY02/focused-01-tmp/test_case0/data.json",
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY03/red-tmp/test_case0/result.json",
        f"{OLD_PLAN}/RUNTIME02_PUBLICATION_VERIFY/tmp-pytest/test_case0/run.sh",
        f"{OLD_PLAN}/OBSERVER03_PUBLICATION_VERIFY/tmp-focused/test_case0/result.json",
        "data/schedule-evidence/snapshots/example.raw",
        "data/schedule-evidence/.ledger.json.lock",
        "data/payout-evidence/4993/private-receipt.png",
        f"{CURRENT_PLAN}/source-captures/example.html",
        f"{CURRENT_PLAN}/history-source/drawing_12106.json",
        f"{CURRENT_PLAN}/prepare5007.stdout.log",
        f"{CURRENT_PLAN}/owner-consent5007.json",
        f"{CURRENT_PLAN}/cleanup-summary.json",
        f"{CURRENT_PLAN}/cleanup-remainder-private-scan.json",
        f"{OLD_PLAN}/4999-ledger-before-03a650359c57f727.json",
    ],
)
def test_generated_data_are_ignored(path):
    assert is_ignored(path)


@pytest.mark.parametrize(
    "path",
    [
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY02/before/src/example.py",
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY03/bootstrap/sitecustomize.py",
        f"{OLD_PLAN}/DELIVERY_OBSERVER_VERIFY03/test_independent_delivery.py",
        f"{OLD_PLAN}/CACHE_ATOMIC_CANDIDATE/src/example.py",
        f"{CURRENT_PLAN}/plan.md",
        f"{CURRENT_PLAN}/machinechecklist.json",
        f"{CURRENT_PLAN}/history-source/import-verification.json",
        f"{CURRENT_PLAN}/A-library-adoption.json",
        f"{CURRENT_PLAN}/C-data-feasibility.md",
        f"{CURRENT_PLAN}/cleanup-remainder-manifest.json",
        f"{OLD_PLAN}/runtime02/candidate/src/toto_ai/ev/package.py",
        "src/toto_ai/sports_stats/v3_probability.py",
        "tests/test_sports_v3_library_isolation.py",
        "memory-bank/ACTIVE_PLAN.md",
        "memory-bank/OPERATIONS_HANDOFF.md",
        "data/schedule-evidence/ledger.json",
        "data/schedule-evidence/reviews/example.md",
    ],
)
def test_source_plans_and_review_documents_remain_visible(path):
    assert not is_ignored(path)
