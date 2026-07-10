# Decisions

- Use repository memory instead of relying on chat memory.
- This memory bank is project-local to TotoAI and must never be mixed with
  local skills, personal knowledge bases, team knowledge bases, or unrelated
  external memory stores.
- One task, one commit, one verification cycle.
- Every hypothesis must be backtested.
- Never claim guaranteed profit.
- Separate prediction quality from cover quality.
- Category 13 means maximum Hamming distance 2.
- Category 14 means maximum Hamming distance 1.
- Category 15 means exact match.
- Cover guarantee only applies if actual outcomes are inside the selected brief.
- User bank can be any positive amount.
- `--open` means next playable drawing with `ended_at` in the future.
- `--live` means betting is closed and drawing is ongoing.
- `--latest-finished` is for historical analysis.
- Internal drawing ID differs from visible drawing number.
