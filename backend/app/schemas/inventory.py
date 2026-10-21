"""Pydantic schemas: validate everything coming in, shape everything going out."""
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, field_validator

MAX_QUANTITY = 1_000_000

# Datetimes are stored as naive UTC; send them to the browser with a trailing "Z".
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(
        lambda value: value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        return_type=str,
    ),
]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
SupplierName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Threshold = Annotated[int, Field(ge=0, le=MAX_QUANTITY)]

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,39}$")


def _clean_sku(value: str) -> str:
    sku = value.strip().upper()
    if not SKU_PATTERN.match(sku):
        raise ValueError("SKU may only contain letters, numbers, '-' and '_' (max 40 characters)")
    return sku


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    sku: str
    category: Category
    unit: Unit = "pcs"
    quantity: Annotated[int, Field(ge=0, le=MAX_QUANTITY)] = 0  # opening quantity
    reorder_threshold: Threshold = 0
    supplier_name: SupplierName | None = None

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        return _clean_sku(value)

    @field_validator("supplier_name")
    @classmethod
    def validate_supplier(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ItemUpdate(BaseModel):
    """Edit product details. Quantity is deliberately NOT editable here:
    it can only change through stock movements so every change is recorded."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    sku: str | None = None
    category: Category | None = None
    unit: Unit | None = None
    reorder_threshold: Threshold | None = None
    supplier_name: SupplierName | None = None

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str | None) -> str | None:
        return None if value is None else _clean_sku(value)

    @field_validator("supplier_name")
    @classmethod
    def validate_supplier(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_type: Literal["in", "out"]
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    # Optional idempotency key. If the same request is sent twice (double click,
    # network retry), the stock is changed only once.
    request_id: Annotated[str, StringConstraints(min_length=8, max_length=64)] | None = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    unit: str
    quantity: int
    reorder_threshold: int
    supplier_name: str | None
    is_archived: bool
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    created_at: UTCDateTime
    updated_at: UTCDateTime


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    user_id: int
    user_name: str | None = None
    movement_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reason: str | None
    created_at: UTCDateTime


class MovementResult(BaseModel):
    movement: MovementOut
    item: ItemOut
    already_applied: bool = False  # True when a retried request was recognised


class InventorySummary(BaseModel):
    total_products: int
    in_stock: int
    low_stock: int
    out_of_stock: int
    archived: int
