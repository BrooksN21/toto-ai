#!/bin/sh
set -eu

ROOT="/Users/turshevr/toto-ai"
cd "$ROOT"

python -B plans/TOTO-FULL-HISTORY-DATA-AUDIT/audit_full_history.py
sqlite3 -readonly -header -csv data/toto.db \
  < plans/TOTO-FULL-HISTORY-DATA-AUDIT/queries.sql \
  > plans/TOTO-FULL-HISTORY-DATA-AUDIT/queries-output.txt
