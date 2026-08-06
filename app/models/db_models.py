"""
ORM models.

Stock: one row per ticker — slow-changing info (name, sector, business
description, Shariah screening result). Refreshed weekly, not every session.

PriceSnapshot: one row per (ticker, timestamp) — fast-changing price data.
Refreshed as often as we poll during a trading session. Kept as a running
history (not just "latest") so the reasoning agent can look at intraday
movement, not just a single point.
"""


from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base 


def utcnow() -> datetime:
    """Naive UTC datetime. SQLite has no timezone-aware column type, so a
    timezone-aware value written here comes back naive after a round-trip —
    comparing the two blows up. Staying naive everywhere avoids the mismatch."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str]= mapped_column(String(16), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255))

    sector: Mapped[str| None] = mapped_column(String(128), nullable=True)
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

    shariah_status: Mapped[str|None] = mapped_column(String(32), nullable=True)
    shariah_reason: Mapped[str|None] = mapped_column(Text, nullable=True)
    shariah_checked_at: Mapped[datetime| None] = mapped_column(DateTime, nullable=True)

    last_recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "BUY" | "HOLD" | "SELL"
    last_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_recommendation_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )

class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)

    price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[str | None] = mapped_column(String(32), nullable=True)  # kept as displayed (e.g. "447.75B")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    stock: Mapped["Stock"] = relationship(back_populates="price_snapshots")

class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[str] = mapped_column(Text)  # JSON-encoded list[float]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)