# API-Sports Coverage Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prospectively measure whether API-Sports' free football and hockey odds can provide safe three-way probabilities for BaltBet events while retaining an explicit TotoBrief BK fallback for every event.

**Architecture:** A provider-neutral domain layer parses one fresh 15-event TotoBrief drawing. An API-Sports adapter fetches cached schedules and event odds under a quota reserve; deterministic matching and strict market validation produce append-only per-event dispositions. A separate read-only audit aggregates stored evidence and atomically publishes coverage reports. The accepted EV pipeline remains unchanged until a later ensemble design passes the prospective gate.

**Tech Stack:** Python 3.12, dataclasses, `requests`, SQLAlchemy 2, SQLite, Typer/Rich, pytest, Ruff.

## Global Constraints

- The provider budget is zero; do not add a paid dependency or subscription requirement.
- Read the API key only from `API_SPORTS_KEY`; redact it from errors, storage, and reports.
- Never scrape bookmaker or score websites and never access Pinnacle directly.
- Never silently omit one of the 15 TotoBrief events.
- Only football full-time and hockey regulation-time complete `1/X/2` markets are eligible.
- Ambiguous, missing, partial, stale, or semantically unknown external data must use an explicit TotoBrief BK fallback disposition.
- External probabilities must not affect `ev-package` or `PLAY` in this plan.
- Require three eligible bookmakers for consensus and use a 36-hour maximum odds age.
- Do not make live network access a repository test dependency.
- Update project memory after each completed feature and run full pytest and Ruff before every commit.

---

## File Structure

- `src/toto_ai/external_odds/domain.py`: immutable provider-neutral records and validation.
- `src/toto_ai/external_odds/targets.py`: strict TotoBrief target parsing and sport classification.
- `src/toto_ai/external_odds/api_sports.py`: API-Sports HTTP, quota, cache, and response parsing.
- `src/toto_ai/external_odds/matching.py`: deterministic event normalization and matching.
- `src/toto_ai/external_odds/consensus.py`: market semantics, rejection, de-vig, and consensus.
- `src/toto_ai/external_odds/storage.py`: append-only SQLAlchemy persistence and read queries.
- `src/toto_ai/external_odds/collection.py`: 15-event collection orchestration and fallback guarantees.
- `src/toto_ai/external_odds/audit.py`: stored-snapshot coverage metrics and GO/STOP gate.
- `src/toto_ai/external_odds/reports.py`: deterministic atomic CSV/Markdown reports.
- `src/toto_ai/db/models.py`: external collection, event disposition, and bookmaker quote tables.
- `src/toto_ai/cli.py`: `collect-external-odds` and `audit-external-coverage` commands.

---

### Task 1: Provider-Neutral Domain and TotoBrief Targets

**Files:**
- Create: `src/toto_ai/external_odds/__init__.py`
- Create: `src/toto_ai/external_odds/domain.py`
- Create: `src/toto_ai/external_odds/targets.py`
- Test: `tests/test_external_odds_targets.py`

**Interfaces:**
- Consumes: a fresh `drawing-info` mapping from `TotoBriefClient`.
- Produces: `TargetDrawing`, `TargetEvent`, `ProviderEvent`, `ProviderMarket`, `QuotaState`, `ExternalOddsProvider`, `parse_target_drawing(payload, fetched_at)`, and `classify_sport(championship, explicit_sport)`.

- [ ] **Step 1: Write failing validation and parsing tests**

```python
def test_fresh_payload_becomes_fifteen_ordered_targets():
    drawing = parse_target_drawing(payload(), fetched_at="2026-07-14T12:00:00Z")
    assert drawing.drawing_id == 9000
    assert tuple(event.event_order for event in drawing.events) == tuple(range(15))
    assert drawing.events[0].starts_at.isoformat() == "2026-07-14T18:00:00+00:00"
    assert drawing.events[0].home_team == "Бавария"
    assert drawing.events[0].away_team == "ПСЖ"
    assert drawing.events[0].bk_probabilities == pytest.approx((0.60, 0.18, 0.22))


def test_unknown_sport_is_explicit_and_not_guessed():
    assert classify_sport("Неизвестный турнир", None) == "unknown"


def test_payload_requires_exactly_fifteen_unique_orders_and_aware_times():
    data = payload()
    data["data"]["events"].pop()
    with pytest.raises(ValueError, match="exactly 15"):
        parse_target_drawing(data, fetched_at="2026-07-14T12:00:00Z")
```

- [ ] **Step 2: Run the target tests and confirm RED**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_targets.py -q`

Expected: collection fails because `toto_ai.external_odds.targets` does not exist.

- [ ] **Step 3: Implement strict immutable domain records**

```python
OutcomeTriplet = tuple[float, float, float]
Sport = Literal["football", "hockey", "unknown"]


@dataclass(frozen=True)
class TargetEvent:
    drawing_id: int
    drawing_number: int | None
    event_id: int
    event_order: int
    sport: Sport
    championship: str
    starts_at: datetime
    deadline: datetime
    home_team: str
    away_team: str
    home_team_en: str | None
    away_team_en: str | None
    bk_probabilities: OutcomeTriplet


@dataclass(frozen=True)
class TargetDrawing:
    drawing_id: int
    drawing_number: int | None
    deadline: datetime
    fetched_at: datetime
    events: tuple[TargetEvent, ...]


@dataclass(frozen=True)
class ProviderMarket:
    provider: str
    provider_event_id: str
    bookmaker_id: str
    market_name: str
    updated_at: datetime
    fetched_at: datetime
    payload_hash: str
    home_price: float | None
    draw_price: float | None
    away_price: float | None


@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    provider_event_id: str
    sport: Sport
    league: str
    starts_at: datetime
    home_team: str
    away_team: str
    fetched_at: datetime
    payload_hash: str
    markets: tuple[ProviderMarket, ...] = ()


@dataclass(frozen=True)
class QuotaState:
    daily_limit: int | None
    daily_remaining: int | None
    minute_limit: int | None
    minute_remaining: int | None


class ExternalOddsProvider(Protocol):
    provider_name: str

    @property
    def quota_state(self) -> QuotaState:
        raise NotImplementedError

    def fetch_schedule(
        self, sport: Sport, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        raise NotImplementedError

    def fetch_event_markets(
        self, sport: Sport, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        raise NotImplementedError
```

Validate aware UTC times, non-empty identifiers/names, event orders `0..14`, finite positive BK values normalized to one, and finite decimal prices when present.

- [ ] **Step 4: Implement TotoBrief target parsing and sport rules**

```python
HOCKEY_CHAMPIONSHIP_TOKENS = (
    "кхл", "вхл", "мхл", "nhl", "ahl", "shl", "liiga",
    "del", "hockey", "хоккей",
)


def classify_sport(championship: str, explicit_sport: object) -> Sport:
    explicit = str(explicit_sport or "").strip().casefold()
    if explicit in {"football", "футбол", "soccer"}:
        return "football"
    if explicit in {"hockey", "хоккей", "ice hockey"}:
        return "hockey"
    normalized = unicodedata.normalize("NFKC", championship).casefold()
    if any(token in normalized for token in HOCKEY_CHAMPIONSHIP_TOKENS):
        return "hockey"
    if championship.strip():
        return "football"
    return "unknown"
```

`parse_target_drawing()` must read TotoBrief's `start_at`, split `name` and an
optional `name_en` on one of `—`, `–`, or ` - `, reject an unsplittable primary
name, sort by `order`, and preserve normalized TotoBrief BK probabilities for
fallback.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_targets.py -q
PYTHONPATH=src ../../.venv/bin/python -m pytest -q
PYTHONPATH=src ../../.venv/bin/python -m ruff check .
```

Expected: all commands exit zero.

- [ ] **Step 6: Update memory and commit**

Update `memory-bank/ARCHITECTURE.md` and `memory-bank/CURRENT_STATE.md`, then run:

```bash
git add src/toto_ai/external_odds tests/test_external_odds_targets.py memory-bank
git commit -m "Add external odds domain"
```

---

### Task 2: API-Sports Transport, Parsing, Cache, and Quota

**Files:**
- Create: `src/toto_ai/external_odds/api_sports.py`
- Test: `tests/test_api_sports_provider.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `TargetDrawing`, `Sport`, injected `requests.Session`, and `API_SPORTS_KEY`.
- Produces: `APISportsClient`, `APISportsError`, `QuotaExhausted`, `fetch_schedule(sport, dates)`, and `fetch_event_markets(sport, provider_event_id)`.

- [ ] **Step 1: Write failing transport contract tests**

```python
def test_client_requires_key_before_network_call(fake_session, tmp_path):
    with pytest.raises(ValueError, match="API_SPORTS_KEY"):
        APISportsClient(api_key="", session=fake_session, cache_dir=tmp_path)
    assert fake_session.calls == []


def test_schedule_response_is_cached_and_key_is_never_serialized(
    fake_session, tmp_path
):
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)
    first = client.fetch_schedule("football", (date(2026, 7, 14),))
    second = client.fetch_schedule("football", (date(2026, 7, 14),))
    assert first == second
    assert len(fake_session.calls) == 1
    assert "secret-key" not in "".join(path.read_text() for path in tmp_path.iterdir())


def test_quota_reserve_stops_before_request(fake_session, tmp_path):
    client = APISportsClient(
        "secret-key", session=fake_session, cache_dir=tmp_path, quota_reserve=5
    )
    client.set_quota_for_test(QuotaState(100, 5, 10, 10))
    with pytest.raises(QuotaExhausted):
        client.fetch_event_markets("hockey", "42")
    assert fake_session.calls == []
```

- [ ] **Step 2: Run the provider tests and confirm RED**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api_sports_provider.py -q`

Expected: import failure for `APISportsClient`.

- [ ] **Step 3: Implement sanitized HTTP and deterministic cache keys**

```python
FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
HOCKEY_BASE_URL = "https://v1.hockey.api-sports.io"


class APISportsClient:
    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache_dir: Path = Path("data/external-cache/api-sports"),
        quota_reserve: int = 10,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key.strip():
            raise ValueError("API_SPORTS_KEY is required")
        if quota_reserve < 0:
            raise ValueError("quota_reserve must be non-negative")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._cache_dir = cache_dir
        self._quota_reserve = quota_reserve
        self._timeout = timeout
        self._max_retries = max_retries
```

Use `x-apisports-key` only in request headers. Cache canonical response JSON by SHA-256 of host, path, and sorted query parameters. Store neither request headers nor URLs containing credentials. Retry only connection errors, HTTP 408, 429, and 5xx with bounded deterministic delays; convert final failures to sanitized `APISportsError`.

- [ ] **Step 4: Implement football and hockey parsers**

Map football fixtures and hockey games into `ProviderEvent`; preserve official event IDs, UTC dates, league names, and home/away names. Parse odds into `ProviderMarket` without deciding eligibility. Reject invalid top-level `errors`, paging, timestamp, price, or identifier shapes with `APISportsError`.

Read response headers into `QuotaState`:

```python
def quota_from_headers(headers: Mapping[str, str]) -> QuotaState:
    return QuotaState(
        daily_limit=_optional_int(headers.get("x-ratelimit-requests-limit")),
        daily_remaining=_optional_int(headers.get("x-ratelimit-requests-remaining")),
        minute_limit=_optional_int(headers.get("x-ratelimit-limit")),
        minute_remaining=_optional_int(headers.get("x-ratelimit-remaining")),
    )
```

- [ ] **Step 5: Ignore only raw external cache files**

Add `data/external-cache/` to `.gitignore`. Do not ignore coverage reports or test fixtures globally.

- [ ] **Step 6: Verify and commit**

Run focused tests, full pytest, and Ruff. Update `memory-bank/CURRENT_STATE.md`, then:

```bash
git add .gitignore src/toto_ai/external_odds/api_sports.py tests/test_api_sports_provider.py memory-bank/CURRENT_STATE.md
git commit -m "Add API-Sports odds provider"
```

---

### Task 3: Deterministic Fail-Closed Event Matching

**Files:**
- Create: `src/toto_ai/external_odds/matching.py`
- Create: `data/external-odds/team-aliases.json`
- Test: `tests/test_external_event_matching.py`

**Interfaces:**
- Consumes: `TargetEvent`, sequence of `ProviderEvent`, and versioned aliases.
- Produces: `MatchDecision`, `MatchSuggestion`, `MatchStatus`, `load_aliases(path)`, `normalize_team_name(name)`, `suggest_matches(target, candidates, aliases)`, and `match_event(target, candidates, aliases)`.

- [ ] **Step 1: Write failing exact/missing/ambiguous/reversed tests**

```python
def test_exact_unique_match_is_accepted(target, provider_event):
    result = match_event(target, [provider_event], aliases={})
    assert result.status == "matched"
    assert result.provider_event_id == provider_event.provider_event_id


def test_ambiguous_and_reversed_matches_are_never_consumed(target):
    ambiguous = match_event(target, [candidate("a"), candidate("b")], aliases={})
    reversed_result = match_event(target, [reversed_candidate("c")], aliases={})
    assert ambiguous.status == "ambiguous"
    assert ambiguous.provider_event_id is None
    assert reversed_result.status == "missing"


def test_time_outside_three_hours_is_missing(target, provider_event):
    late = dataclasses.replace(
        provider_event, starts_at=target.starts_at + timedelta(hours=3, seconds=1)
    )
    assert match_event(target, [late], aliases={}).status == "missing"


def test_fuzzy_suggestion_never_authorizes_a_match(target, provider_event):
    suggestion = suggest_matches(target, [provider_event], aliases={})[0]
    decision = match_event(target, [provider_event], aliases={})
    assert suggestion.provider_event_id == provider_event.provider_event_id
    assert 0.0 <= suggestion.score <= 1.0
    assert decision.status == "missing"
```

- [ ] **Step 2: Run the matcher tests and confirm RED**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_event_matching.py -q`

- [ ] **Step 3: Implement canonical normalization and versioned aliases**

```python
MATCHER_VERSION = "api-sports-v1"
MAX_START_DELTA = timedelta(hours=3)


def normalize_team_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())
```

`team-aliases.json` starts as `{"version": 1, "aliases": {}}`. `load_aliases()` validates exact schema, normalized unique keys, non-empty normalized values, and rejects cycles. Aliases are applied after normalization and never learned automatically.

`suggest_matches()` uses `difflib.SequenceMatcher` only after sport and time
filtering. It scores home and away separately, sorts by descending mean score
then provider event ID, and returns at most five `MatchSuggestion` records. The
scores appear in diagnostics only. Exact matching compares provider names with
the primary target names, optional `name_en` alternatives, and reviewed aliases.

- [ ] **Step 4: Implement fail-closed matching**

```python
@dataclass(frozen=True)
class MatchDecision:
    status: Literal["matched", "missing", "ambiguous", "unknown_sport"]
    provider_event_id: str | None
    matcher_version: str
    candidate_ids: tuple[str, ...]
    reason: str


def match_event(
    target: TargetEvent,
    candidates: Sequence[ProviderEvent],
    aliases: Mapping[str, str],
) -> MatchDecision:
    if target.sport == "unknown":
        return MatchDecision("unknown_sport", None, MATCHER_VERSION, (), "unknown sport")
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.sport == target.sport
        and abs(candidate.starts_at - target.starts_at) <= MAX_START_DELTA
        and _canonical(candidate.home_team, aliases) == _canonical(target.home_team, aliases)
        and _canonical(candidate.away_team, aliases) == _canonical(target.away_team, aliases)
    )
    if len(matches) == 1:
        return MatchDecision("matched", matches[0].provider_event_id, MATCHER_VERSION, (matches[0].provider_event_id,), "unique exact match")
    status = "missing" if not matches else "ambiguous"
    return MatchDecision(status, None, MATCHER_VERSION, tuple(sorted(item.provider_event_id for item in matches)), f"{len(matches)} exact candidates")
```

League similarity may appear only in diagnostic reasons; it cannot turn a non-match into a match.

- [ ] **Step 5: Verify and commit**

Run focused tests, full pytest, and Ruff. Update project memory, then commit:

```bash
git add src/toto_ai/external_odds/matching.py data/external-odds/team-aliases.json tests/test_external_event_matching.py memory-bank
git commit -m "Add deterministic external event matching"
```

---

### Task 4: Strict Market Semantics and Consensus

**Files:**
- Create: `src/toto_ai/external_odds/consensus.py`
- Test: `tests/test_external_odds_consensus.py`

**Interfaces:**
- Consumes: matched `TargetEvent`, provider markets, collection time, `minimum_bookmakers=3`, and `maximum_age=36h`.
- Produces: `BookmakerAssessment`, `ConsensusResult`, `assess_market()`, `devig_decimal_prices()`, and `build_consensus()`.

- [ ] **Step 1: Write failing semantic and arithmetic tests**

```python
def test_devig_matches_hand_calculation():
    result = devig_decimal_prices((2.0, 4.0, 4.0))
    assert result == pytest.approx((0.5, 0.25, 0.25))


def test_hockey_two_way_moneyline_is_rejected(hockey_target):
    market = provider_market(name="Home/Away", draw_price=None)
    result = assess_market(hockey_target, market, fetched_at=aware_now())
    assert result.eligible is False
    assert result.rejection_reason == "not regulation three-way"


def test_three_book_median_consensus_is_normalized(football_target):
    result = build_consensus(football_target, three_valid_markets(), aware_now())
    assert result.eligible_bookmaker_count == 3
    assert sum(result.probabilities) == pytest.approx(1.0)
    assert result.fallback_reason is None


def test_two_books_produce_explicit_fallback(football_target):
    result = build_consensus(football_target, two_valid_markets(), aware_now())
    assert result.probabilities is None
    assert result.fallback_reason == "fewer than 3 eligible bookmakers"
```

- [ ] **Step 2: Run consensus tests and confirm RED**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_consensus.py -q`

- [ ] **Step 3: Implement market eligibility**

Normalize API-Sports market names to a small explicit allow-list:

```python
FOOTBALL_THREE_WAY = frozenset({"match winner", "1x2", "home draw away"})
HOCKEY_REGULATION_THREE_WAY = frozenset({
    "home draw away", "match winner regulation time", "1x2 regulation time"
})
MAXIMUM_ODDS_AGE = timedelta(hours=36)
```

Reject unknown market names, absent outcomes, duplicate bookmaker/market records, prices `<= 1`, non-finite prices, future update timestamps, and age above 36 hours. Do not infer settlement semantics from outcome count alone.

- [ ] **Step 4: Implement de-vig and robust median consensus**

```python
def devig_decimal_prices(prices: tuple[float, float, float]) -> OutcomeTriplet:
    inverse = tuple(1.0 / price for price in prices)
    total = math.fsum(inverse)
    return tuple(value / total for value in inverse)  # type: ignore[return-value]


def build_consensus(
    target: TargetEvent,
    markets: Sequence[ProviderMarket],
    fetched_at: datetime,
    *,
    minimum_bookmakers: int = 3,
) -> ConsensusResult:
    assessments = tuple(assess_market(target, item, fetched_at) for item in markets)
    eligible = tuple(item for item in assessments if item.eligible)
    if len(eligible) < minimum_bookmakers:
        return ConsensusResult(None, len(eligible), assessments, f"fewer than {minimum_bookmakers} eligible bookmakers")
    medians = tuple(statistics.median(item.probabilities[index] for item in eligible) for index in range(3))
    total = math.fsum(medians)
    probabilities = tuple(value / total for value in medians)
    return ConsensusResult(probabilities, len(eligible), assessments, None)
```

- [ ] **Step 5: Verify and commit**

Run focused tests, full pytest, and Ruff. Update `knowledge/expected_value.md` with the consensus assumption and commit:

```bash
git add src/toto_ai/external_odds/consensus.py tests/test_external_odds_consensus.py knowledge/expected_value.md memory-bank
git commit -m "Add external odds consensus"
```

---

### Task 5: Append-Only Storage and 15-Event Collection

**Files:**
- Modify: `src/toto_ai/db/models.py`
- Create: `src/toto_ai/external_odds/storage.py`
- Create: `src/toto_ai/external_odds/collection.py`
- Test: `tests/test_external_odds_storage.py`
- Test: `tests/test_external_odds_collection.py`

**Interfaces:**
- Consumes: `TargetDrawing`, `APISportsClient`, aliases, matcher, consensus builder, and writable SQLAlchemy session factory.
- Produces: `ExternalCollectionRun`, `ExternalEventDisposition`, `ExternalBookmakerQuote`, `build_external_collection(target, provider, aliases)`, `collect_open_external_odds(totobrief_client, provider, session_factory, aliases, fetched_at)`, `save_collection()`, and `load_latest_complete_collections()`.

- [ ] **Step 1: Write failing schema, idempotency, and completeness tests**

```python
def test_collection_persists_exactly_fifteen_dispositions(session_factory):
    result = build_external_collection(target_drawing(), fake_provider(), aliases={})
    save_collection(session_factory, result)
    stored = load_latest_complete_collections(session_factory, last=1)
    assert len(stored) == 1
    assert len(stored[0].events) == 15
    assert tuple(row.event_order for row in stored[0].events) == tuple(range(15))


def test_same_canonical_inputs_are_idempotent(session_factory):
    result = complete_collection()
    save_collection(session_factory, result)
    save_collection(session_factory, result)
    assert count_runs(session_factory) == 1


def test_provider_failure_falls_back_for_every_remaining_event():
    result = build_external_collection(target_drawing(), failing_provider(), aliases={})
    assert len(result.events) == 15
    assert all(row.probability_source == "totobrief_bk_fallback" for row in result.events)
    assert all(row.fallback_reason for row in result.events)
```

- [ ] **Step 2: Run storage and collection tests and confirm RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_storage.py tests/test_external_odds_collection.py -q
```

- [ ] **Step 3: Add append-only SQLAlchemy tables**

Add models with exact uniqueness constraints:

```python
class ExternalCollectionRun(Base):
    __tablename__ = "external_collection_runs"
    collection_id: Mapped[str] = mapped_column(String, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[str] = mapped_column(String)
    deadline: Mapped[str] = mapped_column(String)
    event_count: Mapped[int] = mapped_column(Integer)
    requests_made: Mapped[int] = mapped_column(Integer)
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    daily_remaining: Mapped[int | None] = mapped_column(Integer)
    minute_remaining: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)


class ExternalEventDisposition(Base):
    __tablename__ = "external_event_dispositions"
    __table_args__ = (UniqueConstraint("collection_id", "event_order", name="uq_external_collection_event"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[str] = mapped_column(String, index=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    event_order: Mapped[int] = mapped_column(Integer)
    target_event_id: Mapped[int] = mapped_column(Integer)
    sport: Mapped[str] = mapped_column(String)
    championship: Mapped[str] = mapped_column(String)
    starts_at: Mapped[str] = mapped_column(String)
    home_team: Mapped[str] = mapped_column(String)
    away_team: Mapped[str] = mapped_column(String)
    home_team_en: Mapped[str | None] = mapped_column(String)
    away_team_en: Mapped[str | None] = mapped_column(String)
    match_status: Mapped[str] = mapped_column(String)
    provider_event_id: Mapped[str | None] = mapped_column(String)
    matcher_version: Mapped[str] = mapped_column(String)
    probability_source: Mapped[str] = mapped_column(String)
    probability_1: Mapped[float] = mapped_column(Float)
    probability_x: Mapped[float] = mapped_column(Float)
    probability_2: Mapped[float] = mapped_column(Float)
    eligible_bookmaker_count: Mapped[int] = mapped_column(Integer)
    odds_age_hours: Mapped[float | None] = mapped_column(Float)
    fallback_reason: Mapped[str | None] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)


class ExternalBookmakerQuote(Base):
    __tablename__ = "external_bookmaker_quotes"
    __table_args__ = (UniqueConstraint("collection_id", "event_order", "bookmaker_id", "market_name", name="uq_external_book_quote"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[str] = mapped_column(String, index=True)
    event_order: Mapped[int] = mapped_column(Integer)
    bookmaker_id: Mapped[str] = mapped_column(String)
    market_name: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    home_price: Mapped[float | None] = mapped_column(Float)
    draw_price: Mapped[float | None] = mapped_column(Float)
    away_price: Mapped[float | None] = mapped_column(Float)
    eligible: Mapped[int] = mapped_column(Integer)
    rejection_reason: Mapped[str | None] = mapped_column(String)
```

New tables are created by existing `init_db()` and require no destructive migration.

- [ ] **Step 4: Implement deterministic collection orchestration**

`build_external_collection()` must:

1. fetch each required sport/date schedule once;
2. match all 15 targets before odds requests;
3. fetch odds only for unique matches while honoring cache and quota reserve;
4. build consensus or retain the target BK triplet with an exact fallback reason;
5. return all 15 ordered dispositions even after provider or quota failure;
6. compute `collection_id` as SHA-256 of canonical drawing identity, fetched-at timestamp, target payload, provider payload hashes, matching decisions, and consensus configuration;
7. set run status `complete` only when all 15 dispositions exist.

Use one `session_factory.begin()` transaction in `save_collection()`. If the deterministic `collection_id` already exists, verify stored canonical content and return without inserting. Reject conflicting content under the same ID.

`collect_open_external_odds()` must resolve the nearest open drawing with
`resolve_open_drawing_from_api()`, fetch exactly that `drawing_info`, call
`parse_target_drawing()`, build the collection, and save it only after all 15
event dispositions exist. It returns the immutable collection result.

- [ ] **Step 5: Verify and commit**

Run focused tests, full pytest, and Ruff. Update architecture, data notes, current state, and decisions; then:

```bash
git add src/toto_ai/db/models.py src/toto_ai/external_odds/storage.py src/toto_ai/external_odds/collection.py tests/test_external_odds_storage.py tests/test_external_odds_collection.py memory-bank
git commit -m "Store prospective external odds"
```

---

### Task 6: Coverage Audit, Atomic Reports, and CLI

**Files:**
- Create: `src/toto_ai/external_odds/audit.py`
- Create: `src/toto_ai/external_odds/reports.py`
- Modify: `src/toto_ai/cli.py`
- Test: `tests/test_external_odds_audit.py`
- Test: `tests/test_external_odds_reports.py`
- Test: `tests/test_external_odds_cli.py`

**Interfaces:**
- Consumes: complete stored collections only.
- Produces: `CoverageAudit`, `CoverageGate`, `audit_external_coverage()`, `write_external_coverage_reports()`, and both approved CLI commands.

- [ ] **Step 1: Write failing metric and gate tests**

```python
def test_gate_requires_all_registered_thresholds():
    audit = audit_from_counts(
        drawings=30, events=450, unique_matches=360, usable_consensus=315,
        consumed_ambiguous=0, explicit_dispositions=450, operational_failures=0,
    )
    assert audit.gate.decision == "GO"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"unique_matches": 359}, "unique match rate below 80%"),
        ({"usable_consensus": 314}, "consensus coverage below 70%"),
        ({"consumed_ambiguous": 1}, "ambiguous match consumed"),
        ({"explicit_dispositions": 449}, "silent event loss"),
    ],
)
def test_gate_fails_closed(change, reason):
    values = {
        "drawings": 30,
        "events": 450,
        "unique_matches": 360,
        "usable_consensus": 315,
        "consumed_ambiguous": 0,
        "explicit_dispositions": 450,
        "operational_failures": 0,
    }
    values.update(change)
    audit = audit_from_counts(**values)
    assert audit.gate.decision == "STOP"
    assert reason in audit.gate.reasons
```

- [ ] **Step 2: Write failing atomic report and CLI tests**

```python
def test_reports_are_deterministic_and_atomic(tmp_path, audit, monkeypatch):
    first = write_external_coverage_reports(audit, report_dir=tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first)
    second = write_external_coverage_reports(audit, report_dir=tmp_path)
    assert tuple(path.read_bytes() for path in second) == first_bytes


def test_collect_cli_missing_key_makes_no_network_call(monkeypatch, tmp_path):
    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    result = CliRunner().invoke(app, ["collect-external-odds", "--open", "--db", str(tmp_path / "toto.db")])
    assert result.exit_code != 0
    assert "API_SPORTS_KEY" in result.output


def test_audit_cli_reads_stored_data_without_api_key(populated_db, tmp_path):
    result = CliRunner().invoke(app, ["audit-external-coverage", "--db", str(populated_db), "--last", "30", "--report-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "GO" in result.output
```

- [ ] **Step 3: Run audit/report/CLI tests and confirm RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_external_odds_audit.py tests/test_external_odds_reports.py tests/test_external_odds_cli.py -q
```

- [ ] **Step 4: Implement exact stored-data metrics and gate**

Aggregate latest complete collection per drawing. Report overall, per-sport, per-league, and per-drawing:

- target count;
- unique match, missing, ambiguous, and unknown-sport counts/rates;
- complete consensus at one, two, and three eligible bookmakers;
- stale, semantic, incomplete-market, quota, provider-error, and fallback counts;
- median and p90 fallback events per drawing;
- average and maximum requests consumed per drawing.

The gate returns `PENDING` below 30 drawings or 450 events, `GO` only when every approved predicate passes, and `STOP` otherwise. Per-sport metrics are displayed for diagnosis but do not add an unapproved gate predicate.

- [ ] **Step 5: Implement deterministic atomic reports**

CSV contains one row per event disposition followed by stable aggregate rows. Markdown contains configuration, provenance, quota, overall/sport/league metrics, fallback-reason counts, gate predicates, and explicit statements that coverage is not probability quality or profitability evidence. Render both temporary files completely, fsync/close, then replace the final pair with rollback on any `BaseException`, matching the EV report safety contract.

- [ ] **Step 6: Implement both CLI commands**

```python
@app.command("collect-external-odds")
def collect_external_odds_command(
    open: bool = typer.Option(False),
    provider: str = typer.Option("api-sports"),
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    quota_reserve: int = typer.Option(10, min=0),
) -> None:
    if not open:
        raise typer.BadParameter("--open is required")
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    api_key = os.environ.get("API_SPORTS_KEY", "")
    try:
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        provider_client = APISportsClient(
            api_key,
            quota_reserve=quota_reserve,
        )
        result = collect_open_external_odds(
            TotoBriefClient(),
            provider_client,
            session_factory,
            load_aliases(aliases),
            fetched_at=datetime.now(timezone.utc),
        )
    except (APISportsError, OSError, SQLAlchemyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    print(_external_collection_table(result))


@app.command("audit-external-coverage")
def audit_external_coverage_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(30, min=1),
    min_bookmakers: int = typer.Option(3, min=1),
    report_dir: str = typer.Option("reports"),
) -> None:
    try:
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        audit = audit_external_coverage(
            session_factory,
            last=last,
            minimum_bookmakers=min_bookmakers,
        )
        paths = write_external_coverage_reports(audit, report_dir=report_dir)
    except (OSError, SQLAlchemyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    print(_external_coverage_table(audit))
    print(f"Reports written to {paths[0]} and {paths[1]}")
```

Collection requires `--open`, provider `api-sports`, and `API_SPORTS_KEY`. It uses `init_db()` because it writes prospective tables. Audit requires an existing database, uses `open_readonly_db()`, and performs no network calls or migrations. Both convert controlled provider, parsing, SQLAlchemy, and filesystem errors to concise `typer.BadParameter` messages without exposing secrets.

- [ ] **Step 7: Verify and commit**

Run focused tests, full pytest, Ruff, and both `--help` commands. Update memory and commit:

```bash
git add src/toto_ai/external_odds src/toto_ai/cli.py tests/test_external_odds_audit.py tests/test_external_odds_reports.py tests/test_external_odds_cli.py memory-bank README.md
git commit -m "Add external odds coverage audit"
```

---

### Task 7: End-to-End Fail-Closed Acceptance

**Files:**
- Create: `tests/test_external_odds_end_to_end.py`
- Modify: `README.md`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DECISIONS.md` only if an approved definition changed.

**Interfaces:**
- Consumes: the complete external coverage pipeline.
- Produces: reproducible acceptance evidence and an operator workflow for prospective collection.

- [ ] **Step 1: Add end-to-end success and failure tests**

```python
def test_open_collection_records_all_events_and_never_changes_ev_input(tmp_path):
    result = collect_open_external_odds(
        totobrief_client=fresh_drawing_client(),
        provider=mixed_coverage_provider(),
        session_factory=sqlite_factory(tmp_path),
        aliases={},
        fetched_at="2026-07-14T12:00:00Z",
    )
    assert len(result.events) == 15
    assert sum(row.probability_source == "api_sports_consensus" for row in result.events) == 9
    assert sum(row.probability_source == "totobrief_bk_fallback" for row in result.events) == 6
    assert tuple(event.true_probabilities for event in existing_ev_input()) == original_ev_probabilities()


def test_quota_failure_after_five_events_still_records_fifteen(tmp_path):
    result = collect_open_external_odds(
        totobrief_client=fresh_drawing_client(),
        provider=quota_failure_provider(after=5),
        session_factory=sqlite_factory(tmp_path),
        aliases={},
        fetched_at="2026-07-14T12:00:00Z",
    )
    assert len(result.events) == 15
    assert all(row.fallback_reason for row in result.events[5:])


def test_interrupted_collection_publishes_no_complete_run(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        collect_open_external_odds(
            totobrief_client=fresh_drawing_client(),
            provider=interrupting_provider(),
            session_factory=sqlite_factory(tmp_path),
            aliases={},
            fetched_at="2026-07-14T12:00:00Z",
        )
    assert load_latest_complete_collections(sqlite_factory(tmp_path), last=1) == ()
```

- [ ] **Step 2: Add secret-leak and report-integrity acceptance**

Assert the API key is absent from SQLite text values, cache files, CLI output, exceptions, CSV, and Markdown. Assert deterministic report hashes, all 15 ordered event rows, source and fallback reasons, provider timestamps, quota counters, consensus settings, and gate predicates.

- [ ] **Step 3: Document the operator workflow**

Add to README:

```bash
read -s API_SPORTS_KEY
export API_SPORTS_KEY
python -m toto_ai.cli collect-external-odds --open --provider api-sports --db data/toto.db
python -m toto_ai.cli audit-external-coverage --db data/toto.db --last 30 --min-bookmakers 3
```

Document the free 100-request-per-day limits for each API, quota reserve, prospective nature, 30-drawing/450-event minimum, explicit fallback behavior, and that external data does not affect `PLAY` in this phase.

- [ ] **Step 4: Run full acceptance verification**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest -q
PYTHONPATH=src ../../.venv/bin/python -m ruff check .
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli collect-external-odds --help
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli audit-external-coverage --help
PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli ev-package --help
```

Expected: all commands exit zero; existing `ev-package` options and accepted EV behavior remain unchanged.

- [ ] **Step 5: Update memory and commit acceptance**

Record exact test/Ruff/CLI evidence, mark implementation complete but the prospective gate pending, and commit:

```bash
git add README.md tests/test_external_odds_end_to_end.py memory-bank
git commit -m "Verify external odds coverage workflow"
```

---

## Post-Implementation Operations

Implementation completion does not produce a GO decision. The operator must
register one lawful API-Sports free account, provide `API_SPORTS_KEY` locally,
and run collection before each future drawing deadline until the database
contains at least 30 drawings and 450 events. Only then run the gate report.

- `GO`: design a separate calibrated ensemble and untouched prospective
  evaluation. Do not connect consensus directly to `PLAY` without that design.
- `STOP` due to coverage: implement The Odds API adapter against the same
  provider contract and rerun the free gate.
- `STOP` only due to quota: evaluate API-Sports Pro at 19 USD/month, remaining
  below the approved 30 USD ceiling, before purchasing.
