import gc
import weakref
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

import toto_ai.cli as cli_module
from toto_ai.cli import app
from toto_ai.ev.drawing import (
    EVPackageRun,
    build_open_ev_package,
    ev_input_from_payload,
    resolve_open_drawing_from_api,
)
from toto_ai.ev.models import (
    EVComponents,
    EVConfig,
    EVPackage,
    EVSurface,
    PlayTimingEligibility,
    RankedCoupon,
)
from toto_ai.ev.package_quality import PackageSelectionProvenance


@pytest.fixture
def open_drawing_payload():
    events = []
    for order in reversed(range(15)):
        events.append(
            {
                "order": order,
                "result": "must-not-be-read",
                "quotes": {
                    "bk_win_1": 45 + order,
                    "bk_draw": 30 + order,
                    "bk_win_2": 25 + order,
                    "pool_win_1": 50 + order,
                    "pool_draw": 35 + order,
                    "pool_win_2": 15 + order,
                },
            }
        )
    return {
        "data": {
            "id": 9000,
            "number": 5000,
            "pool_sum": 3_000.0,
            "jackpot": 1_200.0,
            "events": events,
        }
    }


def test_payload_becomes_ordered_ev_input(open_drawing_payload):
    result = ev_input_from_payload(
        open_drawing_payload,
        fetched_at="2026-07-14T12:00:00+00:00",
        stake=30,
        prize_fund_factor=0.9,
        possible_winnings=None,
        jackpot_override=None,
    )

    assert result.drawing_id == 9000
    assert result.drawing_number == 5000
    assert len(result.true_probabilities) == 15
    assert result.true_probabilities[0] == pytest.approx((0.45, 0.30, 0.25))
    assert result.true_probabilities[-1] == pytest.approx(
        (59 / 142, 44 / 142, 39 / 142)
    )
    assert result.possible_winnings == result.pool_sum * 0.9
    assert result.probability_sources == ("totobrief_bk",) * 15
    assert all(sum(row) == pytest.approx(1.0) for row in result.crowd_probabilities)


def test_payload_uses_explicit_winnings_and_jackpot_override(open_drawing_payload):
    open_drawing_payload["data"]["jackpot"] = None

    result = ev_input_from_payload(
        open_drawing_payload,
        fetched_at="2026-07-14T12:00:00+00:00",
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=2_500.0,
        jackpot_override=800.0,
    )

    assert result.possible_winnings == 2_500.0
    assert result.jackpot == 800.0


def test_payload_rejects_naive_fetched_at(open_drawing_payload):
    with pytest.raises(ValueError, match="timezone"):
        ev_input_from_payload(
            open_drawing_payload,
            fetched_at="2026-07-14T12:00:00",
            stake=30,
            prize_fund_factor=1.0,
            possible_winnings=None,
            jackpot_override=None,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.__setitem__("pool_sum", 10**10_000),
        lambda data: data["events"][0]["quotes"].__setitem__("bk_win_1", 10**10_000),
    ],
)
def test_payload_converts_oversized_numeric_failures_to_value_error(
    open_drawing_payload,
    mutate,
):
    mutate(open_drawing_payload["data"])

    with pytest.raises(ValueError, match="finite number"):
        ev_input_from_payload(
            open_drawing_payload,
            fetched_at="2026-07-14T12:00:00+00:00",
            stake=30,
            prize_fund_factor=1.0,
            possible_winnings=None,
            jackpot_override=None,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["events"].pop(), "exactly 15"),
        (
            lambda data: data["events"].__setitem__(
                0, {**data["events"][0], "order": 0}
            ),
            "orders 0 through 14",
        ),
        (lambda data: data.__setitem__("pool_sum", None), "pool_sum"),
        (lambda data: data.__setitem__("jackpot", None), "jackpot"),
        (lambda data: data["events"][0]["quotes"].__setitem__("bk_win_1", -1), "BK"),
        (
            lambda data: data["events"][0]["quotes"].__setitem__("pool_draw", None),
            "pool",
        ),
    ],
)
def test_payload_rejects_incomplete_or_invalid_inputs(
    open_drawing_payload,
    mutate,
    message,
):
    mutate(open_drawing_payload["data"])

    with pytest.raises(ValueError, match=message):
        ev_input_from_payload(
            open_drawing_payload,
            fetched_at="2026-07-14T12:00:00+00:00",
            stake=30,
            prize_fund_factor=1.0,
            possible_winnings=None,
            jackpot_override=None,
        )


def test_payload_rejects_explicit_winnings_with_non_default_factor(
    open_drawing_payload,
):
    with pytest.raises(ValueError, match="possible_winnings"):
        ev_input_from_payload(
            open_drawing_payload,
            fetched_at="2026-07-14T12:00:00+00:00",
            stake=30,
            prize_fund_factor=0.9,
            possible_winnings=2_500.0,
            jackpot_override=None,
        )


def test_resolver_uses_page_one_and_nearest_future_ended_at():
    class Client:
        def __init__(self):
            self.calls = []

        def drawings(self, name, page):
            self.calls.append((name, page))
            return {
                "data": [
                    {
                        "id": 8,
                        "number": 5008,
                        "status": "active",
                        "ended_at": "2026-07-14T13:00:00Z",
                    },
                    {
                        "id": 6,
                        "number": 5006,
                        "status": "expected",
                        "ended_at": "2026-07-14T12:30:00Z",
                    },
                    {
                        "id": 5,
                        "number": 5005,
                        "status": "active",
                        "ended_at": "2026-07-14T12:30:00Z",
                    },
                    {
                        "id": 4,
                        "number": 5004,
                        "status": "expected",
                        "ended_at": "2026-07-14T11:30:00Z",
                    },
                    {
                        "id": 3,
                        "number": 5003,
                        "status": "finished",
                        "ended_at": "2026-07-14T12:15:00Z",
                    },
                ]
            }

    client = Client()

    result = resolve_open_drawing_from_api(
        client,
        now="2026-07-14T09:00:00+00:00",
    )

    assert result.drawing_id == 5
    assert result.number == 5005
    assert client.calls == [("baltbet-main", 1)]


def test_resolver_fails_without_a_playable_page_one_row():
    class Client:
        def drawings(self, name, page):
            return {
                "data": [
                    {"id": 1, "status": "active", "ended_at": "2026-07-14T11:00:00Z"},
                    {"id": 2, "status": "finished", "ended_at": "2026-07-14T13:00:00Z"},
                ]
            }

    with pytest.raises(ValueError, match="page one"):
        resolve_open_drawing_from_api(
            Client(),
            now="2026-07-14T12:00:00+00:00",
        )


def test_build_rejects_drawing_info_id_mismatch_before_calculation(
    monkeypatch,
    open_drawing_payload,
):
    import toto_ai.ev.drawing as drawing_module

    open_drawing_payload["data"]["id"] = 9001

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    monkeypatch.setattr(
        drawing_module,
        "compute_ev_components",
        lambda *args, **kwargs: pytest.fail("mismatched input must not be calculated"),
    )

    with pytest.raises(ValueError, match="does not match requested drawing id"):
        build_open_ev_package(
            client=Client(),
            drawing_id=9000,
            config=EVConfig(bank=30),
        )


def test_build_rejects_overflowed_pool_proxy_before_calculation(
    monkeypatch,
    open_drawing_payload,
):
    import toto_ai.ev.drawing as drawing_module

    open_drawing_payload["data"]["pool_sum"] = 1e308

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    monkeypatch.setattr(
        drawing_module,
        "compute_ev_components",
        lambda *args, **kwargs: pytest.fail("invalid proxy must not be calculated"),
    )

    with pytest.raises(ValueError, match="possible_winnings"):
        build_open_ev_package(
            client=Client(),
            drawing_id=9000,
            config=EVConfig(bank=30, prize_fund_factor=2.0),
        )


def _surface(value):
    return EVSurface(
        gross_ev=np.array([value], dtype=np.float64),
        event_count=15,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def _package(config, *, cost, decision=None):
    selected = cost // config.stake
    coupons = tuple(
        RankedCoupon(rank=index + 1, coupon="1" * 15, gross_ev=1.1, net_ev=0.1)
        for index in range(selected)
    )
    return EVPackage(
        decision=decision or ("RESEARCH ONLY" if config.mode == "research" else "PLAY"),
        coupons=coupons,
        cost=cost,
        unused_bank=config.bank - cost,
        expected_payout=cost * 1.1,
        modeled_roi=0.1 if cost else None,
        derived_brief=("1",) * 15,
    )


def _install_fast_ev_engine(monkeypatch):
    import toto_ai.ev.drawing as drawing_module

    monkeypatch.setattr(
        drawing_module,
        "compute_ev_components",
        lambda ev_input, progress_callback=None: EVComponents(
            np.array([1.0]),
            np.array([0.0]),
            15,
            1.0,
            1.0,
            1.0,
        ),
    )
    monkeypatch.setattr(
        drawing_module,
        "materialize_ev_surface",
        lambda components, possible_winnings, jackpot: _surface(possible_winnings),
    )
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package",
        lambda surface, config: _package(config, cost=30),
    )
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        lambda surface, config, diagnostic_limit=20: (
            _package(config, cost=30),
            (
                RankedCoupon(
                    rank=1,
                    coupon="1" * 15,
                    gross_ev=1.1,
                    net_ev=0.1,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        drawing_module,
        "_utc_now",
        lambda: "2026-07-14T12:00:01+00:00",
    )


def _build_fast_run(
    monkeypatch,
    payload,
    *,
    mode="playable",
    timing_resolver=None,
):
    _install_fast_ev_engine(monkeypatch)

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return payload

    return build_open_ev_package(
        client=Client(),
        drawing_id=9000,
        config=EVConfig(
            bank=30,
            stake=30,
            mode=mode,
            prize_fund_factor=0.9,
        ),
        timing_eligibility_resolver=timing_resolver,
    )


def test_effective_budget_caps_capacity_without_replacing_requested_bank():
    config = EVConfig(bank=4980, stake=30, effective_budget=810)

    assert config.requested_bank == 4980
    assert config.selection_budget == 810
    assert config.max_coupons == 27


@pytest.mark.parametrize(
    ("effective_budget", "message"),
    [
        (-30, "non-negative int"),
        (30.0, "non-negative int"),
        (True, "non-negative int"),
        (5_010, "cannot exceed bank"),
        (811, "divisible by stake"),
    ],
)
def test_caller_effective_budget_rejects_invalid_or_misaligned_values(
    effective_budget,
    message,
):
    with pytest.raises(ValueError, match=message):
        EVConfig(bank=4_980, stake=30, effective_budget=effective_budget)


@pytest.mark.parametrize(
    ("pool_sum", "requested_bank", "stake", "expected"),
    [
        (81_445, 4_980, 30, 810),
        (81_445.0, 600, 30, 600),
        (2_999.999, 30, 30, 0),
        (9_007_199_254_742_999, 90_071_992_547_430, 30, 90_071_992_547_400),
    ],
)
def test_effective_budget_uses_exact_stake_aligned_arithmetic(
    pool_sum,
    requested_bank,
    stake,
    expected,
):
    import toto_ai.ev.drawing as drawing_module

    assert (
        drawing_module._effective_budget(
            requested_bank=requested_bank,
            pool_sum=pool_sum,
            stake=stake,
        )
        == expected
    )


@pytest.mark.parametrize(
    "pool_sum",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        -1,
        0,
        10**10_000,
        Decimal("81445"),
        True,
        "81445",
    ],
)
def test_effective_budget_rejects_invalid_pool_values(pool_sum):
    import toto_ai.ev.drawing as drawing_module

    with pytest.raises(ValueError, match="pool_sum"):
        drawing_module._effective_budget(
            requested_bank=4_980,
            pool_sum=pool_sum,
            stake=30,
        )


def test_play_timing_eligibility_is_immutable():
    timing = PlayTimingEligibility(
        status="playable",
        reason="all event starts fit within two Moscow calendar days",
        target_fingerprint="a" * 64,
        fingerprint_match=True,
    )

    with pytest.raises(FrozenInstanceError):
        timing.status = "unknown"

    unfingerprinted = PlayTimingEligibility(
        status="absent",
        reason="fresh timing target could not be parsed or fingerprinted",
        target_fingerprint=None,
        fingerprint_match=False,
    )
    assert unfingerprinted.target_fingerprint is None


def test_timing_resolver_receives_exact_payload_once(
    monkeypatch,
    open_drawing_payload,
):
    received = []

    def resolver(payload):
        received.append(payload)
        return PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="b" * 64,
            fingerprint_match=True,
        )

    result = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        timing_resolver=resolver,
    )

    assert received == [open_drawing_payload]
    assert received[0] is open_drawing_payload
    assert result.timing_eligibility.status == "playable"


def test_playable_timing_verdict_preserves_selected_package(
    monkeypatch,
    open_drawing_payload,
):
    playable = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        timing_resolver=lambda payload: PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="c" * 64,
            fingerprint_match=True,
        ),
    )

    assert playable.package == _package(playable.config, cost=30)
    assert all(row.decision == "PLAY" for row in playable.sensitivity)


def test_final_package_safety_veto_remains_after_safety_aware_selection(
    monkeypatch,
    open_drawing_payload,
):
    import toto_ai.ev.drawing as drawing_module

    _install_fast_ev_engine(monkeypatch)
    selected_probabilities = []

    def unsafe_package(config):
        coupon = RankedCoupon(
            rank=1,
            coupon="1" * 15,
            gross_ev=1.1,
            net_ev=0.1,
        )
        return EVPackage(
            decision="PLAY",
            coupons=(coupon,),
            cost=30,
            unused_bank=config.bank - 30,
            expected_payout=33.0,
            modeled_roi=0.1,
            derived_brief=("1",) * 15,
        )

    def fake_select(surface, config, *, probabilities=None, provenance=None):
        assert provenance is None or isinstance(
            provenance,
            PackageSelectionProvenance,
        )
        selected_probabilities.append(probabilities)
        return unsafe_package(config)

    def fake_select_with_top(
        surface,
        config,
        *,
        probabilities=None,
        provenance=None,
        diagnostic_limit=20,
    ):
        return (
            fake_select(
                surface,
                config,
                probabilities=probabilities,
                provenance=provenance,
            ),
            (),
        )

    monkeypatch.setattr(drawing_module, "select_ev_package", fake_select)
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        fake_select_with_top,
    )

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    result = build_open_ev_package(
        client=Client(),
        drawing_id=9000,
        config=EVConfig(
            bank=30,
            stake=30,
            mode="playable",
            prize_fund_factor=0.9,
            package_safety_enabled=True,
        ),
        timing_eligibility_resolver=lambda payload: PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="c" * 64,
            fingerprint_match=True,
        ),
        fetched_at="2026-08-10T10:00:00+00:00",
    )

    assert selected_probabilities
    assert all(
        probabilities == result.ev_input.true_probabilities
        for probabilities in selected_probabilities
    )
    assert result.package.decision == "NO BET"
    assert result.package.coupons == ()
    assert result.package.decision_reason is not None
    assert result.package.decision_reason.startswith("package_safety:")
    assert result.package_safety is not None
    assert result.package_safety.decision == "NO BET"
    assert result.package_safety.evaluated_coupons == ("1" * 15,)


def test_playable_without_timing_resolver_fails_closed(
    monkeypatch,
    open_drawing_payload,
):
    result = _build_fast_run(monkeypatch, open_drawing_payload)

    assert result.timing_eligibility.status == "not_checked"
    assert result.timing_eligibility.target_fingerprint is None
    assert result.package.decision == "NO BET"
    assert result.package.coupons == ()
    assert result.package.cost == 0
    assert result.package.unused_bank == result.config.bank
    assert result.package.expected_payout == 0.0
    assert result.package.modeled_roi is None
    assert result.package.derived_brief == ()
    assert result.top_coupons
    assert all(row.decision == "NO BET" for row in result.sensitivity)
    assert all(row.selected_count == 0 for row in result.sensitivity)


@pytest.mark.parametrize(
    ("status", "fingerprint_match"),
    [
        ("multi_day", True),
        ("unknown", True),
        ("absent", False),
    ],
)
def test_nonplayable_timing_verdict_suppresses_only_final_playable_output(
    monkeypatch,
    open_drawing_payload,
    status,
    fingerprint_match,
):
    baseline = _build_fast_run(monkeypatch, open_drawing_payload)
    vetoed = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        timing_resolver=lambda payload: PlayTimingEligibility(
            status=status,
            reason=f"timing status is {status}",
            target_fingerprint="d" * 64,
            fingerprint_match=fingerprint_match,
        ),
    )

    assert vetoed.package.decision == "NO BET"
    assert vetoed.package.coupons == ()
    assert vetoed.package.cost == 0
    assert vetoed.package.unused_bank == vetoed.config.bank
    assert vetoed.package.expected_payout == 0.0
    assert vetoed.package.modeled_roi is None
    assert vetoed.package.derived_brief == ()
    assert vetoed.ev_input == baseline.ev_input
    assert vetoed.top_coupons == baseline.top_coupons
    assert np.array_equal(vetoed.surface.gross_ev, baseline.surface.gross_ev)


@pytest.mark.parametrize("status", ["playable", "multi_day", "unknown", "absent"])
def test_research_retains_package_under_every_timing_status(
    monkeypatch,
    open_drawing_payload,
    status,
):
    baseline = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        mode="research",
    )
    resolved = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        mode="research",
        timing_resolver=lambda payload: PlayTimingEligibility(
            status=status,
            reason=f"timing status is {status}",
            target_fingerprint="e" * 64,
            fingerprint_match=status != "absent",
        ),
    )

    assert resolved.package == baseline.package
    assert resolved.package.decision == "RESEARCH ONLY"
    assert resolved.sensitivity == baseline.sensitivity


def test_timing_resolver_cannot_change_ev_inputs_surface_or_ranking(
    monkeypatch,
    open_drawing_payload,
):
    baseline = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        mode="research",
    )

    def resolver(payload):
        for event in payload["data"]["events"]:
            event["external_consensus"] = (0.01, 0.01, 0.98)
            event["fallback_probabilities"] = (0.98, 0.01, 0.01)
        return PlayTimingEligibility(
            status="unknown",
            reason="external timing is unresolved",
            target_fingerprint="f" * 64,
            fingerprint_match=True,
        )

    resolved = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        mode="research",
        timing_resolver=resolver,
    )

    assert resolved.ev_input == baseline.ev_input
    assert resolved.ev_input.probability_sources == ("totobrief_bk",) * 15
    assert resolved.top_coupons == baseline.top_coupons
    assert np.array_equal(resolved.surface.gross_ev, baseline.surface.gross_ev)


def test_timing_veto_suppresses_playable_sensitivity_labels(
    monkeypatch,
    open_drawing_payload,
):
    result = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        timing_resolver=lambda payload: PlayTimingEligibility(
            status="multi_day",
            reason="event span exceeds two Moscow calendar days",
            target_fingerprint="0" * 64,
            fingerprint_match=True,
        ),
    )

    assert all(row.decision == "NO BET" for row in result.sensitivity)
    assert all(row.selected_count == 0 for row in result.sensitivity)
    assert all(row.cost == 0 for row in result.sensitivity)
    assert all(row.unused_bank == result.config.bank for row in result.sensitivity)


@pytest.mark.parametrize(
    ("mode", "expected_decision"),
    [("research", "RESEARCH ONLY"), ("playable", "NO BET")],
)
def test_timing_parse_failure_is_conservative_without_aborting_ev(
    monkeypatch,
    tmp_path,
    open_drawing_payload,
    mode,
    expected_decision,
):
    resolver = cli_module._build_timing_eligibility_resolver(
        str(tmp_path / "missing.sqlite")
    )

    result = _build_fast_run(
        monkeypatch,
        open_drawing_payload,
        mode=mode,
        timing_resolver=resolver,
    )

    assert result.timing_eligibility.status == "absent"
    assert result.timing_eligibility.target_fingerprint is None
    assert result.timing_eligibility.fingerprint_match is False
    assert result.timing_eligibility.reason == (
        "fresh timing target could not be parsed or fingerprinted"
    )
    assert result.package.decision == expected_decision
    assert result.ev_input.probability_sources == ("totobrief_bk",) * 15
    if mode == "research":
        assert result.package.coupons
        assert result.top_coupons
    else:
        assert result.package.coupons == ()
        assert all(row.decision == "NO BET" for row in result.sensitivity)


@pytest.mark.parametrize(
    (
        "mode",
        "pool_sum",
        "jackpot_override",
        "expected_jackpot_source",
        "expected_effective_budget",
        "expected_decision",
    ),
    [
        ("playable", 3_000.0, None, "totobrief payload", 30, "PLAY"),
        ("playable", 2_999.999, 800.0, "explicit override", 0, "NO BET"),
        ("research", 2_999.999, None, "totobrief payload", 0, "NO BET"),
    ],
)
def test_build_package_uses_stake_aligned_self_dilution_budget(
    monkeypatch,
    open_drawing_payload,
    mode,
    pool_sum,
    jackpot_override,
    expected_jackpot_source,
    expected_effective_budget,
    expected_decision,
):
    import toto_ai.ev.drawing as drawing_module

    open_drawing_payload["data"]["pool_sum"] = pool_sum

    class Client:
        def __init__(self):
            self.calls = []

        def drawing_info(self, drawing_id):
            self.calls.append(drawing_id)
            return open_drawing_payload

    client = Client()
    component_calls = []
    materialized = []
    selected_configs = []
    surface_references = []
    live_surface_counts = []

    def fake_components(ev_input, progress_callback=None):
        component_calls.append(ev_input)
        return EVComponents(np.array([1.0]), np.array([0.0]), 15, 1.0, 1.0, 1.0)

    def fake_materialize(components, possible_winnings, jackpot):
        materialized.append((possible_winnings, jackpot))
        surface = _surface(possible_winnings)
        surface_references.append(weakref.ref(surface))
        return surface

    def fake_select(surface, config):
        gc.collect()
        live_surface_counts.append(
            sum(reference() is not None for reference in surface_references)
        )
        selected_configs.append(config)
        return _package(config, cost=min(30, config.selection_budget))

    def fake_select_with_top(surface, config, diagnostic_limit=20):
        return fake_select(surface, config), ()

    monkeypatch.setattr(drawing_module, "compute_ev_components", fake_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", fake_materialize)
    monkeypatch.setattr(drawing_module, "select_ev_package", fake_select)
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        fake_select_with_top,
    )
    monkeypatch.setattr(drawing_module, "_utc_now", lambda: "2026-07-14T12:00:01+00:00")

    def playable_timing(payload):
        return PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="a" * 64,
            fingerprint_match=True,
        )

    timing_resolver = None if mode == "research" else playable_timing

    result = build_open_ev_package(
        client=client,
        drawing_id=9000,
        config=EVConfig(bank=30, stake=30, mode=mode, prize_fund_factor=0.9),
        jackpot_override=jackpot_override,
        timing_eligibility_resolver=timing_resolver,
    )

    assert client.calls == [9000]
    assert result.ev_input.fetched_at == "2026-07-14T12:00:01+00:00"
    assert len(component_calls) == 1
    assert [row.prize_fund_factor for row in result.sensitivity] == [
        0.70,
        0.80,
        0.90,
        1.00,
    ]
    assert result.requested_bank == 30
    assert result.config.bank == 30
    assert result.effective_budget == expected_effective_budget
    assert result.config.effective_budget == expected_effective_budget
    assert result.selected_cost == (30 if expected_effective_budget else 0)
    assert result.unused_requested_bank == 30 - result.selected_cost
    assert result.self_dilution_ratio == pytest.approx(result.selected_cost / pool_sum)
    assert result.model_supported is True
    assert result.package.decision == expected_decision
    assert result.jackpot_source == expected_jackpot_source
    assert result.ev_input.jackpot == (
        1_200.0 if jackpot_override is None else jackpot_override
    )
    assert len(materialized) == 4
    assert len(selected_configs) == 4
    assert all(config.bank == 30 for config in selected_configs)
    assert all(
        config.effective_budget == expected_effective_budget
        for config in selected_configs
    )
    assert max(live_surface_counts) <= 2
    if expected_effective_budget < result.config.stake:
        reason = (
            "Effective budget 0 RUB is below one coupon stake 30 RUB after "
            "applying the 1% self-dilution support limit to requested bank "
            "30 RUB; no supported coupon can be selected."
        )
        assert result.package.coupons == ()
        assert result.package.cost == 0
        assert result.package.unused_bank == result.config.bank
        assert result.package.expected_payout == 0.0
        assert result.package.modeled_roi is None
        assert result.package.derived_brief == ()
        assert result.package.decision_reason == reason
        assert result.model_warning == reason
        assert all(row.selected_count == 0 for row in result.sensitivity)
        assert all(row.cost == 0 for row in result.sensitivity)
        assert all(row.unused_bank == result.config.bank for row in result.sensitivity)
    else:
        assert result.package.decision_reason is None
        assert result.model_warning is None


def test_requested_bank_above_support_cap_selects_with_effective_budget(
    monkeypatch,
    open_drawing_payload,
):
    import toto_ai.ev.drawing as drawing_module

    open_drawing_payload["data"]["pool_sum"] = 81_445.0
    selected_configs = []

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    monkeypatch.setattr(
        drawing_module,
        "compute_ev_components",
        lambda ev_input, progress_callback=None: EVComponents(
            np.array([1.0]),
            np.array([0.0]),
            15,
            1.0,
            1.0,
            1.0,
        ),
    )
    monkeypatch.setattr(
        drawing_module,
        "materialize_ev_surface",
        lambda components, possible_winnings, jackpot: _surface(possible_winnings),
    )

    def fake_select(surface, config):
        selected_configs.append(config)
        return _package(config, cost=config.max_coupons * config.stake)

    monkeypatch.setattr(drawing_module, "select_ev_package", fake_select)
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        lambda surface, config, diagnostic_limit=20: (fake_select(surface, config), ()),
    )

    result = build_open_ev_package(
        client=Client(),
        drawing_id=9000,
        config=EVConfig(
            bank=4980,
            stake=30,
            mode="playable",
            prize_fund_factor=0.9,
        ),
        timing_eligibility_resolver=lambda payload: PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="b" * 64,
            fingerprint_match=True,
        ),
        fetched_at="2026-07-20T12:00:00+00:00",
    )

    assert result.config.bank == 4980
    assert result.requested_bank == 4980
    assert result.effective_budget == 810
    assert result.config.effective_budget == 810
    assert all(config.bank == 4980 for config in selected_configs)
    assert all(config.effective_budget == 810 for config in selected_configs)
    assert all(config.max_coupons == 27 for config in selected_configs)
    assert result.package.decision == "PLAY"
    assert result.package.cost == 810
    assert result.package.cost <= result.effective_budget
    assert result.package.unused_bank == 4170
    assert result.unused_requested_bank == 4170
    assert result.self_dilution_ratio == pytest.approx(810 / 81_445)
    assert result.model_supported is True
    assert result.model_warning is None


@pytest.mark.parametrize(
    ("caller_cap", "expected_budget", "expected_decision"),
    [
        pytest.param(0, 0, "NO BET", id="below-stake"),
        pytest.param(600, 600, "PLAY", id="below-derived-cap"),
        pytest.param(810, 810, "PLAY", id="equal-derived-cap"),
        pytest.param(900, 810, "PLAY", id="above-derived-cap"),
    ],
)
def test_build_uses_strictest_caller_and_derived_effective_budget(
    monkeypatch,
    open_drawing_payload,
    caller_cap,
    expected_budget,
    expected_decision,
):
    import toto_ai.ev.drawing as drawing_module

    open_drawing_payload["data"]["pool_sum"] = 81_445
    selected_configs = []

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    monkeypatch.setattr(
        drawing_module,
        "compute_ev_components",
        lambda ev_input, progress_callback=None: EVComponents(
            np.array([1.0]),
            np.array([0.0]),
            15,
            1.0,
            1.0,
            1.0,
        ),
    )
    monkeypatch.setattr(
        drawing_module,
        "materialize_ev_surface",
        lambda components, possible_winnings, jackpot: _surface(possible_winnings),
    )

    def fake_select(surface, config):
        selected_configs.append(config)
        return _package(config, cost=config.selection_budget)

    monkeypatch.setattr(drawing_module, "select_ev_package", fake_select)
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        lambda surface, config, diagnostic_limit=20: (fake_select(surface, config), ()),
    )

    caller_config = EVConfig(
        bank=4_980,
        stake=30,
        mode="playable",
        prize_fund_factor=0.9,
        effective_budget=caller_cap,
    )
    result = build_open_ev_package(
        client=Client(),
        drawing_id=9000,
        config=caller_config,
        timing_eligibility_resolver=lambda payload: PlayTimingEligibility(
            status="playable",
            reason="stored eligibility matches the fresh target",
            target_fingerprint="c" * 64,
            fingerprint_match=True,
        ),
        fetched_at="2026-07-20T12:00:00+00:00",
    )

    assert caller_config.effective_budget == caller_cap
    assert result.requested_bank == 4_980
    assert result.effective_budget == expected_budget
    assert result.config.effective_budget == expected_budget
    assert all(
        config.effective_budget == expected_budget for config in selected_configs
    )
    assert all(
        config.selection_budget == expected_budget for config in selected_configs
    )
    assert result.package.decision == expected_decision
    assert result.package.cost == expected_budget
    assert result.package.unused_bank == 4_980 - expected_budget
    if expected_budget == 0:
        assert result.package.coupons == ()
        assert result.package.expected_payout == 0.0
        assert result.package.modeled_roi is None
        assert all(row.decision == "NO BET" for row in result.sensitivity)


def test_build_preserves_exact_integer_pool_for_effective_budget(
    monkeypatch,
    open_drawing_payload,
):
    exact_pool_sum = 9_007_199_254_742_999
    rounded_up_float_cap = 90_071_992_547_430
    exact_cap = 90_071_992_547_400
    open_drawing_payload["data"]["pool_sum"] = exact_pool_sum
    _install_fast_ev_engine(monkeypatch)

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 9000
            return open_drawing_payload

    result = build_open_ev_package(
        client=Client(),
        drawing_id=9000,
        config=EVConfig(
            bank=rounded_up_float_cap,
            stake=30,
            mode="research",
            prize_fund_factor=0.9,
        ),
    )

    assert result.requested_bank == rounded_up_float_cap
    assert result.effective_budget == exact_cap
    assert result.config.effective_budget == exact_cap
    assert result.effective_budget != rounded_up_float_cap


def test_cli_requires_open():
    result = CliRunner().invoke(app, ["ev-package", "--bank", "6000"])

    assert result.exit_code == 2
    assert "--open is required" in result.stderr


def test_cli_rejects_invalid_mode_before_api_access(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "TotoBriefClient",
        lambda: pytest.fail("invalid mode must fail before API access"),
    )

    result = CliRunner().invoke(
        app,
        ["ev-package", "--open", "--mode", "invalid", "--bank", "6000"],
    )

    assert result.exit_code == 2
    assert "mode must be 'research' or 'playable'" in result.stderr


def test_cli_interruption_never_prints_play(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "resolve_open_drawing_from_api",
        lambda client: type("Reference", (), {"drawing_id": 9000})(),
    )
    monkeypatch.setattr(
        cli_module,
        "build_open_ev_package",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    result = CliRunner().invoke(
        app,
        ["ev-package", "--open", "--mode", "playable", "--bank", "6000"],
    )

    assert result.exit_code == 2
    assert "interrupted" in result.stderr.lower()
    assert "PLAY" not in result.output


def test_cli_converts_numeric_overflow_to_bad_parameter(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "resolve_open_drawing_from_api",
        lambda client: type("Reference", (), {"drawing_id": 9000})(),
    )
    monkeypatch.setattr(
        cli_module,
        "build_open_ev_package",
        lambda **kwargs: (_ for _ in ()).throw(OverflowError("numeric overflow")),
    )

    result = CliRunner().invoke(
        app,
        ["ev-package", "--open", "--mode", "playable", "--bank", "6000"],
    )

    assert result.exit_code == 2
    assert "numeric overflow" in result.stderr
    assert "PLAY" not in result.output


def test_cli_prints_snapshot_package_top_coupons_and_report_paths(
    monkeypatch,
    open_drawing_payload,
):
    config = EVConfig(bank=30, stake=30, mode="playable")
    ev_input = ev_input_from_payload(
        open_drawing_payload,
        fetched_at="2026-07-14T12:00:00+00:00",
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    package = _package(config, cost=0, decision="NO BET")
    top_coupon = RankedCoupon(
        rank=1,
        coupon="1" * 15,
        gross_ev=0.9,
        net_ev=-0.1,
    )
    run = EVPackageRun(
        config=config,
        ev_input=ev_input,
        surface=_surface(0.9),
        package=package,
        top_coupons=(top_coupon,),
        sensitivity=(),
        possible_winnings_source="pool_sum proxy",
        jackpot_source="totobrief payload",
        self_dilution_ratio=0.0,
        model_supported=True,
        model_warning=None,
        timing_eligibility=PlayTimingEligibility(
            status="multi_day",
            reason="effective event starts span three Moscow calendar days",
            target_fingerprint="a" * 64,
            fingerprint_match=True,
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "resolve_open_drawing_from_api",
        lambda client: type("Reference", (), {"drawing_id": 9000})(),
    )
    build_calls = []

    def build_package(**kwargs):
        build_calls.append(kwargs)
        return run

    monkeypatch.setattr(cli_module, "build_open_ev_package", build_package)
    readonly_calls = []
    readonly_engine = object()
    session_factory = object()
    monkeypatch.setattr(
        cli_module,
        "open_readonly_db",
        lambda db: readonly_calls.append(db) or readonly_engine,
    )
    monkeypatch.setattr(
        cli_module,
        "get_session_factory",
        lambda engine: session_factory if engine is readonly_engine else None,
    )
    monkeypatch.setattr(
        cli_module,
        "init_db",
        lambda *args, **kwargs: pytest.fail("ev-package must never initialize a DB"),
    )
    monkeypatch.setattr(
        cli_module,
        "write_ev_package_reports",
        lambda result: (Path("package.csv"), Path("package.md")),
    )

    result = CliRunner().invoke(
        app,
        [
            "ev-package",
            "--open",
            "--mode",
            "playable",
            "--bank",
            "30",
            "--db",
            "readonly.sqlite",
        ],
    )

    assert result.exit_code == 0
    assert build_calls[0]["config"].package_provenance_required is True
    assert readonly_calls == ["readonly.sqlite"]
    for expected in (
        "EV Input Snapshot",
        "EV Package Summary",
        "Top 20 EV Coupons",
        "NO BET",
        "Timing-veto diagnostics are suppressed in playable mode.",
        "package.csv",
        "package.md",
    ):
        assert expected in result.stdout
    assert top_coupon.coupon not in result.stdout


def test_cli_help_lists_the_exact_task_options():
    result = CliRunner().invoke(app, ["ev-package", "--help"])

    assert result.exit_code == 0
    for option in (
        "--open",
        "--mode",
        "--bank",
        "--stake",
        "--min-gross-ev",
        "--prize-fund-factor",
        "--possible-winnings",
        "--jackpot",
        "--db",
    ):
        assert option in result.stdout
