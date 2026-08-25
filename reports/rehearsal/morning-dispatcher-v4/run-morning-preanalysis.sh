#!/bin/sh
set -eu
umask 077
ENV_FILE=/Users/turshevr/toto-ai/.env
/Users/turshevr/toto-ai/.venv/bin/python - "$ENV_FILE" <<'PY'
import os
import stat
import sys
path = sys.argv[1]
try:
    metadata = os.lstat(path)
except OSError:
    raise SystemExit('scheduler env file is missing or inaccessible')
if stat.S_ISLNK(metadata.st_mode):
    raise SystemExit('scheduler env file must not be a symlink')
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit('scheduler env file must be a regular file')
if metadata.st_uid != os.getuid():
    raise SystemExit('scheduler env file must be owned by current user')
if stat.S_IMODE(metadata.st_mode) & ~0o600:
    raise SystemExit('scheduler env file mode must be no broader than 0600')
PY
. "$ENV_FILE"
if [ -z "${API_SPORTS_KEY:-}" ]; then
  echo 'API_SPORTS_KEY is required in scheduler env file' >&2
  exit 78
fi
export API_SPORTS_KEY
if [ -n "${THESPORTSDB_API_KEY:-}" ]; then
  export THESPORTSDB_API_KEY
fi
if [ -n "${THESPORTSDB_BASE_URL:-}" ]; then
  export THESPORTSDB_BASE_URL
fi
cd /Users/turshevr/toto-ai
attempt=0
while :; do
  if /Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli morning-dispatch --bank 4980 --stake 30 --env-file /Users/turshevr/toto-ai/.env --project-root /Users/turshevr/toto-ai --state-root /Users/turshevr/toto-ai/data/scheduler/morning-dispatch --scheduler-root /Users/turshevr/toto-ai/reports/rehearsal --db /Users/turshevr/toto-ai/data/toto.db --aliases /Users/turshevr/toto-ai/data/external-odds/team-aliases.json --raw-cache-dir /Users/turshevr/toto-ai/data/raw --totobrief-rate-state /Users/turshevr/toto-ai/data/totobrief-cache/request-state.json --cache-root /Users/turshevr/toto-ai/data/external-cache/api-sports --activate; then
    exit 0
  else
    status=$?
  fi
  if [ "$attempt" -ge 2 ]; then
    exit "$status"
  fi
  attempt=$((attempt + 1))
  /Users/turshevr/toto-ai/.venv/bin/python -c 'import time; time.sleep(60.0)'
done
