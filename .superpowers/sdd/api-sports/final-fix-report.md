# API-Sports Final Review Fix Report

## Status

DONE

Final fix commit: created after this report is written; exact hash is reported
in the task final response.

## Findings Fixed

- Critical: collection consensus no longer evaluates provider markets against
  the earlier TotoBrief target fetch timestamp. It now computes an explicit
  external observation time at least as late as all consumed provider market
  fetch timestamps, stores that as collection `fetched_at`, and stores
  TotoBrief provenance separately as `target_fetched_at`.
- Important: API-Sports odds parsing accepts official-shaped item-level
  `update` timestamps as bookmaker defaults and preserves valid bookmaker-level
  overrides.
- Important: schedules and odds fetch every reported provider page with
  explicit `page` parameters. Inconsistent `paging.current` or `paging.total`
  fails closed.
- Important: market outcome labels are validated before `ProviderMarket`
  construction. Exactly one `Home`, `Draw`, and `Away` is required; duplicates
  or unknown extra labels fail closed.
- Minor required: `requests_made` now means actual HTTP attempts, including
  retries and pages. Cache hits are tracked, persisted, and reported separately.

## RED Evidence

Command:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api_sports_provider.py tests/test_external_odds_collection.py tests/test_external_odds_storage.py tests/test_external_odds_reports.py tests/test_external_odds_end_to_end.py -q
```

Result before implementation: `19 failed, 44 passed`.

Expected failures covered item-level update parsing, duplicate/unknown market
outcomes, two-page schedule/odds fetching, inconsistent pagination, missing
client request/cache counters, collection observation time, actual network
delta accounting, and new persisted/report fields.

## GREEN Evidence

Focused behavior wave:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api_sports_provider.py tests/test_external_odds_collection.py tests/test_external_odds_storage.py tests/test_external_odds_reports.py tests/test_external_odds_end_to_end.py -q
```

Result: `63 passed in 1.17s`.

Full external-odds focused suite:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_targets.py tests/test_external_event_matching.py tests/test_api_sports_provider.py tests/test_external_odds_consensus.py tests/test_external_odds_collection.py tests/test_external_odds_storage.py tests/test_external_odds_audit.py tests/test_external_odds_reports.py tests/test_external_odds_cli.py tests/test_external_odds_end_to_end.py -q
```

Result: `115 passed in 1.60s`.

Full suite:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest -q
```

Result: `641 passed in 7.70s`.

Ruff:

```bash
PYTHONPATH=src ../../.venv/bin/python -m ruff check .
```

Result: `All checks passed!`.

CLI help smokes:

```bash
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli collect-external-odds --help
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli audit-external-coverage --help
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli ev-package --help
```

Result: all exited zero.

Whitespace:

```bash
git diff --check
```

Result: exited zero.

## Self-Review

- No live network calls were added to tests.
- API keys remain header-only and sanitized; cache files still exclude secrets.
- EV/PLAY paths remain disconnected from external odds.
- Gate thresholds, three-bookmaker consensus, 36-hour maximum age, and exact
  15-event fallback behavior are unchanged.
- Exact duplicate paginated provider records are deduplicated only when the
  parsed provider-neutral records are identical. Conflicting duplicate schedule
  identifiers fail closed, and duplicate bookmaker markets remain
  consensus-ineligible rather than hidden.
- Schema additions are additive for the current append-only external odds
  tables: `target_fetched_at` and `cache_hits`.

## Concerns

- Existing SQLite databases created before this additive schema change will
  need table migration or recreation before writing new external collections.
  Repository tests create fresh SQLite schemas and remain deterministic.
