from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_external_odds_audit import _collection
from tests.test_external_odds_storage import target_drawing
from toto_ai.external_odds.the_odds_api import CreditState
from toto_ai.external_odds.the_odds_checkpoints import collect_shadow_checkpoint


class FakeProvider:
    request_evidence = ()
    credits_spent = 2
    credit_state = CreditState(498, 2, 1)

    def refresh_credit_state(self) -> CreditState:
        return self.credit_state


def test_checkpoint_is_idempotent_and_does_not_construct_provider_twice(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import toto_ai.external_odds.the_odds_checkpoints as checkpoints

    target = target_drawing()
    snapshot = replace(
        _collection(1, ()),
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider="the-odds-api",
    )
    provider_calls = 0
    collect_calls = 0

    def provider_factory():
        nonlocal provider_calls
        provider_calls += 1
        return FakeProvider()

    def fake_collect(*args, **kwargs):
        nonlocal collect_calls
        collect_calls += 1
        return snapshot

    report_root = tmp_path / "reports"

    def fake_reports(*args, **kwargs):
        drawing_dir = report_root / str(target.drawing_number)
        drawing_dir.mkdir(parents=True, exist_ok=True)
        paths = type(
            "Paths",
            (),
            {
                "json_path": drawing_dir / "shadow.json",
                "csv_path": drawing_dir / "shadow.csv",
                "markdown_path": drawing_dir / "shadow.md",
            },
        )()
        paths.json_path.write_text("{}\n", encoding="utf-8")
        paths.csv_path.write_text("event\n", encoding="utf-8")
        paths.markdown_path.write_text("# shadow\n", encoding="utf-8")
        return paths

    monkeypatch.setattr(checkpoints, "collect_target_external_odds", fake_collect)
    monkeypatch.setattr(
        checkpoints,
        "write_the_odds_shadow_reports",
        fake_reports,
    )

    first = collect_shadow_checkpoint(
        target=target,
        checkpoint="morning",
        provider_factory=provider_factory,
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_root,
    )
    second = collect_shadow_checkpoint(
        target=target,
        checkpoint="morning",
        provider_factory=provider_factory,
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_root,
    )

    assert first.reused is False
    assert second.reused is True
    assert first.status == "COLLECTED"
    assert second.status == "COLLECTED"
    assert first.credits_spent_this_run == 2
    assert second.credits_spent_this_run == 0
    assert provider_calls == 1
    assert collect_calls == 1
    assert second.checkpoint_id == first.checkpoint_id
    payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert payload["checkpoint"] == "morning"
    assert payload["activation_status"] == "NOT_ACTIVATED"
    assert payload["actionable"] is False
    assert payload["credits_spent"] == 2


def test_checkpoint_skips_before_collection_when_quota_reserve_is_reached(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import toto_ai.external_odds.the_odds_checkpoints as checkpoints

    class ReserveProvider:
        request_evidence = ()
        credits_spent = 0
        credit_state = CreditState(50, 450, 0)

        def refresh_credit_state(self) -> CreditState:
            return self.credit_state

    collect_calls = 0

    def forbidden_collect(*args, **kwargs):
        nonlocal collect_calls
        collect_calls += 1
        raise AssertionError("collection must not start at the quota reserve")

    monkeypatch.setattr(
        checkpoints,
        "collect_target_external_odds",
        forbidden_collect,
    )
    report_dir = tmp_path / "reports"
    first = collect_shadow_checkpoint(
        target=target_drawing(),
        checkpoint="control",
        provider_factory=ReserveProvider,
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_dir,
    )
    second = collect_shadow_checkpoint(
        target=target_drawing(),
        checkpoint="control",
        provider_factory=lambda: (_ for _ in ()).throw(
            AssertionError("reused checkpoint must not construct provider")
        ),
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_dir,
    )

    assert collect_calls == 0
    assert first.status == "SKIPPED_QUOTA_RESERVE"
    assert first.collection_id is None
    assert first.credits_spent == 0
    assert first.credits_spent_this_run == 0
    assert first.reused is False
    assert second.status == "SKIPPED_QUOTA_RESERVE"
    assert second.collection_id is None
    assert second.credits_spent_this_run == 0
    assert second.reused is True
    payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert payload["status"] == "SKIPPED_QUOTA_RESERVE"
    assert payload["credits_remaining"] == 50
    assert payload["evidence"] == {}


def test_checkpoint_input_change_conflicts_instead_of_overwriting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import toto_ai.external_odds.the_odds_checkpoints as checkpoints

    target = target_drawing()
    snapshot = replace(
        _collection(1, ()),
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider="the-odds-api",
    )
    monkeypatch.setattr(
        checkpoints,
        "collect_target_external_odds",
        lambda *args, **kwargs: snapshot,
    )

    def fake_reports(*args, **kwargs):
        root = tmp_path / "reports" / str(target.drawing_number)
        root.mkdir(parents=True, exist_ok=True)
        paths = type(
            "Paths",
            (),
            {
                "json_path": root / "shadow.json",
                "csv_path": root / "shadow.csv",
                "markdown_path": root / "shadow.md",
            },
        )()
        for path in (paths.json_path, paths.csv_path, paths.markdown_path):
            path.write_text("evidence\n", encoding="utf-8")
        return paths

    monkeypatch.setattr(
        checkpoints,
        "write_the_odds_shadow_reports",
        fake_reports,
    )
    def provider_factory():
        return FakeProvider()
    report_dir = tmp_path / "reports"
    collect_shadow_checkpoint(
        target=target,
        checkpoint="control",
        provider_factory=provider_factory,
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_dir,
    )

    with pytest.raises(ValueError, match="checkpoint input conflict"):
        collect_shadow_checkpoint(
            target=target,
            checkpoint="control",
            provider_factory=provider_factory,
            session_factory="factory",
            aliases={"different": "alias"},
            quota_reserve=50,
            report_dir=report_dir,
        )


def test_checkpoint_reuse_rejects_mutated_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import toto_ai.external_odds.the_odds_checkpoints as checkpoints

    target = target_drawing()
    snapshot = replace(
        _collection(1, ()),
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider="the-odds-api",
    )
    monkeypatch.setattr(
        checkpoints,
        "collect_target_external_odds",
        lambda *args, **kwargs: snapshot,
    )

    def fake_reports(*args, **kwargs):
        root = tmp_path / "reports" / str(target.drawing_number)
        root.mkdir(parents=True, exist_ok=True)
        paths = type(
            "Paths",
            (),
            {
                "json_path": root / "shadow.json",
                "csv_path": root / "shadow.csv",
                "markdown_path": root / "shadow.md",
            },
        )()
        for path in (paths.json_path, paths.csv_path, paths.markdown_path):
            path.write_text("evidence\n", encoding="utf-8")
        return paths

    monkeypatch.setattr(
        checkpoints,
        "write_the_odds_shadow_reports",
        fake_reports,
    )
    report_dir = tmp_path / "reports"
    collect_shadow_checkpoint(
        target=target,
        checkpoint="t10",
        provider_factory=lambda: FakeProvider(),
        session_factory="factory",
        aliases={},
        quota_reserve=50,
        report_dir=report_dir,
    )
    (report_dir / str(target.drawing_number) / "shadow.json").write_text(
        "mutated\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence hash mismatch"):
        collect_shadow_checkpoint(
            target=target,
            checkpoint="t10",
            provider_factory=lambda: FakeProvider(),
            session_factory="factory",
            aliases={},
            quota_reserve=50,
            report_dir=report_dir,
        )


@pytest.mark.parametrize("checkpoint", ["morning", "control", "t10"])
def test_only_approved_checkpoint_names_are_accepted(checkpoint: str) -> None:
    from toto_ai.external_odds.the_odds_checkpoints import checkpoint_input_sha256

    assert len(
        checkpoint_input_sha256(
            target_drawing(),
            checkpoint=checkpoint,
            aliases={},
            quota_reserve=50,
        )
    ) == 64


def test_unapproved_checkpoint_name_is_rejected() -> None:
    from toto_ai.external_odds.the_odds_checkpoints import checkpoint_input_sha256

    with pytest.raises(ValueError, match="morning, control, or t10"):
        checkpoint_input_sha256(
            target_drawing(),
            checkpoint="extra",
            aliases={},
            quota_reserve=50,
        )
