"""Invocation-scoped faulthandler diagnostics; no application or transport overrides."""
import atexit
import faulthandler
import os
from pathlib import Path
_root = Path(os.environ["TOTOAI_PREFLIGHT_DIAGNOSTIC_DIR"])
_fd = os.open(_root / ("python-stack-" + str(os.getpid()) + ".log"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
_stack_output = os.fdopen(_fd, "w")
faulthandler.dump_traceback_later(15, repeat=True, file=_stack_output)
atexit.register(faulthandler.cancel_dump_traceback_later)
