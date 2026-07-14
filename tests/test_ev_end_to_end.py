import hashlib

import numpy as np
import pytest

import toto_ai.ev.drawing as drawing_module
from toto_ai.ev.drawing import build_open_ev_package
from toto_ai.ev.models import EVComponents, EVConfig, EVSurface
from toto_ai.ev.reference import brute_force_gross_ev
from toto_ai.ev.reports import write_ev_package_reports


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
