import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

import toto_ai.cli as cli_module
import toto_ai.ev.drawing as drawing_module
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.drawing import build_open_ev_package
from toto_ai.ev.models import EVComponents, EVConfig, EVSurface
from toto_ai.ev.reference import brute_force_gross_ev
from toto_ai.ev.reports import write_ev_package_reports
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import ProviderEvent, QuotaState
from toto_ai.external_odds.storage import save_collection
from toto_ai.external_odds.targets import parse_target_drawing


@pytest.fixture
def deterministic_payload():
    return {
        "data": {
            "id": 9100,
            "number": 5100,
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": [
                {
                    "order": order,
                    "quotes": {
                        "bk_win_1": 45 + order,
                        "bk_draw": 30 + order,
                        "bk_win_2": 25 + order,
                        "pool_win_1": 48 + order,
                        "pool_draw": 32 + order,
                        "pool_win_2": 20 + order,
                    },
                }
                for order in reversed(range(15))
            ],
        }
    }


class _PayloadClient:
    def __init__(self, payload):
        self.payload = payload

    def drawing_info(self, drawing_id):
        assert drawing_id == self.payload["data"]["id"]
        return self.payload


def _fixed_components(_ev_input, progress_callback=None):
    if progress_callback is not None:
        progress_callback({"phase": "category", "category": 15})
    values = np.zeros(3**6, dtype=np.float64)
    return EVComponents(
        possible_winnings_ev_per_ruble=values,
        jackpot_ev_per_ruble=values,
        event_count=6,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def _fixed_surface(_components, _possible_winnings, _jackpot):
    return EVSurface(
        gross_ev=np.linspace(0.20, 1.50, num=3**6, dtype=np.float64),
        event_count=6,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def _timing_payload(status):
    base_start = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
    events = []
    for order in reversed(range(15)):
        if status == "multi_day":
            starts_at = base_start + timedelta(days=order // 5, minutes=order)
        elif status == "unknown" and order == 14:
            starts_at = None
        else:
            starts_at = base_start + timedelta(minutes=order)
        events.append(
            {
                "id": 20_000 + order,
                "order": order,
                "name": f"Home {order} - Away {order}",
                "name_en": None,
                "championship": "League",
                "start_at": None if starts_at is None else starts_at.isoformat(),
                "quotes": {
                    "bk_win_1": 45 + order,
                    "bk_draw": 30 + order,
                    "bk_win_2": 25 + order,
                    "pool_win_1": 48 + order,
                    "pool_draw": 32 + order,
                    "pool_win_2": 20 + order,
                },
            }
        )
    return {
        "data": {
            "id": 9100,
            "number": 5100,
            "ended_at": (base_start - timedelta(hours=1)).isoformat(),
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": events,
        }
    }


class _TimingProvider:
    provider_name = "api-sports"

    def __init__(self, target):
        self.target = target
        self.requests_made = 0
        self.cache_hits = 0
        self._quota_state = QuotaState(
            daily_limit=100,
            daily_remaining=99,
            minute_limit=10,
            minute_remaining=9,
        )

    @property
    def quota_state(self):
        return self._quota_state

    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        requested_date = dates[0]
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"provider-{event.event_order}",
                sport="football",
                league="League",
                starts_at=event.starts_at,
                home_team=event.home_team,
                away_team=event.away_team,
                fetched_at=self.target.fetched_at,
                payload_hash=f"schedule-{event.event_order}",
            )
            for event in self.target.events
            if event.starts_at is not None
            and event.starts_at.date() == requested_date
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        return ()


def _persist_timing_collection(db_path, payload):
    fetched_at = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    target = parse_target_drawing(payload, fetched_at=fetched_at)
    collection = build_external_collection(
        target,
        _TimingProvider(target),
        aliases={},
    )
    engine = init_db(db_path)
    try:
        save_collection(get_session_factory(engine), collection)
    finally:
        engine.dispose()
    return collection


def _build_with_db_resolver(monkeypatch, payload, db_path, *, mode="playable"):
    monkeypatch.setattr(drawing_module, "compute_ev_components", _fixed_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", _fixed_surface)
    monkeypatch.setattr(
        drawing_module,
        "_utc_now",
        lambda: "2026-07-16T12:00:00+00:00",
    )
    return build_open_ev_package(
        client=_PayloadClient(payload),
        drawing_id=payload["data"]["id"],
        config=EVConfig(bank=30, stake=30, mode=mode, min_gross_ev=1.0),
        timing_eligibility_resolver=cli_module._build_timing_eligibility_resolver(
            str(db_path)
        ),
    )


def _run_and_publish(monkeypatch, payload, config, report_dir):
    monkeypatch.setattr(drawing_module, "compute_ev_components", _fixed_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", _fixed_surface)
    monkeypatch.setattr(
        drawing_module,
        "_utc_now",
        lambda: "2026-07-14T12:00:00+00:00",
    )
    run = build_open_ev_package(
        client=_PayloadClient(payload),
        drawing_id=payload["data"]["id"],
        config=config,
    )
    csv_path, markdown_path = write_ev_package_reports(run, report_dir)
    return run, csv_path, markdown_path


def _markdown_table_rows(markdown, heading):
    lines = markdown.splitlines()
    start = lines.index(heading) + 1
    stop = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith("## ")
        ),
        len(lines),
    )
    table_lines = [line for line in lines[start:stop] if line.startswith("|")]
    assert len(table_lines) >= 2
    return [
        tuple(cell.strip() for cell in line.strip("|").split("|"))
        for line in table_lines[2:]
    ]


@pytest.mark.parametrize(
    ("stored_status", "fresh_mismatch", "expected_status", "expected_decision"),
    [
        ("playable", False, "playable", "PLAY"),
        ("multi_day", False, "multi_day", "NO BET"),
        ("unknown", False, "unknown", "NO BET"),
        ("playable", True, "absent", "NO BET"),
    ],
)
def test_actual_readonly_timing_lookup_gates_playable_output(
    monkeypatch,
    tmp_path,
    stored_status,
    fresh_mismatch,
    expected_status,
    expected_decision,
):
    stored_payload = _timing_payload(stored_status)
    collection = _persist_timing_collection(tmp_path / "timing.sqlite", stored_payload)
    fresh_payload = deepcopy(stored_payload)
    if fresh_mismatch:
        fresh_payload["data"]["events"][0]["name"] = "Changed Home - Changed Away"

    run = _build_with_db_resolver(
        monkeypatch,
        fresh_payload,
        tmp_path / "timing.sqlite",
    )

    assert run.timing_eligibility.status == expected_status
    assert run.timing_eligibility.fingerprint_match is (not fresh_mismatch)
    assert run.package.decision == expected_decision
    assert run.ev_input.probability_sources == ("totobrief_bk",) * 15
    if not fresh_mismatch:
        assert run.timing_eligibility.target_fingerprint == (
            collection.target_fingerprint
        )
    if expected_decision == "NO BET":
        assert run.package.coupons == ()
        assert run.package.cost == 0
        assert run.package.unused_bank == run.config.bank
        assert run.package.expected_payout == 0.0
        assert run.package.modeled_roi is None
        assert run.package.derived_brief == ("",) * 6


@pytest.mark.parametrize("database_kind", ["missing", "unreadable"])
def test_missing_or_unreadable_timing_db_fails_closed_only_for_playable(
    monkeypatch,
    tmp_path,
    database_kind,
):
    payload = _timing_payload("playable")
    db_path = (
        tmp_path / "missing.sqlite" if database_kind == "missing" else tmp_path
    )

    playable = _build_with_db_resolver(monkeypatch, payload, db_path)
    research = _build_with_db_resolver(
        monkeypatch,
        payload,
        db_path,
        mode="research",
    )

    assert playable.timing_eligibility.status == "absent"
    assert playable.timing_eligibility.fingerprint_match is False
    assert playable.package.decision == "NO BET"
    assert playable.package.cost == 0
    assert research.timing_eligibility.status == "absent"
    assert research.package.decision == "RESEARCH ONLY"
    assert research.package.coupons
    assert research.ev_input.probability_sources == ("totobrief_bk",) * 15


def test_playable_pipeline_can_return_honest_no_bet(
    monkeypatch,
    tmp_path,
    deterministic_payload,
):
    run, csv_path, markdown_path = _run_and_publish(
        monkeypatch,
        deterministic_payload,
        EVConfig(bank=6000, stake=30, mode="playable", min_gross_ev=9.0),
        tmp_path,
    )

    assert run.package.decision == "NO BET"
    assert run.package.coupons == ()
    assert run.package.cost == 0
    assert run.package.unused_bank == 6000
    assert csv_path.exists()
    assert "modeled ROI is not observed ROI" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_research_pipeline_uses_dynamic_bank_and_deterministic_reports(
    monkeypatch,
    tmp_path,
    deterministic_payload,
):
    config = EVConfig(bank=9600, stake=30, mode="research")

    first, first_csv, first_markdown = _run_and_publish(
        monkeypatch,
        deterministic_payload,
        config,
        tmp_path,
    )
    first_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (first_csv, first_markdown)
    )
    second, second_csv, second_markdown = _run_and_publish(
        monkeypatch,
        deterministic_payload,
        config,
        tmp_path,
    )

    assert len(first.package.coupons) == config.max_coupons == 320
    assert first.package.cost == 9600
    assert second.package == first.package
    assert tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (second_csv, second_markdown)
    ) == first_hashes
    markdown = second_markdown.read_text(encoding="utf-8")
    for assumption in (
        "crowd joint model: independent event marginals",
        "possible winnings source: pool_sum proxy",
        "jackpot source: totobrief payload",
        "prize fund factor: 1.000000",
        "modeled ROI is not observed ROI",
        "model supported: yes",
    ):
        assert assumption in markdown

    event_rows = _markdown_table_rows(markdown, "## Event Probabilities")
    assert len(event_rows) == 15
    assert [row[0] for row in event_rows] == [str(index) for index in range(1, 16)]
    assert all(len(row) == 8 and row[1] == "totobrief_bk" for row in event_rows)

    sensitivity_rows = _markdown_table_rows(markdown, "## Sensitivity")
    assert len(sensitivity_rows) == 4
    assert [row[0] for row in sensitivity_rows] == ["0.70", "0.80", "0.90", "1.00"]
    assert all(len(row) == 8 for row in sensitivity_rows)


def test_interrupted_surface_build_creates_no_play_report(
    monkeypatch,
    tmp_path,
    deterministic_payload,
):
    monkeypatch.setattr(drawing_module, "compute_ev_components", _fixed_components)

    def interrupted_surface(*_args):
        raise KeyboardInterrupt("surface interrupted")

    monkeypatch.setattr(
        drawing_module,
        "materialize_ev_surface",
        interrupted_surface,
    )

    with pytest.raises(KeyboardInterrupt, match="surface interrupted"):
        run = build_open_ev_package(
            client=_PayloadClient(deterministic_payload),
            drawing_id=deterministic_payload["data"]["id"],
            config=EVConfig(
                bank=6000,
                stake=30,
                mode="playable",
                min_gross_ev=1.0,
            ),
        )
        write_ev_package_reports(run, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_reference_oracle_rejects_more_than_eight_events_before_enumeration():
    probabilities = ((0.5, 0.3, 0.2),) * 9

    with pytest.raises(
        ValueError,
        match="reference oracle supports at most 8 events",
    ):
        brute_force_gross_ev(
            true_probabilities=probabilities,
            crowd_probabilities=probabilities,
            pool_sum=1_000.0,
            stake=30,
            category_funds_by_hits={9: 100.0},
            minimum_category=9,
        )
