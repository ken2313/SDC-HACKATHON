from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

REVIEW_NOTE = "Potential anomaly for human review, not a confirmed error."


class AnomalyFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    sku: str
    product_name: str
    unit: str
    movement_id: int
    day_total_out: int
    recent_avg_usage: float
    history_days: int
    status: str
    anomaly_score: float | None
    top_feature: str | None
    expected_low: float | None
    expected_high: float | None
    device: str | None
    model_version: str | None
    inference_ms: float | None
    reason: str | None
    reviewed: bool
    reviewed_by: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime
    note: str = REVIEW_NOTE


class AnomalyReview(BaseModel):
    note: str = Field(min_length=1, max_length=500)