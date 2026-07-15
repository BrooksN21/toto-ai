from sqlalchemy import Float, Integer, String, UniqueConstraint
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
