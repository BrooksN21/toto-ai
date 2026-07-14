import csv
from pathlib import Path

import numpy as np
import pytest

import toto_ai.ev.reports as reports_module
from toto_ai.ev.drawing import EVPackageRun, EVSensitivitySummary
from toto_ai.ev.models import EVConfig, EVInput, EVPackage, EVSurface, RankedCoupon
from toto_ai.ev.reports import ev_package_report_paths, write_ev_package_reports


def fixture_run(*, decision="NO BET", unsupported=False):
    ranked = RankedCoupon(rank=1, coupon="1X2" * 5, gross_ev=0.95, net_ev=-0.05)
    return EVPackageRun(
        config=EVConfig(
            bank=6000,
            stake=30,
            mode="playable",
            min_gross_ev=1.0,
            prize_fund_factor=0.9,
        ),
        ev_input=EVInput(
            drawing_id=9000,
            drawing_number=5000,
            true_probabilities=((0.5, 0.3, 0.2),) * 15,
            crowd_probabilities=((0.45, 0.35, 0.2),) * 15,
            pool_sum=1_000_000.0,
            jackpot=100_000.0,
            possible_winnings=900_000.0,
            probability_sources=("totobrief_bk",) * 15,
            fetched_at="2026-07-14T12:00:00+00:00",
        ),
        surface=EVSurface(np.array([0.95]), 15, 1.0, 1.0, 1.0),
        package=EVPackage(
            decision=decision,
            coupons=() if decision == "NO BET" else (ranked,),
            cost=0 if decision == "NO BET" else 30,
            unused_bank=6000 if decision == "NO BET" else 5970,
            expected_payout=0.0 if decision == "NO BET" else 28.5,
            modeled_roi=None if decision == "NO BET" else -0.05,
            derived_brief=("",) * 15 if decision == "NO BET" else tuple(ranked.coupon),
        ),
        top_coupons=(ranked,),
        sensitivity=tuple(
            EVSensitivitySummary(
                prize_fund_factor=factor,
                possible_winnings=1_000_000.0 * factor,
                decision="NO BET",
                selected_count=0,
                cost=0,
                unused_bank=6000,
                expected_payout=0.0,
                modeled_roi=None,
            )
            for factor in (0.70, 0.80, 0.90, 1.00)
        ),
        possible_winnings_source="pool_sum proxy",
        jackpot_source="totobrief payload",
        self_dilution_ratio=0.010001 if unsupported else 0.0,
        model_supported=not unsupported,
        model_warning="self-dilution unsupported" if unsupported else None,
    )


def test_reports_use_deterministic_paths_and_disclose_model(tmp_path):
    csv_path, markdown_path = write_ev_package_reports(fixture_run(), tmp_path)

    assert csv_path.name == "ev_package_5000_playable_bank_6000.csv"
    assert markdown_path.name == "ev_package_5000_playable_bank_6000.md"
    with csv_path.open(encoding="utf-8", newline="") as source:
        assert next(csv.reader(source)) == ["rank", "coupon", "gross_ev", "net_ev"]
    markdown = markdown_path.read_text(encoding="utf-8")
    for expected in (
        "crowd joint model: independent event marginals",
        "possible winnings source: pool_sum proxy",
        "jackpot source: totobrief payload",
        "prize fund factor: 0.900000",
        "modeled ROI is not observed ROI",
        "decision: NO BET",
        "fetched at: 2026-07-14T12:00:00+00:00",
        "self-dilution ratio:",
        "model supported: yes",
        "## Sensitivity",
        "## Top 20 diagnostics",
    ):
        assert expected in markdown


def test_unsupported_no_bet_report_is_non_actionable(tmp_path):
    run = fixture_run(unsupported=True)

    csv_path, markdown_path = write_ev_package_reports(run, tmp_path)

    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "rank,coupon,gross_ev,net_ev"
    ]
    markdown = markdown_path.read_text(encoding="utf-8")
    for expected in (
        "decision: NO BET",
        "selected count: 0",
        "cost: 0",
        "unused bank: 6000",
        "expected payout: 0.000000000000",
        "modeled ROI: n/a",
        "model supported: no",
        "| 0.70 | 700000.000000 | NO BET | 0 | 0 | 6000 |",
    ):
        assert expected in markdown


def test_reports_are_deterministic(tmp_path):
    first = write_ev_package_reports(fixture_run(decision="PLAY"), tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first)

    second = write_ev_package_reports(fixture_run(decision="PLAY"), tmp_path)

    assert tuple(path.read_bytes() for path in second) == first_bytes


def test_reports_reject_input_output_path_collision(tmp_path):
    run = fixture_run()
    csv_path, _ = ev_package_report_paths(run, tmp_path)

    with pytest.raises(ValueError, match="distinct"):
        write_ev_package_reports(run, tmp_path, input_paths=(csv_path,))


def test_second_report_replace_failure_restores_existing_pair(monkeypatch, tmp_path):
    run = fixture_run(decision="PLAY")
    csv_path, markdown_path = ev_package_report_paths(run, tmp_path)
    csv_path.write_bytes(b"old csv\n")
    markdown_path.write_bytes(b"old markdown\n")
    original_replace = Path.replace
    final_replace_count = 0

    def fail_second_final_replace(source, target):
        nonlocal final_replace_count
        if Path(target) in {csv_path, markdown_path}:
            final_replace_count += 1
            if final_replace_count == 2:
                raise OSError("second final replace failed")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_final_replace)

    with pytest.raises(OSError, match="second final replace failed"):
        write_ev_package_reports(run, tmp_path)

    assert csv_path.read_bytes() == b"old csv\n"
    assert markdown_path.read_bytes() == b"old markdown\n"
    assert set(tmp_path.iterdir()) == {csv_path, markdown_path}


def test_keyboard_interrupt_during_second_replace_restores_existing_pair(
    monkeypatch,
    tmp_path,
):
    run = fixture_run(decision="PLAY")
    csv_path, markdown_path = ev_package_report_paths(run, tmp_path)
    csv_path.write_bytes(b"old csv\n")
    markdown_path.write_bytes(b"old markdown\n")
    original_replace = Path.replace
    final_replace_count = 0

    def interrupt_second_final_replace(source, target):
        nonlocal final_replace_count
        if Path(target) in {csv_path, markdown_path}:
            final_replace_count += 1
            if final_replace_count == 2:
                raise KeyboardInterrupt("second final replace interrupted")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", interrupt_second_final_replace)

    with pytest.raises(KeyboardInterrupt, match="second final replace interrupted"):
        write_ev_package_reports(run, tmp_path)

    assert csv_path.read_bytes() == b"old csv\n"
    assert markdown_path.read_bytes() == b"old markdown\n"
    assert set(tmp_path.iterdir()) == {csv_path, markdown_path}


def test_render_failure_leaves_no_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        reports_module,
        "_render_markdown",
        lambda result: (_ for _ in ()).throw(OSError("render failed")),
    )

    with pytest.raises(OSError, match="render failed"):
        write_ev_package_reports(fixture_run(), tmp_path)

    assert list(tmp_path.iterdir()) == []
