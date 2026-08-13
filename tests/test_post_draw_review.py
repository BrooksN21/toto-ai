import hashlib
import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.operations.finished_draw import (
    complete_post_draw_review,
    create_review_request,
    load_review_request,
    transition_review_request,
)


def _settlement_payload():
    return {
        "settlement_sha256": "a" * 64,
        "snapshot_sha256": "b" * 64,
        "package_sha256": "c" * 64,
        "actual": "1X2" * 5,
        "void_event_orders": (15,),
        "hit_distribution": {13: 2, 14: 1, 15: 0},
        "best_hits": 14,
        "best_coupon_ranks": (7,),
        "category_counts": {13: 2, 14: 1, 15: 0},
        "cost": 4980,
        "fixed_miss_events": (4,),
        "zero_exposure_miss_events": (9,),
        "known_return": None,
        "roi": None,
        "return_status": "official_payments_unavailable",
    }


def test_review_request_is_durable_and_notification_is_advisory(tmp_path):
    calls = []

    def failing_notification(message):
        calls.append(message)
        raise RuntimeError("notification unavailable")

    path = tmp_path / "review-request.json"
    request = create_review_request(
        path,
        drawing_id=12001,
        drawing_number=5001,
        package_kind="package",
        settlement=_settlement_payload(),
        requested_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
        notifier=failing_notification,
    )
    assert request["status"] == "AWAITING_USER_REVIEW"
    assert request["question"] == "Разбираем пакет тиража 5001?"
    assert request["best_hits"] == 14
    assert request["fixed_miss_events"] == [4]
    assert request["zero_exposure_miss_events"] == [9]
    assert request["void_event_orders"] == [15]
    assert request["notification"]["status"] == "failed"
    assert calls == ["Разбираем пакет тиража 5001?"]
    assert load_review_request(path) == request
    assert create_review_request(
        path,
        drawing_id=12001,
        drawing_number=5001,
        package_kind="package",
        settlement=_settlement_payload(),
        requested_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
    ) == request


def test_review_transitions_and_immutable_postmortem(tmp_path):
    request_path = tmp_path / "review-request.json"
    create_review_request(
        request_path,
        drawing_id=12001,
        drawing_number=5001,
        package_kind="package",
        settlement=_settlement_payload(),
        requested_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
    )
    requested = transition_review_request(
        request_path,
        transition="request",
        transitioned_at=datetime(2026, 8, 14, 10, tzinfo=timezone.utc),
    )
    assert requested["status"] == "REVIEW_REQUESTED"
    with pytest.raises(ValueError, match="transition"):
        transition_review_request(
            request_path,
            transition="skip",
            transitioned_at=datetime(2026, 8, 14, 10, tzinfo=timezone.utc),
        )

    postmortem = tmp_path / "postmortem.md"
    complete = complete_post_draw_review(
        request_path,
        postmortem_path=postmortem,
        completed_at=datetime(2026, 8, 14, 11, tzinfo=timezone.utc),
    )
    assert complete["status"] == "REVIEW_COMPLETE"
    assert complete["postmortem_sha256"] == hashlib.sha256(
        postmortem.read_bytes()
    ).hexdigest()
    text = postmortem.read_text()
    assert "# Post-draw review: drawing 5001" in text
    assert "one drawing cannot establish causality or profitability" in text
    assert "BK / pool / Pin / sports-shadow" in text
    assert complete_post_draw_review(
        request_path,
        postmortem_path=postmortem,
        completed_at=datetime(2026, 8, 14, 11, tzinfo=timezone.utc),
    ) == complete
    postmortem.write_text("tampered\n")
    with pytest.raises(ValueError, match="postmortem hash"):
        load_review_request(request_path)


def test_review_status_cli_lists_unacknowledged_and_transitions(tmp_path):
    request_path = tmp_path / "review-request.json"
    create_review_request(
        request_path,
        drawing_id=12001,
        drawing_number=5001,
        package_kind="package_free_no_bet",
        settlement=None,
        snapshot_sha256="b" * 64,
        actual="1X2" * 5,
        void_event_orders=(),
        requested_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
    )
    runner = CliRunner()
    status = runner.invoke(
        cli.app,
        ["post-draw-review-status", "--request-file", str(request_path)],
    )
    assert status.exit_code == 0
    payload = json.loads(status.stdout)
    assert payload["unacknowledged"] is True
    assert payload["question"] == "Разбираем пакет тиража 5001?"

    accepted = runner.invoke(
        cli.app,
        [
            "post-draw-review-transition",
            "--request-file",
            str(request_path),
            "--action",
            "request",
            "--at",
            "2026-08-14T10:00:00+00:00",
        ],
    )
    assert accepted.exit_code == 0
    assert json.loads(accepted.stdout)["status"] == "REVIEW_REQUESTED"
