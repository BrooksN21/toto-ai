"""Bounded, visible invocation of the unchanged public production CLI."""

import json
import subprocess
import time
from pathlib import Path

root = Path("/Users/turshevr/toto-ai")
task = Path(__file__).resolve().parent
command = [
    str(root / ".venv/bin/python"),
    "-m",
    "toto_ai.cli",
    "morning-dispatch",
    "--bank",
    "4980",
    "--stake",
    "30",
    "--env-file",
    str(root / ".env"),
    "--project-root",
    str(root),
    "--state-root",
    str(root / "data/scheduler/morning-dispatch"),
    "--scheduler-root",
    str(root / "reports/rehearsal"),
    "--db",
    str(root / "data/toto.db"),
    "--aliases",
    str(
        root
        / "data/scheduler/morning-dispatch/preflight"
        / "drawing-12100-20260905T133000Z-fe49b1ba85febf3a"
        / "team-aliases-4997.json"
    ),
    "--expected-drawing-id",
    "12100",
    "--expected-drawing-number",
    "4997",
    "--expected-fingerprint",
    "fe49b1ba85febf3aa2a2929c8bb73dba6f81ef1f96361b29f92002a0f0ac5cb7",
    "--expected-deadline",
    "2026-09-05T13:30:00Z",
    "--schedule-evidence-ledger",
    str(root / "data/schedule-evidence/ledger.json"),
    "--api-sports-max-retries",
    "0",
    "--activate",
    "--goal-shadow-auto",
    "--parallel-challenger-auto",
]
record = (
    root
    / "data/scheduler/morning-dispatch"
    / "drawing-12100-20260905T133000Z-fe49b1ba85febf3a.json"
)
marker = task / "active-command.json"
with (
    (task / "production-prepare.stdout.log").open("w") as out,
    (task / "production-prepare.stderr.log").open("w") as err,
):
    process = subprocess.Popen(command, cwd=root, stdout=out, stderr=err)
    marker.write_text(
        json.dumps(
            {
                "owner": "01a06df7-2a47-7d02-b16d-56aaeee6ca14",
                "pid": process.pid,
                "status": "running",
                "command": command,
            },
            indent=2,
        )
        + "\n"
    )
    print("PRODUCTION PREPARE PID", process.pid, flush=True)
    started = time.monotonic()
    last_id = None
    while process.poll() is None:
        try:
            code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            code = None
        elapsed = time.monotonic() - started
        if record.exists():
            current = json.loads(record.read_text())
            if current.get("plan_id") and current["plan_id"] != last_id:
                last_id = current["plan_id"]
                print("NEW_PLAN", last_id, "PATH", current.get("plan_path"), flush=True)
        print(
            "progress",
            round(elapsed, 1),
            "seconds; pid",
            process.pid,
            "exit",
            code,
            flush=True,
        )
        if elapsed >= 360 and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            print("TIMEOUT: no automatic retry", flush=True)
            break
    marker.write_text(
        json.dumps(
            {
                "owner": "01a06df7-2a47-7d02-b16d-56aaeee6ca14",
                "pid": None,
                "status": "finished",
                "exit_code": process.returncode,
            },
            indent=2,
        )
        + "\n"
    )
    print("EXIT", process.returncode, flush=True)
