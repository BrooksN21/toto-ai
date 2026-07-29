from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Drawing(Base):
    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    pool_sum: Mapped[float | None] = mapped_column(Float)
    jackpot: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[str | None] = mapped_column(String)
    ended_at: Mapped[str | None] = mapped_column(String)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("drawing_id", "event_order", name="uq_events_drawing_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    event_order: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String)
    championship: Mapped[str | None] = mapped_column(String)
    sport: Mapped[str | None] = mapped_column(String)
    result: Mapped[str | None] = mapped_column(String)
    score: Mapped[str | None] = mapped_column(String)


class DrawingResultSnapshot(Base):
    """Immutable authoritative drawing-result observation."""

    __tablename__ = "drawing_result_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "snapshot_sha256",
            name="uq_drawing_result_snapshot_content",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int] = mapped_column(Integer, index=True)
    hash_schema_version: Mapped[int] = mapped_column(Integer, default=3)
    ended_at: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[str] = mapped_column(String)
    source_endpoint: Mapped[str] = mapped_column(String)
    payload_sha256: Mapped[str] = mapped_column(String)
    result_sha256: Mapped[str] = mapped_column(String)
    snapshot_sha256: Mapped[str] = mapped_column(String, index=True)
    complete: Mapped[bool] = mapped_column(Boolean)
    event_count: Mapped[int] = mapped_column(Integer)
    actual: Mapped[str] = mapped_column(String)
    events_json: Mapped[str] = mapped_column(Text)
    payments_json: Mapped[str | None] = mapped_column(Text)
    pool_sum: Mapped[float | None] = mapped_column(Float)
    jackpot: Mapped[float | None] = mapped_column(Float)
    payload_json: Mapped[str] = mapped_column(Text)


class ArchivedPackage(Base):
    """Canonical package plus original source bytes for exact replay."""

    __tablename__ = "archived_packages"

    archive_sha256: Mapped[str] = mapped_column(String, primary_key=True)
    package_sha256: Mapped[str] = mapped_column(String, index=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int] = mapped_column(Integer, index=True)
    stake: Mapped[int] = mapped_column(Integer)
    coupon_count: Mapped[int] = mapped_column(Integer)
    cost: Mapped[int] = mapped_column(Integer)
    source_path: Mapped[str] = mapped_column(Text)
    source_bytes_sha256: Mapped[str] = mapped_column(String)
    source_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    coupons_json: Mapped[str] = mapped_column(Text)
    archived_at: Mapped[str] = mapped_column(String)
    provenance: Mapped[str] = mapped_column(String)
    archive_manifest_sha256: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    final_input_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    probability_input_sha256: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    final_input_captured_at: Mapped[str | None] = mapped_column(
        String, nullable=True
    )


class PackageSettlement(Base):
    """Immutable settlement bound to one result and one archived package."""

    __tablename__ = "package_settlements"

    settlement_sha256: Mapped[str] = mapped_column(String, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int] = mapped_column(Integer, index=True)
    result_snapshot_sha256: Mapped[str] = mapped_column(String, index=True)
    archive_sha256: Mapped[str] = mapped_column(String, index=True)
    package_sha256: Mapped[str] = mapped_column(String, index=True)
    settled_at: Mapped[str] = mapped_column(String)
    actual: Mapped[str] = mapped_column(String)
    hit_distribution_json: Mapped[str] = mapped_column(Text)
    best_hits: Mapped[int] = mapped_column(Integer)
    best_coupon_ranks_json: Mapped[str] = mapped_column(Text)
    category_counts_json: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[int] = mapped_column(Integer)
    fixed_miss_events_json: Mapped[str] = mapped_column(Text)
    zero_exposure_miss_events_json: Mapped[str] = mapped_column(Text)
    known_return: Mapped[float | None] = mapped_column(Float)
    roi: Mapped[float | None] = mapped_column(Float)
    return_status: Mapped[str] = mapped_column(String)
    settlement_json: Mapped[str] = mapped_column(Text)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("drawing_id", "event_order", name="uq_quotes_drawing_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    event_order: Mapped[int | None] = mapped_column(Integer)
    pool_win_1: Mapped[float | None] = mapped_column(Float)
    pool_draw: Mapped[float | None] = mapped_column(Float)
    pool_win_2: Mapped[float | None] = mapped_column(Float)
    bk_win_1: Mapped[float | None] = mapped_column(Float)
    bk_draw: Mapped[float | None] = mapped_column(Float)
    bk_win_2: Mapped[float | None] = mapped_column(Float)
    pin_win_1: Mapped[float | None] = mapped_column(Float)
    pin_draw: Mapped[float | None] = mapped_column(Float)
    pin_win_2: Mapped[float | None] = mapped_column(Float)
    norm_win_1: Mapped[float | None] = mapped_column(Float)
    norm_draw: Mapped[float | None] = mapped_column(Float)
    norm_win_2: Mapped[float | None] = mapped_column(Float)


class ExternalCollectionRun(Base):
    __tablename__ = "external_collection_runs"

    collection_id: Mapped[str] = mapped_column(String, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[str] = mapped_column(String)
    target_fetched_at: Mapped[str] = mapped_column(String)
    deadline: Mapped[str] = mapped_column(String)
    event_count: Mapped[int] = mapped_column(Integer)
    requests_made: Mapped[int] = mapped_column(Integer)
    cache_hits: Mapped[int] = mapped_column(Integer)
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    daily_remaining: Mapped[int | None] = mapped_column(Integer)
    minute_remaining: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    target_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    missing_start_horizon_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    requested_schedule_dates: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    successful_schedule_dates: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    failed_schedule_dates: Mapped[str | None] = mapped_column(String, nullable=True)
    eligibility_status: Mapped[str | None] = mapped_column(String, nullable=True)
    eligibility_earliest_start: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    eligibility_latest_start: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    eligibility_span_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    eligibility_missing_event_orders: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    eligibility_totobrief_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    eligibility_provider_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    pinned_revalidation_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )


class ExternalEventDisposition(Base):
    __tablename__ = "external_event_dispositions"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "event_order",
            name="uq_external_collection_event",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[str] = mapped_column(String, index=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    event_order: Mapped[int] = mapped_column(Integer)
    target_event_id: Mapped[int] = mapped_column(Integer)
    sport: Mapped[str] = mapped_column(String)
    championship: Mapped[str] = mapped_column(String)
    starts_at: Mapped[str] = mapped_column(String)
    home_team: Mapped[str] = mapped_column(String)
    away_team: Mapped[str] = mapped_column(String)
    home_team_en: Mapped[str | None] = mapped_column(String)
    away_team_en: Mapped[str | None] = mapped_column(String)
    match_status: Mapped[str] = mapped_column(String)
    match_orientation: Mapped[str] = mapped_column(String)
    provider_event_id: Mapped[str | None] = mapped_column(String)
    provider_event_fetched_at: Mapped[str | None] = mapped_column(String)
    provider_event_payload_hash: Mapped[str | None] = mapped_column(String)
    matcher_version: Mapped[str] = mapped_column(String)
    match_candidate_ids: Mapped[str] = mapped_column(String)
    match_reason: Mapped[str] = mapped_column(String)
    probability_source: Mapped[str] = mapped_column(String)
    probability_1: Mapped[float] = mapped_column(Float)
    probability_x: Mapped[float] = mapped_column(Float)
    probability_2: Mapped[float] = mapped_column(Float)
    eligible_bookmaker_count: Mapped[int] = mapped_column(Integer)
    odds_age_hours: Mapped[float | None] = mapped_column(Float)
    fallback_reason: Mapped[str | None] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    provider_starts_at: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_starts_at: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_start_source: Mapped[str | None] = mapped_column(
        String, nullable=True
    )


class ExternalBookmakerQuote(Base):
    __tablename__ = "external_bookmaker_quotes"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "event_order",
            "bookmaker_id",
            "market_name",
            name="uq_external_book_quote",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[str] = mapped_column(String, index=True)
    event_order: Mapped[int] = mapped_column(Integer)
    bookmaker_id: Mapped[str] = mapped_column(String)
    market_name: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[str] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    home_price: Mapped[float | None] = mapped_column(Float)
    draw_price: Mapped[float | None] = mapped_column(Float)
    away_price: Mapped[float | None] = mapped_column(Float)
    eligible: Mapped[int] = mapped_column(Integer)
    rejection_reason: Mapped[str | None] = mapped_column(String)
    source_count: Mapped[int] = mapped_column(Integer)
    source_provenance: Mapped[str] = mapped_column(String)


class TeamEntity(Base):
    __tablename__ = "team_entities"
    __table_args__ = (
        UniqueConstraint(
            "sport",
            "normalized_name",
            "country",
            "context",
            name="uq_team_entity_identity",
        ),
        Index("ix_team_entities_sport_transliterated", "sport", "transliterated_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String)
    canonical_name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String)
    transliterated_name: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="")
    context: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (
        UniqueConstraint(
            "sport",
            "provider",
            "normalized_alias",
            "country",
            "context",
            name="uq_team_alias_identity",
        ),
        Index(
            "uq_team_alias_provider_team_id",
            "sport",
            "provider",
            "provider_team_id",
            unique=True,
            sqlite_where=text("provider_team_id IS NOT NULL"),
        ),
        Index(
            "ix_team_alias_reviewed_lookup",
            "sport",
            "provider",
            "normalized_alias",
            "reviewed",
            "active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team_entities.id"), index=True)
    sport: Mapped[str] = mapped_column(String)
    alias: Mapped[str] = mapped_column(String)
    normalized_alias: Mapped[str] = mapped_column(String)
    transliterated_alias: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String, default="")
    country: Mapped[str] = mapped_column(String, default="")
    context: Mapped[str] = mapped_column(String, default="")
    provider_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provenance: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class TeamRegistryReview(Base):
    __tablename__ = "team_registry_reviews"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            "target_event_id",
            "event_order",
            "provider",
            name="uq_team_registry_review_identity",
        ),
        Index("ix_team_registry_reviews_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    target_event_id: Mapped[str] = mapped_column(String)
    event_order: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String)
    sport: Mapped[str] = mapped_column(String)
    target_home_team: Mapped[str] = mapped_column(String)
    target_away_team: Mapped[str] = mapped_column(String)
    target_home_normalized: Mapped[str] = mapped_column(String)
    target_away_normalized: Mapped[str] = mapped_column(String)
    context: Mapped[str] = mapped_column(Text)
    resolution_reason: Mapped[str] = mapped_column(Text, default="")
    candidate_evidence: Mapped[str] = mapped_column(Text)
    matching_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    resolution_home_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_entities.id"), nullable=True
    )
    resolution_away_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_entities.id"), nullable=True
    )
    resolution_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    resolved_at: Mapped[str | None] = mapped_column(String, nullable=True)


class DrawingEventPin(Base):
    __tablename__ = "drawing_event_pins"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            "target_event_id",
            "event_order",
            "provider",
            name="uq_drawing_event_pin_identity",
        ),
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            "provider",
            "provider_fixture_id",
            name="uq_drawing_event_pin_fixture",
        ),
        Index(
            "ix_drawing_event_pins_exact_lookup",
            "drawing_id",
            "drawing_fingerprint",
            "target_event_id",
            "event_order",
            "provider",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    target_event_id: Mapped[str] = mapped_column(String)
    event_order: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String)
    canonical_home_team_id: Mapped[int] = mapped_column(
        ForeignKey("team_entities.id")
    )
    canonical_away_team_id: Mapped[int] = mapped_column(
        ForeignKey("team_entities.id")
    )
    provider_home_team_id: Mapped[str] = mapped_column(String)
    provider_away_team_id: Mapped[str] = mapped_column(String)
    provider_fixture_id: Mapped[str] = mapped_column(String)
    starts_at: Mapped[str | None] = mapped_column(String, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provenance: Mapped[str] = mapped_column(Text)
    pin_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    invalidated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class DrawingPreparation(Base):
    __tablename__ = "drawing_preparations"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            "provider",
            name="uq_drawing_preparation_identity",
        ),
        Index(
            "ix_drawing_preparations_lookup",
            "drawing_id",
            "provider",
            "status",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(Integer)
    drawing_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    mapped_count: Mapped[int] = mapped_column(Integer)
    unresolved_event_orders: Mapped[str] = mapped_column(Text)
    eligibility_status: Mapped[str] = mapped_column(String)
    readiness_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class DrawingPinSet(Base):
    """Canonical authoritative schedule pin set.

    Legacy drawing_event_pins remain readable for API-Sports-only preparations.
    Mixed-source sets are stored here so reviewed evidence never needs a fake
    provider fixture or team identifier.
    """

    __tablename__ = "drawing_pin_sets"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            name="uq_drawing_pin_set_target",
        ),
        Index(
            "ix_drawing_pin_sets_lookup",
            "drawing_id",
            "drawing_fingerprint",
            "status",
        ),
    )

    pin_set_id: Mapped[str] = mapped_column(String, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(Integer)
    drawing_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    pin_set_hash: Mapped[str] = mapped_column(String)
    provider_distribution_json: Mapped[str] = mapped_column(Text)
    reviewed_catalog_hash: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    invalidated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(
        String, nullable=True
    )


class DrawingPinSetItem(Base):
    __tablename__ = "drawing_pin_set_items"
    __table_args__ = (
        UniqueConstraint(
            "pin_set_id", "event_order", name="uq_pin_set_item_order"
        ),
        UniqueConstraint(
            "pin_set_id", "target_event_id", name="uq_pin_set_item_target"
        ),
        Index(
            "ix_drawing_pin_set_items_lookup",
            "pin_set_id",
            "event_order",
            "source_provider",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pin_set_id: Mapped[str] = mapped_column(
        ForeignKey("drawing_pin_sets.pin_set_id")
    )
    drawing_id: Mapped[int] = mapped_column(Integer)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    target_event_id: Mapped[str] = mapped_column(String)
    event_order: Mapped[int] = mapped_column(Integer)
    source_provider: Mapped[str] = mapped_column(String)
    source_fixture_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_evidence_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    canonical_home_team_id: Mapped[int] = mapped_column(
        ForeignKey("team_entities.id")
    )
    canonical_away_team_id: Mapped[int] = mapped_column(
        ForeignKey("team_entities.id")
    )
    source_home_team_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    source_away_team_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    starts_at: Mapped[str] = mapped_column(String)
    source_identity_hash: Mapped[str] = mapped_column(String)
    schedule_only: Mapped[bool] = mapped_column(Boolean)
    provenance: Mapped[str] = mapped_column(Text)
    pin_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class SportsStatsRun(Base):
    """Immutable, content-addressed audit-only sports-statistics run."""

    __tablename__ = "sports_stats_runs"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "drawing_fingerprint",
            "provider",
            "as_of",
            name="uq_sports_stats_run_identity",
        ),
        Index(
            "ix_sports_stats_runs_latest",
            "drawing_id",
            "drawing_fingerprint",
            "provider",
            "as_of",
        ),
    )

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String)
    schema_version: Mapped[int] = mapped_column(Integer)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    drawing_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drawing_fingerprint: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    requested_history_size: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(String)
    as_of: Mapped[str] = mapped_column(String)
    deadline: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    complete_count: Mapped[int] = mapped_column(Integer)
    partial_count: Mapped[int] = mapped_column(Integer)
    missing_count: Mapped[int] = mapped_column(Integer)
    unsupported_count: Mapped[int] = mapped_column(Integer)
    requests_made: Mapped[int] = mapped_column(Integer)
    cache_hits: Mapped[int] = mapped_column(Integer)
    source_request_fingerprints_json: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str] = mapped_column(Text)


class SportsEventFeatureSnapshot(Base):
    """One immutable event row belonging to a sports-statistics run."""

    __tablename__ = "sports_event_feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "event_order",
            name="uq_sports_stats_run_event",
        ),
        UniqueConstraint(
            "run_id",
            "target_event_id",
            name="uq_sports_stats_run_target_event",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    drawing_id: Mapped[int] = mapped_column(Integer, index=True)
    event_order: Mapped[int] = mapped_column(Integer)
    target_event_id: Mapped[str] = mapped_column(String)
    sport: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    missing_reasons_json: Mapped[str] = mapped_column(Text)
    provider_fixture_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_home_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_away_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    league_id: Mapped[str | None] = mapped_column(String, nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_starts_at: Mapped[str] = mapped_column(String)
    feature_sha256: Mapped[str] = mapped_column(String)
    feature_json: Mapped[str] = mapped_column(Text)
    source_evidence_json: Mapped[str] = mapped_column(Text)


# Name retained for the candidate terminology used by the implementation plan.
TeamRegistryCandidate = TeamRegistryReview
