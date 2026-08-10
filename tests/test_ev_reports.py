import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import toto_ai.ev.reports as reports_module
from toto_ai.ev.drawing import EVPackageRun, EVSensitivitySummary
from toto_ai.ev.models import (
    EVConfig,
    EVInput,
    EVPackage,
    EVSurface,
    PlayTimingEligibility,
    RankedCoupon,
    SafetyAwareSelectionDiagnostics,
    SafetyMaterialRepair,
    SafetySelectionExposure,
    SafetySelectionReplacement,
)
from toto_ai.ev.reports import ev_package_report_paths, write_ev_package_reports


def fixture_run(*, decision="NO BET", unsupported=False, timing=None):
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
        timing_eligibility=timing or PlayTimingEligibility.not_checked(),
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
        "decision reason: n/a",
        "requested bank: 6000",
        "effective cap: 6000",
        "selected cost: 0",
        "unused requested bank: 6000",
        "fetched at: 2026-07-14T12:00:00+00:00",
        "self-dilution ratio:",
        "model supported: yes",
        "## Sensitivity",
        "## Top 20 diagnostics",
    ):
        assert expected in markdown


def test_report_exposes_requested_bank_effective_cap_and_unused_request(tmp_path):
    base = fixture_run(decision="PLAY")
    run = replace(
        base,
        config=replace(base.config, bank=4980, effective_budget=810),
        ev_input=replace(
            base.ev_input,
            pool_sum=81_445.0,
            possible_winnings=73_300.5,
        ),
        package=replace(
            base.package,
            cost=30,
            unused_bank=4950,
            expected_payout=28.5,
            modeled_roi=-0.05,
        ),
        self_dilution_ratio=30 / 81_445,
    )

    _, markdown_path = write_ev_package_reports(run, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")

    for expected in (
        "requested bank: 4980",
        "effective cap: 810",
        "selected cost: 30",
        "unused requested bank: 4950",
        "self-dilution ratio: 0.000368346737",
    ):
        assert expected in markdown


def test_report_exposes_safety_aware_reselection_diagnostics(tmp_path):
    base = fixture_run(decision="PLAY")
    diagnostics = SafetyAwareSelectionDiagnostics(
        required_coupon_count=2,
        eligible_candidate_count=9,
        candidate_universe_count=9,
        candidate_universe_exhaustive=True,
        concentration_maximum_count=1,
        pre_exposures=(
            SafetySelectionExposure(1, (2, 0, 0), "1", 2, 1.0),
        ),
        post_exposures=(
            SafetySelectionExposure(1, (1, 0, 1), "1", 1, 0.5),
        ),
        material_outcomes_repaired=(
            SafetyMaterialRepair(1, "2", 0.3, 0, 1),
        ),
        replacements=(
            SafetySelectionReplacement(2, "1" * 15, 9.0, 3, "2" * 15, 8.0, -1.0),
        ),
        gross_ev_delta=-1.0,
        pre_package_sha256="a" * 64,
        post_package_sha256="b" * 64,
        constraint_feasible=True,
        infeasibility_reasons=(),
    )
    run = replace(
        base,
        package=replace(base.package, selection_diagnostics=diagnostics),
    )

    _, markdown_path = write_ev_package_reports(run, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")

    for expected in (
        "## Safety-aware Reselection",
        "constraint feasible: yes",
        "candidate universe: 9 / 9 (exhaustive: yes)",
        "concentration maximum count: 1",
        "material outcomes repaired: E1 2 (0->1)",
        "replacements: 1",
        "gross EV delta: -1.000000000000",
        "| 1 | 1:2/0/0 (100.0000%) | 1:1/0/1 (50.0000%) |",
    ):
        assert expected in markdown


def test_below_stake_no_bet_report_includes_precise_reason(tmp_path):
    reason = (
        "Effective budget 0 RUB is below one coupon stake 30 RUB after applying "
        "the 1% self-dilution support limit to requested bank 30 RUB; no "
        "supported coupon can be selected."
    )
    base = fixture_run()
    run = replace(
        base,
        config=replace(base.config, bank=30, effective_budget=0),
        ev_input=replace(
            base.ev_input,
            pool_sum=2_999.999,
            possible_winnings=2_699.9991,
        ),
        package=replace(
            base.package,
            unused_bank=30,
            decision_reason=reason,
        ),
        model_warning=reason,
    )

    _, markdown_path = write_ev_package_reports(run, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "decision: NO BET" in markdown
    assert f"decision reason: {reason}" in markdown
    assert "requested bank: 30" in markdown
    assert "effective cap: 0" in markdown
    assert f"model warning: {reason}" in markdown


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


def test_timing_veto_report_is_deterministic_and_csv_is_header_only(tmp_path):
    timing = PlayTimingEligibility(
        status="multi_day",
        reason="event span exceeds two Moscow calendar days",
        target_fingerprint="1234abcd" * 8,
        fingerprint_match=True,
    )
    run = fixture_run(timing=timing)

    first_csv, first_markdown = write_ev_package_reports(run, tmp_path)
    first_bytes = (first_csv.read_bytes(), first_markdown.read_bytes())
    second_csv, second_markdown = write_ev_package_reports(run, tmp_path)

    assert second_csv.read_text(encoding="utf-8").splitlines() == [
        "rank,coupon,gross_ev,net_ev"
    ]
    markdown = second_markdown.read_text(encoding="utf-8")
    timing_lines = markdown.split("## Timing Eligibility\n\n", maxsplit=1)[1].split(
        "\n\n## ", maxsplit=1
    )[0]
    assert timing_lines.splitlines() == [
        "- status: multi_day",
        "- fingerprint match: yes",
        f"- target fingerprint: {timing.target_fingerprint}",
        "- reason: event span exceeds two Moscow calendar days",
    ]
    assert "Timing-veto diagnostics are suppressed in playable mode." in markdown
    assert "1X21X21X21X21X2" not in markdown
    assert (second_csv.read_bytes(), second_markdown.read_bytes()) == first_bytes


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


def test_system_exit_during_second_replace_restores_existing_pair(
    monkeypatch,
    tmp_path,
):
    run = fixture_run(decision="PLAY")
    csv_path, markdown_path = ev_package_report_paths(run, tmp_path)
    csv_path.write_bytes(b"old csv\n")
    markdown_path.write_bytes(b"old markdown\n")
    original_replace = Path.replace
    final_replace_count = 0

    def exit_during_second_final_replace(source, target):
        nonlocal final_replace_count
        if Path(target) in {csv_path, markdown_path}:
            final_replace_count += 1
            if final_replace_count == 2:
                raise SystemExit("second final replace exited")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", exit_during_second_final_replace)

    with pytest.raises(SystemExit, match="second final replace exited"):
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
