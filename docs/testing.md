# Test suites

Pytest's project configuration excludes `heavy` tests by default. The default
suite is the release/CI safety gate and must remain practical for local use.
It validates quality-v2 contracts from small synthetic surfaces and frozen
golden artifacts; it does not rebuild `3**15` EV surfaces.

```bash
# Default local and release-CI command.
.venv/bin/pytest -q

# Static release checks.
.venv/bin/ruff check .
git diff --check
```

Multi-minute research validation is retained, not deleted. It includes the
three full frozen 4967/4969/4970 recomputations, the full bank-4,980 four-
sensitivity runtime build, and the real 4951 offline replay/pinning plus
scheduler prepare/final stale-pin pipeline.

```bash
# Opt-in/nightly heavy research suite only.
.venv/bin/pytest -q -o addopts='' -m heavy

# Every test, including fast and heavy.
.venv/bin/pytest -q -o addopts=''
```

The `research` marker describes non-release frozen/offline evidence. Every
currently heavy test is also research-oriented, but `heavy` alone controls
default exclusion. Heavy results are evidence of reproducibility and runtime,
not predictive quality or permission to wager.
