from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class AnomalyFlag(Base):
    """One AI check of one stock OUT movement (Feature 9).

    The AI (PyTorch autoencoder on a RunPod GPU) compares the day's usage of a product
    with its recent daily usage. A result of "Unusual" or "Highly Unusual" is a
    POTENTIAL anomaly for a human to review, never a confirmed error, and it never
    changes stock.

    movement_id and request_id are unique, so a retried check can never create a
    second record for the same movement.
    """

    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("stock_movements.id"), unique=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)

    # What the AI was asked (kept so the result can be explained later)
    day_total_out: Mapped[int] = mapped_column(Integer)          # units used that day, incl. this movement
    recent_avg_usage: Mapped[float] = mapped_column(Float)
    usage_std: Mapped[float] = mapped_column(Float)
    history_days: Mapped[int] = mapped_column(Integer)

    # What the AI answered
    status: Mapped[str] = mapped_column(String(30), index=True)  # Normal / Unusual / Highly Unusual / ...
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_feature: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    device: Mapped[str | None] = mapped_column(String(20), nullable=True)   # "cuda" proves the GPU ran it
    model_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inference_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # why there is no score

    # Human review
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)