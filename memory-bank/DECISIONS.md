# Decisions

- Use repository memory instead of relying on chat memory.
- This memory bank is project-local to TotoAI and must never be mixed with
  local skills, personal knowledge bases, team knowledge bases, or unrelated
  external memory stores.
- Project knowledge is stored in repository directories:
  - `memory-bank/` for project state and durable decisions.
  - `knowledge/` for domain notes grounded in implemented repository state.
  - `skills/` for project-local workflow checklists.
  - `prompts/` for reusable project prompt templates.
- After every completed feature, update the project knowledge base first.
- One task, one commit, one verification cycle.
- Every hypothesis must be backtested.
- Never claim guaranteed profit.
- Separate prediction quality from cover quality.
- Budget-constrained oracle commands may use actual results only as benchmark
  upper bounds; they must not be treated as playable prediction methods.
- Budget-oracle must not reduce the candidate search space by default. Candidate
  limits only apply when explicitly requested.
- Budget-oracle drawing timeouts keep the best candidate found so far and should
  not fail the whole run.
- Category 13 means maximum Hamming distance 2.
- Category 14 means maximum Hamming distance 1.
- Category 15 means exact match.
- Cover guarantee only applies if actual outcomes are inside the selected brief.
- User bank can be any positive amount.
- `--open` means next playable drawing with `ended_at` in the future.
- `--live` means betting is closed and drawing is ongoing.
- `--latest-finished` is for historical analysis.
- Internal drawing ID differs from visible drawing number.
