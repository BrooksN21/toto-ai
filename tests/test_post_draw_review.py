import hashlib
import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.operations.finished_draw import (
    complete_post_draw_review,
    create_review_request,
    load_post_draw_delivery,
    load_review_request,
    record_post_draw_delivery_receipt,
    retry_post_draw_delivery,
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
    assert len(calls) == 1
    assert calls[0].startswith("Тираж 5001: лучший купон 14/15")
    assert "postmortem.md" in calls[0]
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


def test_completed_review_delivery_requires_receipt_and_is_retryable(tmp_path):
    request_path = tmp_path / "review-request.json"
    sent = []
    create_review_request(
        request_path,
        drawing_id=12001,
        drawing_number=5001,
        package_kind="package",
        settlement=_settlement_payload(),
        requested_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
        notifier=sent.append,
    )
    request = transition_review_request(
        request_path,
        transition="request",
        transitioned_at=datetime(2026, 8, 14, 10, tzinfo=timezone.utc),
    )
    request = complete_post_draw_review(
        request_path,
        postmortem_path=tmp_path / "postmortem.md",
        completed_at=datetime(2026, 8, 14, 11, tzinfo=timezone.utc),
    )

    delivery = load_post_draw_delivery(request_path)
    assert request["notification"]["status"] == "sent"
    assert delivery["status"] == "pending"
    assert delivery["reason"] == "OWNER_RECEIPT_REQUIRED"
    assert delivery["retryable"] is True
    assert delivery["receipt"] is None
    assert delivery["attempts"][0]["transport_status"] == "sent"
    status = CliRunner().invoke(
        cli.app,
        ["post-draw-review-status", "--request-file", str(request_path)],
    )
    assert status.exit_code == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["owner_delivery_status"] == "pending"
    assert status_payload["owner_delivered"] is False
    assert status_payload["delivery_retryable"] is True
    assert status_payload["delivery_record_sha256"] == delivery["record_sha256"]

    def fail(_message):
        raise RuntimeError("delivery channel unavailable")

    delivery = retry_post_draw_delivery(
        request_path,
        attempted_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        notifier=fail,
    )
    assert delivery["status"] == "failed"
    assert delivery["reason"] == "DELIVERY_ATTEMPT_FAILED"
    assert delivery["retryable"] is True
    assert delivery["attempts"][-1]["transport_status"] == "failed"

    delivery = retry_post_draw_delivery(
        request_path,
        attempted_at=datetime(2026, 8, 14, 13, tzinfo=timezone.utc),
        notifier=sent.append,
    )
    assert delivery["status"] == "pending"
    assert delivery["reason"] == "OWNER_RECEIPT_REQUIRED"
    assert delivery["attempts"][-1]["transport_status"] == "sent"

    receipt = {
        "schema_version": 1,
        "drawing_id": 12001,
        "drawing_number": 5001,
        "review_request_sha256": request["request_sha256"],
        "postmortem_sha256": request["postmortem_sha256"],
        "channel": "codex_thread",
        "receipt_id": "message-5001",
        "delivered_at": "2026-08-14T13:05:00+00:00",
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    receipt_path = tmp_path / "owner-delivery-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    delivered = record_post_draw_delivery_receipt(
        request_path,
        receipt_path=receipt_path,
        recorded_at=datetime(2026, 8, 14, 13, 6, tzinfo=timezone.utc),
    )
    assert delivered["status"] == "delivered"
    assert delivered["retryable"] is False
    assert delivered["receipt"]["receipt_sha256"] == receipt["receipt_sha256"]


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
