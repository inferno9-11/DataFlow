import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    records: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="List of transaction records for asynchronous background validation and ingestion",
    )
    job_type: str = Field(default="bulk_transaction_ingest", max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_type: str
    status: str
    total_records: int
    processed_records: int
    failed_records: int
    retry_count: int
    max_retries: int
    idempotency_key: str | None
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobItemErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    row_index: int
    raw_data: dict[str, Any] | None
    error_code: str
    error_message: str
    created_at: datetime


class JobDetailResponse(JobResponse):
    errors: list[JobItemErrorResponse] = []


class JobFilterParams(BaseModel):
    status: str | None = None
    job_type: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
