import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_CATEGORIES = {"payment", "transfer", "refund", "withdrawal", "deposit"}
VALID_STATUSES = {"pending", "cleared", "flagged", "rejected"}
ALLOWED_SORT_FIELDS = {"occurred_at", "amount", "created_at", "transaction_id", "status"}


class RecordBase(BaseModel):
    transaction_id: str = Field(..., min_length=3, max_length=64, examples=["txn_20261026_001"])
    account_id: str = Field(..., min_length=3, max_length=64, examples=["acc_98765"])
    amount: Decimal = Field(..., gt=0, decimal_places=4, examples=[129.50])
    currency: str = Field(..., min_length=3, max_length=3, examples=["USD"])
    category: str = Field(..., examples=["payment"])
    merchant_name: str = Field(
        ..., min_length=1, max_length=128, examples=["Stripe Cloud Services"]
    )
    idempotency_key: str | None = Field(default=None, max_length=128, examples=["idem_txn_001"])
    metadata: dict[str, Any] | None = Field(
        default=None, examples=[{"channel": "mobile_app", "ip": "192.168.1.1"}]
    )
    occurred_at: datetime | None = Field(
        default_factory=lambda: datetime.now(UTC),
        examples=["2026-10-26T03:00:00Z"],
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        v_upper = v.upper().strip()
        if len(v_upper) != 3 or not v_upper.isalpha():
            raise ValueError("Currency must be a valid 3-letter ISO code (e.g., USD, EUR).")
        return v_upper

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        v_lower = v.lower().strip()
        if v_lower not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
        return v_lower


class RecordCreateRequest(RecordBase):
    pass


class RecordUpdateRequest(BaseModel):
    merchant_name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None:
            v_lower = v.lower().strip()
            if v_lower not in VALID_CATEGORIES:
                raise ValueError(f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
            return v_lower
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            v_lower = v.lower().strip()
            if v_lower not in VALID_STATUSES:
                raise ValueError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}")
            return v_lower
        return v


class RecordBulkCreateRequest(BaseModel):
    records: list[RecordCreateRequest] = Field(..., min_length=1, max_length=5000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    transaction_id: str
    account_id: str
    amount: Decimal
    currency: str
    category: str
    merchant_name: str
    status: str
    risk_score: float
    idempotency_key: str | None
    metadata_json: dict[str, Any] | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class BulkRecordResultResponse(BaseModel):
    inserted_count: int
    failed_count: int
    duplicates_skipped: int
    job_id: uuid.UUID | None = None
    errors: list[dict[str, Any]] = []


class RecordFilterParams(BaseModel):
    account_id: str | None = None
    status: str | None = None
    category: str | None = None
    currency: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    sort_by: str = Field(default="occurred_at")
    sort_order: Literal["asc", "desc"] = Field(default="desc")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        if v not in ALLOWED_SORT_FIELDS:
            raise ValueError(f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORT_FIELDS))}")
        return v
