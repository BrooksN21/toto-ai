import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from toto_ai.external_odds.domain import TargetDrawing, TargetEvent
from toto_ai.external_odds.schedule_evidence import (
    drawing_schedule_dates,
    ingest_reviewed_observation,
    load_schedule_evidence_ledger,
    resolve_schedule_evidence,
)

NOW = datetime(2026, 8, 3, 17, 30, tzinfo=timezone.utc)
DEADLINE = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)


def _target(
    home: str,
    away: str,
    championship: str,
    *,
    starts_at=None,
    order=0,
):
    return TargetEvent(
        drawing_id=12004,
        drawing_number=4965,
        event_id=179163 + order,
        event_order=order,
        sport="football",
        championship=championship,
        starts_at=starts_at,
        deadline=DEADLINE,
        home_team=home,
        away_team=away,
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )


def _ledger(tmp_path, observations):
    tmp_path.mkdir(parents=True, exist_ok=True)
    review = tmp_path / "review.md"
    review.write_text("reviewed official schedule", encoding="utf-8")
    digest = hashlib.sha256(review.read_bytes()).hexdigest()
    for item in observations:
        item.update(
            reviewer="tester",
            reviewed_at="2026-08-03T17:00:00Z",
            review_document="review.md",
            review_document_sha256=digest,
            claims=[
                {
                    "source_name": "official",
                    "role": "official",
                    "source_url": "https://example.test/schedule",
                }
            ],
            status="scheduled",
        )
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-03T17:00:00Z",
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )
    return load_schedule_evidence_ledger(path)


def _observation(**overrides):
    row = {
        "observation_id": "match-1",
        "sport": "football",
        "gender_age_class": "men-senior",
        "competition_aliases": [
            "Европа. Лига Европы УЕФА. Квалификация",
            "UEFA Europa League qualifying",
        ],
        "home_entity": "FC Iberia 1999",
        "home_aliases": ["Иберия 1999", "FC Iberia 1999", "FC Saburtalo"],
        "away_entity": "Larne FC",
        "away_aliases": ["Ларн", "Larne FC"],
        "starts_at": "2026-08-06T19:00:00Z",
        "conditional": False,
    }
    row.update(overrides)
    return row


def test_unseen_localized_and_historical_aliases_resolve_exactly(tmp_path):
    historical = _observation(
        observation_id="historical-alias-review",
        home_aliases=["FC Saburtalo", "ФК Сабуртало"],
        away_entity="Historical Opponent",
        away_aliases=["Historical Opponent"],
        starts_at="2026-08-08T19:00:00Z",
    )
    current = _observation(
        home_aliases=["Иберия 1999", "FC Iberia 1999"],
    )
    ledger = _ledger(tmp_path, [historical, current])
    result = resolve_schedule_evidence(
        _target(
            "ФК Сабуртало",
            "Ларн",
            "Европа. Лига Европы УЕФА. Квалификация",
        ),
        ledger,
        evaluated_at=NOW,
    )
    assert result.state == "RESOLVED"
    assert result.observation.home_entity == "FC Iberia 1999"

    # Ledger observations are drawing-neutral: a renamed multilingual alias
    # remains reusable for a new drawing/event identity without a catalog row.
    reused = resolve_schedule_evidence(
        TargetEvent(
            **{
                **_target(
                    "FC Saburtalo",
                    "LARNE F.C.",
                    "UEFA Europa League qualifying",
                ).__dict__,
                "drawing_id": 13000,
                "drawing_number": 5000,
                "event_id": 220000,
            }
        ),
        ledger,
        evaluated_at=NOW,
    )
    assert reused.state == "RESOLVED"
    assert reused.confidence == "high"


def test_unsupported_script_alias_does_not_block_supported_exact_alias(tmp_path):
    observation = _observation(
        home_aliases=["الفايكنج FK", "Иберия 1999", "FC Iberia 1999"],
    )
    ledger = _ledger(tmp_path, [observation])

    result = resolve_schedule_evidence(
        _target(
            "Иберия 1999",
            "Ларн",
            "Европа. Лига Европы УЕФА. Квалификация",
        ),
        ledger,
        evaluated_at=NOW,
    )

    assert result.state == "RESOLVED"
    assert result.observation.home_entity == "FC Iberia 1999"


def test_fuzzy_only_stays_review_required_but_exact_reversed_schedule_resolves(
    tmp_path,
):
    ledger = _ledger(tmp_path, [_observation()])
    fuzzy = resolve_schedule_evidence(
        _target("Иберия Сити", "Ларн Таун", "Европа. Лига Европы УЕФА. Квалификация"),
        ledger,
        evaluated_at=NOW,
    )
    reversed_pair = resolve_schedule_evidence(
        _target("Ларн", "Иберия 1999", "Европа. Лига Европы УЕФА. Квалификация"),
        ledger,
        evaluated_at=NOW,
    )
    assert fuzzy.state == "REVIEW_REQUIRED"
    assert reversed_pair.state == "RESOLVED"
    assert reversed_pair.orientation == "reversed"


def test_womens_marker_is_not_silently_dropped(tmp_path):
    ledger = _ledger(tmp_path, [_observation()])
    women = resolve_schedule_evidence(
        _target("Иберия 1999 (ж)", "Ларн (ж)", "Женщины. Лига Европы"),
        ledger,
        evaluated_at=NOW,
    )
    assert women.state != "RESOLVED"


def test_missing_start_uses_bounded_five_day_window(tmp_path):
    ledger = _ledger(
        tmp_path,
        [_observation(starts_at="2026-08-09T14:59:00Z")],
    )
    target = _target("Иберия 1999", "Ларн", "Европа. Лига Европы УЕФА. Квалификация")
    assert (
        resolve_schedule_evidence(target, ledger, evaluated_at=NOW).state == "RESOLVED"
    )
    drawing = TargetDrawing(
        12004,
        4965,
        DEADLINE,
        NOW,
        tuple(
            TargetEvent(**{**target.__dict__, "event_id": 200 + i, "event_order": i})
            for i in range(15)
        ),
    )
    assert drawing_schedule_dates(drawing, maximum_span_days=5) == tuple(
        date(2026, 8, 3) + timedelta(days=offset) for offset in range(6)
    )


def test_known_four_day_drawing_fetches_every_intermediate_date():
    starts = tuple(DEADLINE + timedelta(days=4) for _ in range(15))
    events = tuple(
        TargetEvent(
            **{
                **_target("Home", "Away", "League", order=i).__dict__,
                "event_id": 300 + i,
                "event_order": i,
                "starts_at": starts[i],
            }
        )
        for i in range(15)
    )
    drawing = TargetDrawing(12004, 4965, DEADLINE, NOW, events)
    assert drawing_schedule_dates(drawing) == tuple(
        date(2026, 8, 3) + timedelta(days=offset) for offset in range(6)
    )


def test_schedule_dates_cover_moscow_day_across_utc_date_boundaries():
    event = _target(
        "Home",
        "Away",
        "League",
        starts_at=datetime(2026, 8, 4, 22, 30, tzinfo=timezone.utc),
    )
    drawing = TargetDrawing(
        12004,
        4965,
        DEADLINE,
        NOW,
        tuple(
            TargetEvent(**{**event.__dict__, "event_id": 400 + i, "event_order": i})
            for i in range(15)
        ),
    )

    assert drawing_schedule_dates(drawing) == (
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 8, 5),
    )


def test_conditional_cup_pairing_and_source_gap_fail_closed(tmp_path):
    ledger = _ledger(tmp_path, [_observation(conditional=True)])
    target = _target("Иберия 1999", "Ларн", "Европа. Лига Европы УЕФА. Квалификация")
    conditional = resolve_schedule_evidence(target, ledger, evaluated_at=NOW)
    missing = resolve_schedule_evidence(
        _target("Unknown", "Missing", "Unknown competition"),
        ledger,
        evaluated_at=NOW,
    )
    assert conditional.state == "REVIEW_REQUIRED"
    assert missing.state == "SOURCE_MISSING"

    exact = _ledger(tmp_path / "exact", [_observation()])
    failed = resolve_schedule_evidence(
        target,
        exact,
        evaluated_at=NOW,
        source_coverage={date(2026, 8, 6): "failed"},
    )
    gap = resolve_schedule_evidence(
        target,
        exact,
        evaluated_at=NOW,
        source_coverage={},
    )
    assert failed.state == "SOURCE_FAILED"
    assert gap.state == "SOURCE_MISSING"


def test_reviewed_evidence_ingestion_is_append_only_and_idempotent(tmp_path):
    path = _ledger(tmp_path, [_observation()]).path
    payload = json.loads(path.read_text(encoding="utf-8"))
    row = payload["observations"][0]
    assert ingest_reviewed_observation(path, row).semantic_hash
    changed = {**row, "starts_at": "2026-08-07T19:00:00Z"}
    try:
        ingest_reviewed_observation(path, changed)
    except ValueError as error:
        assert "immutable" in str(error)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError("changed reviewed evidence was accepted")


def test_repository_4965_evidence_resolves_only_non_conflicting_exact_rows():
    ledger = load_schedule_evidence_ledger(
        __import__("pathlib").Path("data/schedule-evidence/ledger.json")
    )
    rows = (
        _target(
            "Сент-Жиллуаз",
            "Боде Глимт",
            "Европа. Лига Чемпионов УЕФА. Квалификация",
            order=5,
        ),
        _target(
            "Ларн", "Иберия 1999", "Европа. Лига Европы УЕФА. Квалификация", order=7
        ),
        _target("Ремо", "Сантос", "Бразилия. Кубок", order=10),
        _target(
            "Шарлотт ФК",
            "Пумас УНАМ",
            "Америка. Кубок Североамериканских лиг",
            order=12,
        ),
        _target(
            "Тигрес",
            "Реал Солт Лейк",
            "Америка. Кубок Североамериканских лиг",
            order=13,
        ),
    )
    states = tuple(
        resolve_schedule_evidence(item, ledger, evaluated_at=NOW).state for item in rows
    )
    assert states == (
        "RESOLVED",
        "SOURCE_MISSING",
        "RESOLVED",
        "RESOLVED",
        "SOURCE_MISSING",
    )


def test_conflicting_official_home_away_identity_is_rejected(tmp_path):
    first = _observation(
        observation_id="tigres-rsl-a",
        home_entity="Tigres UANL",
        home_aliases=["Тигрес", "Tigres UANL"],
        away_entity="Real Salt Lake",
        away_aliases=["Реал Солт Лейк", "Real Salt Lake"],
        starts_at="2026-08-05T02:00:00Z",
    )
    second = _observation(
        observation_id="tigres-rsl-b",
        home_entity="Tigres de la UANL",
        home_aliases=["Тигрес", "Tigres de la UANL"],
        away_entity="Real Salt Lake",
        away_aliases=["Реал Солт Лейк", "Real Salt Lake"],
        starts_at="2026-08-05T02:00:00Z",
    )
    ledger = _ledger(tmp_path, [first, second])
    result = resolve_schedule_evidence(
        _target(
            "Тигрес",
            "Реал Солт Лейк",
            "Америка. Кубок Североамериканских лиг",
        ),
        ledger,
        evaluated_at=NOW,
    )
    assert result.state == "CONFLICT"
    assert result.observation is None
