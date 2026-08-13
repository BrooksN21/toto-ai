from __future__ import annotations

from pathlib import Path

import pytest

from toto_ai.runner.scheduler import (
    SchedulerIntegrityError,
    render_paper_package,
    validate_paper_package,
)


def test_render_paper_package_is_exact_baltbet_text_without_metadata() -> None:
    coupons = ("1X2" * 5, "2X1" * 5)

    payload = render_paper_package(coupons, stake=30)

    assert payload == (
        b"30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2\n"
        b"30; 2; X; 1; 2; X; 1; 2; X; 1; 2; X; 1; 2; X; 1\n"
    )
    assert payload.endswith(b"\n")
    assert b"\r" not in payload
    assert b"\x00" not in payload
    assert b"rank" not in payload
    assert b"gross_ev" not in payload
    assert b"net_ev" not in payload
    assert b"PAPER" not in payload


def test_render_paper_package_preserves_source_order_and_allows_empty() -> None:
    coupons = ("2" * 15, "1" * 15, "X" * 15)

    payload = render_paper_package(coupons, stake=60)
    summary = validate_paper_package(
        payload,
        stake=60,
        expected_coupons=coupons,
        expected_count=3,
        expected_cost=180,
    )

    assert summary.coupons == coupons
    assert summary.count == 3
    assert summary.cost == 180
    assert render_paper_package((), stake=60) == b""
    empty = validate_paper_package(
        b"",
        stake=60,
        expected_coupons=(),
        expected_count=0,
        expected_cost=0,
    )
    assert empty.count == 0
    assert empty.cost == 0


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"30; 1; X\n", "15 outcomes"),
        (b"30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; Z\n", "outcomes"),
        (b"30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2", "line encoding"),
        (b"30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2\r\n", "line encoding"),
        (b"30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2\x00\n", "line encoding"),
        (b"31; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2\n", "<stake>"),
    ),
)
def test_validate_paper_package_rejects_malformed_payload(
    payload: bytes,
    message: str,
) -> None:
    with pytest.raises(SchedulerIntegrityError, match=message):
        validate_paper_package(
            payload,
            stake=30,
            expected_coupons=("1X2" * 5,),
            expected_count=1,
            expected_cost=30,
        )


def test_paper_validation_fails_closed_on_order_count_cost_or_duplicates() -> None:
    coupons = ("1" * 15, "2" * 15)
    payload = render_paper_package(coupons, stake=30)

    with pytest.raises(SchedulerIntegrityError, match="order"):
        validate_paper_package(
            payload,
            stake=30,
            expected_coupons=tuple(reversed(coupons)),
            expected_count=2,
            expected_cost=60,
        )
    with pytest.raises(SchedulerIntegrityError, match="count"):
        validate_paper_package(
            payload,
            stake=30,
            expected_coupons=coupons,
            expected_count=1,
            expected_cost=30,
        )
    with pytest.raises(SchedulerIntegrityError, match="cost"):
        validate_paper_package(
            payload,
            stake=30,
            expected_coupons=coupons,
            expected_count=2,
            expected_cost=90,
        )
    duplicate = payload.splitlines(keepends=True)[0] * 2
    with pytest.raises(SchedulerIntegrityError, match="unique"):
        validate_paper_package(
            duplicate,
            stake=30,
            expected_coupons=(coupons[0], coupons[0]),
            expected_count=2,
            expected_cost=60,
        )


def test_renderer_rejects_invalid_stake_coupon_and_duplicates() -> None:
    with pytest.raises(ValueError, match="positive"):
        render_paper_package(("1" * 15,), stake=0)
    with pytest.raises(SchedulerIntegrityError, match="15 outcomes"):
        render_paper_package(("1" * 14,), stake=30)
    with pytest.raises(SchedulerIntegrityError, match="unique"):
        render_paper_package(("1" * 15, "1" * 15), stake=30)


def test_known_4974_paper_payload_is_166_unique_non_actionable_lines() -> None:
    project_root = Path(__file__).resolve().parents[1]
    paper_path = project_root / (
        "reports/rehearsal/evening-4974-recovery-20260813T1330Z/"
        "paper-package-4974-baltbet-format.txt"
    )
    if not paper_path.is_file():
        pytest.skip("local historical 4974 paper artifact is not present")

    payload = paper_path.read_bytes()
    coupons = tuple(
        "".join(line.split("; ")[1:])
        for line in payload.decode("utf-8").splitlines()
    )
    summary = validate_paper_package(
        payload,
        stake=30,
        expected_coupons=coupons,
        expected_count=166,
        expected_cost=4980,
    )

    assert summary.count == 166
    assert summary.cost == 4980
    assert len(set(summary.coupons)) == 166
    assert not (paper_path.parent / ".bet-ready").exists()
