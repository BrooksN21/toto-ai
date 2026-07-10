# Agent Instructions

This repository has its own persistent project memory bank. It is local to the
TotoAI pet project and must never be mixed with local skills, personal
knowledge bases, team knowledge bases, or any other external memory source.

Before making changes:
- Read all files in `memory-bank/`.
- Treat `memory-bank/` as the source of project context for TotoAI.
- Do not use local skills, local knowledge bases, or unrelated memory stores as
  project memory for TotoAI.

Maintenance rules:
- Update `memory-bank/CURRENT_STATE.md` after every meaningful commit.
- Update `memory-bank/DECISIONS.md` when architecture or mathematical
  definitions change.
- Update `memory-bank/ROADMAP.md` when a phase or task is completed.
- Do not silently change category, cover, budget, or probability definitions.
- Run pytest and ruff before committing.
- Keep answers and implementation notes concise.
- Do not claim profitability without backtest evidence.
