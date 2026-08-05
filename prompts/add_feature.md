# Add Feature Prompt

Use this prompt shape for TotoAI feature work.

```text
Implement <feature name>.

Requirements:
- Keep definitions from memory-bank/DECISIONS.md unchanged unless explicitly
  requested.
- Add focused tests.
- Update project knowledge first after the feature is completed:
  memory-bank/, knowledge/, skills/, or prompts/ as relevant.
- Run pytest and ruff.
- Commit with message: <message>
```

Related:
- [../skills/algorithm-review.md](../skills/algorithm-review.md)
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
