from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import toto_ai.cli as cli_module
import toto_ai.ev.drawing as drawing_module
from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from toto_ai.db.session import get_session_factory, init_db, open_readonly_db
from toto_ai.ev.models import (
    EVComponents,
    EVPackage,
    EVSurface,
    PlayTimingEligibility,
    RankedCoupon,
)
from toto_ai.ev.package_quality import PackageSelectionProvenance
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.domain import ProviderEvent, QuotaState
from toto_ai.external_odds.matching import load_aliases
from toto_ai.external_odds.prospective import (
    ProspectiveCollectionResult,
    collect_fresh_open_external_odds,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.timing_overrides import (
    PinnedTimingOverrideCatalog,
    pin_timing_override_catalog,
)
from toto_ai.runner import (
    DrawingRunnerConfig,
    RunnerTimingResolution,
    pin_drawing,
    publish_drawing_run_artifacts,
    run_drawing,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)
RUN_AT = datetime(2026, 7, 20, 14, 11, tzinfo=UTC)
FINGERPRINT = "8f06d994a6e505d59e5b76166208a5987463df904fcc79afaf3311401b2c3704"
EXPECTED_PROVIDER_IDS = (
    "1551047",
    None,
    "1508810",
    "1508813",
    None,
    "1515888",
    "1593669",
    "1593670",
    "1586075",
    "1565183",
    "1565184",
    "1495737",
    "1494214",
    "1497627",
    "1519414",
)
MISSING_EVENT_ORDERS = (1, 4)
FIXTURES = Path(__file__).parent / "fixtures"
SCHEDULE_PATH = FIXTURES / "drawing_4950_api_sports_schedule.json"
OVERRIDE_PATH = FIXTURES / "drawing_4950_timing_overrides.json"
TOTOBRIEF_PATH = FIXTURES / "drawing_4950_totobrief.json"
ALIASES_PATH = Path("data/external-odds/team-aliases.json")


class _ReplayProvider:
    provider_name = "api-sports"

    def __init__(self) -> None:
        payload = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        self.events = tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=event["id"],
                sport="football",
                league=event["league"],
                starts_at=datetime.fromisoformat(event["date"]),
                home_team=event["home"],
                away_team=event["away"],
                fetched_at=fetched_at,
                payload_hash=f"offline-fixture-{event['id']}",
            )
            for event in payload["events"]
        )
        self.requests_made = 0
        self.cache_hits = 0
        self.quota_state = QuotaState(100, 100, 10, 10)

    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        requested_dates = set(dates)
        return tuple(
            event
            for event in self.events
            if event.sport == sport and event.starts_at.date() in requested_dates
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        assert sport == "football"
        assert isinstance(provider_event_id, str)
        return ()


class _PayloadClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        assert drawing_id == 11964
        return deepcopy(self.payload)


@dataclass(frozen=True)
class _ReplayContext:
    payload: dict[str, object]
    pinned: object
    collection: ProspectiveCollectionResult
    raw_timing: object
    audit: object
    engine: object
    readonly_engine: object
    cache_root: Path


def _drawing_payload() -> dict[str, object]:
    return json.loads(TOTOBRIEF_PATH.read_text(encoding="utf-8"))


def _collect_replay(tmp_path: Path) -> _ReplayContext:
    payload = _drawing_payload()
    target = parse_target_drawing(payload, fetched_at=RUN_AT)
    pinned = pin_drawing(target)
    assert pinned.fingerprint == FINGERPRINT

    db_path = tmp_path / "timing.sqlite"
    cache_root = tmp_path / "cache"
    engine = init_db(db_path)
    session_factory = get_session_factory(engine)
    collection = collect_fresh_open_external_odds(
        totobrief_client=_PayloadClient(payload),
        provider_factory=lambda _cache_dir: _ReplayProvider(),
        session_factory=session_factory,
        aliases=load_aliases(ALIASES_PATH),
        cache_root=cache_root,
        target=target,
        max_passes=1,
        max_expansion_passes=1,
        retry_delay_seconds=0.0,
        now=lambda: RUN_AT,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("offline replay must not sleep"),
    )
    # This suite isolates reviewed timing-overlay behavior. Identity
    # revalidation is independently covered by production pin tests, so supply
    # its already-passed boundary explicitly instead of exercising legacy name
    # matching as an authorization path.
    snapshot = replace(
        collection.snapshot,
        pinned_revalidation=ready_pinned_revalidation(RUN_AT),
    )
    collection = replace(
        collection,
        snapshot=snapshot,
        passes=tuple(replace(item, snapshot=snapshot) for item in collection.passes),
        base_passes=tuple(
            replace(item, snapshot=snapshot) for item in collection.base_passes
        ),
        expansion_passes=tuple(
            replace(item, snapshot=snapshot)
            for item in collection.expansion_passes
        ),
    )
    raw_timing = cli_module._build_runner_timing_resolver(str(db_path))(pinned)
    readonly_engine = open_readonly_db(db_path)
    audit = audit_external_coverage(
        get_session_factory(readonly_engine),
        last=30,
        minimum_bookmakers=3,
    )
    return _ReplayContext(
        payload=payload,
        pinned=pinned,
        collection=collection,
        raw_timing=raw_timing,
        audit=audit,
        engine=engine,
        readonly_engine=readonly_engine,
        cache_root=cache_root,
    )


def _copy_override(tmp_path: Path) -> Path:
    path = tmp_path / "timing-overrides.json"
    path.write_bytes(OVERRIDE_PATH.read_bytes())
    return path


def _catalog_payload() -> dict[str, object]:
    return json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))


def _coupon(index: int) -> str:
    digest = hashlib.sha256(f"timing-override-{index}".encode()).digest()
    return "".join("1X2"[digest[order] % 3] for order in range(15))


def _install_operational_ev_replay(monkeypatch: pytest.MonkeyPatch) -> None:
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
        lambda components, possible_winnings, jackpot: EVSurface(
            gross_ev=np.array([1.0]),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        ),
    )

    def package(config):
        cost = config.max_coupons * config.stake
        coupons = tuple(
            RankedCoupon(
                rank=index + 1,
                coupon=_coupon(index),
                gross_ev=1.0,
                net_ev=0.0,
            )
            for index in range(cost // config.stake)
        )
        return EVPackage(
            decision="PLAY" if coupons else "NO BET",
            coupons=coupons,
            cost=cost,
            unused_bank=config.bank - cost,
            expected_payout=float(cost),
            modeled_roi=0.0 if coupons else None,
            derived_brief=("1",) * 15 if coupons else (),
        )

    def select_package(surface, config, *, probabilities=None, provenance=None):
        assert provenance is None or isinstance(
            provenance,
            PackageSelectionProvenance,
        )
        return package(config)

    def select_package_with_top_coupons(
        surface,
        config,
        *,
        probabilities=None,
        provenance=None,
        diagnostic_limit=20,
    ):
        selected = select_package(
            surface,
            config,
            probabilities=probabilities,
            provenance=provenance,
        )
        return selected, selected.coupons[:diagnostic_limit]

    monkeypatch.setattr(drawing_module, "select_ev_package", select_package)
    monkeypatch.setattr(
        drawing_module,
        "select_ev_package_with_top_coupons",
        select_package_with_top_coupons,
    )


def _run_with_override(
    context: _ReplayContext,
    catalog_path: Path,
    *,
    audit_callback=None,
    build_package=None,
):
    catalog_pin: PinnedTimingOverrideCatalog | None = None
    timing_resolution: RunnerTimingResolution | None = None

    def preflight_check(pinned, preflight_at):
        nonlocal catalog_pin
        assert pinned == context.pinned
        assert preflight_at == RUN_AT
        catalog_pin = pin_timing_override_catalog(catalog_path)

    def require_pin() -> PinnedTimingOverrideCatalog:
        assert catalog_pin is not None
        return catalog_pin

    def resolve_override(pinned, collection, raw):
        nonlocal timing_resolution
        timing_resolution = cli_module._resolve_runner_timing_override(
            pinned,
            collection,
            raw,
            require_pin(),
        )
        return timing_resolution

    def verify_override(resolution):
        nonlocal timing_resolution
        timing_resolution = cli_module._verify_runner_timing_override(
            resolution,
            require_pin(),
        )
        return timing_resolution

    def invoke_package(pinned):
        if build_package is None:
            pytest.fail("NO BET must not build a package")
        assert timing_resolution is not None
        return build_package(pinned, timing_resolution)

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980, stake=30, mode="playable"),
        resolve_target=lambda _resolved_at: context.pinned,
        collect_target=lambda _target, _stop_at: context.collection,
        resolve_timing=lambda _pinned: context.raw_timing,
        audit_coverage=(audit_callback or (lambda: context.audit)),
        build_package=invoke_package,
        now=lambda: RUN_AT,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("offline replay must not sleep"),
        preflight_check=preflight_check,
        resolve_timing_override=resolve_override,
        verify_timing_override=verify_override,
    )
    return result, timing_resolution, catalog_pin


def test_drawing_4950_totobrief_fixture_is_clean_checkout_independent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    payload = _drawing_payload()
    data = payload["data"]

    assert TOTOBRIEF_PATH.is_file()
    assert data["id"] == 11964
    assert data["number"] == 4950
    assert data["pool_sum"] == 81_445
    assert len(data["events"]) == 15
    assert all(
        "result" not in event and "score" not in event
        for event in data["events"]
    )
    assert all(
        not any(field.startswith("norm_") for field in event["quotes"])
        for event in data["events"]
    )


def test_drawing_4950_reviewed_timing_override_operational_readiness_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _collect_replay(tmp_path)
    catalog_path = _copy_override(tmp_path)
    _install_operational_ev_replay(monkeypatch)
    raw_events = context.collection.snapshot.events

    def build_package(pinned, resolution):
        assert resolution.override is not None
        assert resolution.override.package_catalog_sha256 == (
            resolution.override.preflight_catalog_sha256
        )
        return cli_module._build_runner_package(
            client=_PayloadClient(context.payload),
            expected=pinned,
            config=DrawingRunnerConfig(bank=4980, stake=30).ev_config,
            fetched_at=RUN_AT,
            progress_callback=None,
            timing_eligibility_resolver=(
                lambda _payload: resolution.effective
            ),
        )

    result, timing_resolution, catalog_pin = _run_with_override(
        context,
        catalog_path,
        build_package=build_package,
    )
    assert timing_resolution is not None
    assert result.decision == "NO BET"
    assert result.raw_timing_eligibility.status == "unknown"
    assert result.timing_eligibility.status == "playable"
    assert result.timing_override is not None
    assert result.timing_override.status == "applied"
    assert result.timing_override.overlay_complete is True
    assert tuple(
        event.event_order for event in result.timing_override.applied_events
    ) == MISSING_EVENT_ORDERS
    assert result.timing_override.preserved_event_orders == tuple(
        order for order in range(15) if order not in MISSING_EVENT_ORDERS
    )
    assert result.timing_override.overlay_summary is not None
    assert result.timing_override.overlay_summary.status == "playable"
    assert result.timing_override.overlay_summary.span_days == 1
    assert result.timing_override.overlay_summary.provider_count == 13
    assert result.timing_override.overlay_summary.operator_override_count == 2
    assert (
        result.timing_override.preflight_catalog_sha256
        == result.timing_override.timing_catalog_sha256
        == result.timing_override.package_catalog_sha256
        == catalog_pin.catalog_sha256
    )

    snapshot = result.collection.snapshot
    assert tuple(event.provider_event_id for event in snapshot.events) == (
        EXPECTED_PROVIDER_IDS
    )
    assert snapshot.events is raw_events
    assert snapshot.eligibility.status == "unknown"
    assert snapshot.eligibility.missing_event_orders == MISSING_EVENT_ORDERS
    assert snapshot.eligibility.provider_count == 13
    assert all(
        event.effective_start_source in {"provider", "unresolved"}
        for event in snapshot.events
    )

    assert result.ev_run is not None
    assert result.ev_run.requested_bank == 4980
    assert result.ev_run.config.stake == 30
    assert result.ev_run.ev_input.pool_sum == 81_445
    assert result.ev_run.effective_budget == 810
    assert result.ev_run.package.decision == "NO BET"
    assert result.ev_run.package.coupons == ()
    assert result.ev_run.package.cost == 0
    assert result.ev_run.package.artifact_class == "TRAINING/PAPER"
    assert result.ev_run.package.paper_coupons
    assert 0 < result.ev_run.package.paper_cost <= 810

    publication = publish_drawing_run_artifacts(
        result,
        report_dir=tmp_path / "reports",
        protected_paths=(catalog_path, tmp_path / "timing.sqlite"),
        protected_roots=(context.cache_root,),
        now=lambda: RUN_AT,
    )
    manifest = json.loads(publication.runner[0].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 4
    assert manifest["eligibility"]["raw"]["status"] == "unknown"
    assert manifest["eligibility"]["raw"]["missing_event_orders"] == [1, 4]
    assert manifest["eligibility"]["effective"]["status"] == "playable"
    assert manifest["eligibility"]["effective"]["span_days"] == 1
    assert manifest["eligibility"]["effective"]["operator_override_count"] == 2
    override = manifest["eligibility"]["override"]
    assert override["override_id"] == "drawing-4950-reviewed-timing-v1"
    assert override["reviewer"] == "offline-reviewer@example.test"
    assert override["source_ref"] == "offline-review:drawing-4950"
    assert [event["event_order"] for event in override["applied_events"]] == [1, 4]
    assert [event["source_ref"] for event in override["applied_events"]] == [
        "https://www.sofascore.com/football/match/atletico-juniors-de-yotala-atletico-sucre/JwMdsiGpj",
        "https://www.footlive.com/score/grindavik-njardvik-women-vs-throttur-reykjavik-women-2026-07-20/",
    ]
    assert (
        override["preflight_catalog_sha256"]
        == override["timing_catalog_sha256"]
        == override["package_catalog_sha256"]
    )
    assert manifest["ev"]["requested_bank"] == 4980
    assert manifest["ev"]["effective_budget"] == 810
    assert manifest["ev"]["selected_cost"] == 0
    package = manifest["ev"]["package"]
    assert package["decision"] == "NO BET"
    assert package["coupons"] == []
    assert package["cost"] == 0
    assert package["artifact_class"] == "TRAINING/PAPER"
    assert package["paper_coupons"]
    assert 0 < package["paper_cost"] <= 810

    context.engine.dispose()
    context.readonly_engine.dispose()


@pytest.mark.parametrize(
    (
        "variant",
        "expected_status",
        "expected_applied_orders",
        "expected_diagnostic",
    ),
    (
        ("stale", "not_applied", (), "target_fingerprint_mismatch"),
        ("partial", "not_applied", (1, 4), "partial_override"),
        ("malformed", "invalid_catalog", (), "strict catalog validation failed"),
        (
            "event_identity_mismatch",
            "not_applied",
            (),
            "event_identity_mismatch",
        ),
        (
            "wrong_year",
            "not_applied",
            (),
            "event_start_before_drawing_end",
        ),
        (
            "before_ended_at",
            "not_applied",
            (),
            "event_start_before_drawing_end",
        ),
        (
            "after_five_days",
            "not_applied",
            (),
            "event_start_after_override_horizon",
        ),
        (
            "future_review",
            "not_applied",
            (),
            "reviewed_at_after_pin",
        ),
        (
            "stale_review",
            "not_applied",
            (),
            "reviewed_at_before_review_window",
        ),
    ),
)
def test_drawing_4950_unusable_override_is_unknown_no_bet(
    tmp_path: Path,
    variant: str,
    expected_status: str,
    expected_applied_orders: tuple[int, ...],
    expected_diagnostic: str,
) -> None:
    context = _collect_replay(tmp_path)
    catalog_path = tmp_path / f"{variant}.json"
    payload = _catalog_payload()
    record = payload["overrides"][0]
    if variant == "stale":
        record["target_fingerprint"] = "0" * 64
    elif variant == "partial":
        record["events"] = [
            event for event in record["events"] if event["event_order"] in (1, 4)
        ]
    elif variant == "event_identity_mismatch":
        record["events"][1]["event_id"] = 999_999
    elif variant == "wrong_year":
        record["events"][1]["starts_at"] = "2025-07-20T19:00:00+00:00"
    elif variant == "before_ended_at":
        record["events"][1]["starts_at"] = "2026-07-20T14:29:59+00:00"
    elif variant == "after_five_days":
        record["events"][1]["starts_at"] = "2026-07-25T14:30:00.000001+00:00"
    elif variant == "future_review":
        record["reviewed_at"] = "2026-07-20T14:11:00.000001+00:00"
    elif variant == "stale_review":
        record["reviewed_at"] = "2026-07-13T14:29:59.999999+00:00"

    if variant == "malformed":
        catalog_path.write_text("{not-json", encoding="utf-8")
    else:
        catalog_path.write_text(json.dumps(payload), encoding="utf-8")

    result, _, _ = _run_with_override(context, catalog_path)

    assert result.decision == "NO BET"
    assert result.raw_timing_eligibility.status == "unknown"
    assert result.timing_eligibility.status == "unknown"
    assert result.timing_override is not None
    assert result.timing_override.status == expected_status
    assert tuple(
        event.event_order for event in result.timing_override.applied_events
    ) == expected_applied_orders
    assert any(
        expected_diagnostic in diagnostic
        for diagnostic in result.timing_override.diagnostics
    )
    assert result.ev_run is None

    context.engine.dispose()
    context.readonly_engine.dispose()


def test_drawing_4950_no_override_and_hash_changed_override_are_no_bet(
    tmp_path: Path,
) -> None:
    context = _collect_replay(tmp_path)
    build_calls = 0

    def forbidden_package(*_args):
        nonlocal build_calls
        build_calls += 1
        pytest.fail("unknown or hash-changed timing must not build a package")

    without_override = run_drawing(
        config=DrawingRunnerConfig(bank=4980, stake=30, mode="playable"),
        resolve_target=lambda _resolved_at: context.pinned,
        collect_target=lambda _target, _stop_at: context.collection,
        resolve_timing=lambda _pinned: context.raw_timing,
        audit_coverage=lambda: context.audit,
        build_package=forbidden_package,
        now=lambda: RUN_AT,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("offline replay must not sleep"),
    )
    assert without_override.decision == "NO BET"
    assert without_override.raw_timing_eligibility.status == "unknown"
    assert without_override.timing_eligibility.status == "unknown"
    assert without_override.timing_override is None

    catalog_path = _copy_override(tmp_path)

    def mutate_catalog_after_timing():
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        payload["overrides"][0]["reviewer"] = "changed-reviewer@example.test"
        catalog_path.write_text(json.dumps(payload), encoding="utf-8")
        return context.audit

    changed, _, pinned_catalog = _run_with_override(
        context,
        catalog_path,
        audit_callback=mutate_catalog_after_timing,
        build_package=forbidden_package,
    )

    assert changed.decision == "NO BET"
    assert changed.raw_timing_eligibility.status == "unknown"
    assert changed.timing_eligibility.status == "unknown"
    assert changed.timing_override is not None
    assert changed.timing_override.status == "catalog_changed"
    assert changed.timing_override.preflight_catalog_sha256 == (
        pinned_catalog.catalog_sha256
    )
    assert changed.timing_override.timing_catalog_sha256 == (
        pinned_catalog.catalog_sha256
    )
    assert changed.timing_override.package_catalog_sha256 is None
    assert changed.ev_run is None
    assert build_calls == 0

    context.engine.dispose()
    context.readonly_engine.dispose()


def test_explicit_catalog_cannot_force_playable_without_exact_override_audit(
    tmp_path: Path,
) -> None:
    context = _collect_replay(tmp_path)
    forced_raw = PlayTimingEligibility(
        status="playable",
        reason="malicious dependency attempted to bypass exact catalog validation",
        target_fingerprint=context.pinned.fingerprint,
        fingerprint_match=True,
    )
    build_calls = 0

    def forbidden_package(_pinned):
        nonlocal build_calls
        build_calls += 1
        pytest.fail("an unvalidated override must never reach package generation")

    with pytest.raises(ValueError, match="explicitly supplied timing catalog"):
        run_drawing(
            config=DrawingRunnerConfig(bank=4980, stake=30, mode="playable"),
            resolve_target=lambda _resolved_at: context.pinned,
            collect_target=lambda _target, _stop_at: context.collection,
            resolve_timing=lambda _pinned: forced_raw,
            audit_coverage=lambda: context.audit,
            build_package=forbidden_package,
            now=lambda: RUN_AT,
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: pytest.fail("offline replay must not sleep"),
            preflight_check=lambda _pinned, _preflight_at: None,
            resolve_timing_override=(
                lambda _pinned, _collection, raw: (
                    RunnerTimingResolution.without_override(raw)
                )
            ),
            verify_timing_override=lambda resolution: resolution,
        )

    assert build_calls == 0
    context.engine.dispose()
    context.readonly_engine.dispose()
