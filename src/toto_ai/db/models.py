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
