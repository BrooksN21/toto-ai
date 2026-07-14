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
    RankedCoupon,
)


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
            lambda data: data["events"][0]["quotes"].__setitem__(
                "pool_draw", None
            ),
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
        now="2026-07-14T12:00:00+00:00",
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


@pytest.mark.parametrize(
    ("mode", "pool_sum", "expected_supported", "expected_decision"),
    [
        ("playable", 3_000.0, True, "PLAY"),
        ("playable", 2_999.999, False, "NO BET"),
        ("research", 2_999.999, False, "RESEARCH ONLY"),
    ],
)
def test_build_package_enforces_self_dilution_boundary(
    monkeypatch,
    open_drawing_payload,
    mode,
    pool_sum,
    expected_supported,
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

    def fake_components(ev_input, progress_callback=None):
        component_calls.append(ev_input)
        return EVComponents(np.array([1.0]), np.array([0.0]), 15, 1.0, 1.0, 1.0)

    def fake_materialize(components, possible_winnings, jackpot):
        materialized.append((possible_winnings, jackpot))
        return _surface(possible_winnings)

    def fake_select(surface, config):
        selected_configs.append(config)
        return _package(config, cost=30)

    monkeypatch.setattr(drawing_module, "compute_ev_components", fake_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", fake_materialize)
    monkeypatch.setattr(drawing_module, "select_ev_package", fake_select)
    monkeypatch.setattr(drawing_module, "_top_coupons", lambda surface, limit=20: ())
    monkeypatch.setattr(drawing_module, "_utc_now", lambda: "2026-07-14T12:00:01+00:00")

    result = build_open_ev_package(
        client=client,
        drawing_id=9000,
        config=EVConfig(bank=30, stake=30, mode=mode, prize_fund_factor=0.9),
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
    assert result.self_dilution_ratio == pytest.approx(30 / pool_sum)
    assert result.model_supported is expected_supported
    assert result.package.decision == expected_decision
    assert len(materialized) == 4
    assert len(selected_configs) == 4


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
        self_dilution_ratio=0.0,
        model_supported=True,
        model_warning=None,
    )
    monkeypatch.setattr(
        cli_module,
        "resolve_open_drawing_from_api",
        lambda client: type("Reference", (), {"drawing_id": 9000})(),
    )
    monkeypatch.setattr(cli_module, "build_open_ev_package", lambda **kwargs: run)
    monkeypatch.setattr(
        cli_module,
        "write_ev_package_reports",
        lambda result: (Path("package.csv"), Path("package.md")),
    )

    result = CliRunner().invoke(
        app,
        ["ev-package", "--open", "--mode", "playable", "--bank", "30"],
    )

    assert result.exit_code == 0
    for expected in (
        "EV Input Snapshot",
        "EV Package Summary",
        "Top 20 EV Coupons",
        "NO BET",
        "package.csv",
        "package.md",
    ):
        assert expected in result.stdout


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
    ):
        assert option in result.stdout
