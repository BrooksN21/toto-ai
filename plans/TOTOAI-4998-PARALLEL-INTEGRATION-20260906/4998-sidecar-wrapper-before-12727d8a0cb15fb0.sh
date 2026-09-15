#!/bin/zsh
set -eu
cd /Users/turshevr/toto-ai
exec /Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli run-final-goal-hybrid-sidecar --scheduler-plan /Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json --sports-artifact /Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/sports-seed/sports_probability_shadow_4998_08da2cb616e108b8.json --output-root /Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/output --wait-seconds 900 --minimum-runtime-seconds 240
