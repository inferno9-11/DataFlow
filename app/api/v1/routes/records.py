import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import get_current_user, get_record_service
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.record import (
    BulkRecordResultResponse,
    RecordBulkCreateRequest,
    RecordCreateRequest,
    RecordFilterParams,
    RecordResponse,
    RecordUpdateRequest,
)
from app.services.record_service import RecordService

router = APIRouter(prefix="/records", tags=["Records"])
settings = get_settings()


@router.post(
    "",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single transaction record",
)
async def create_record(
    payload: RecordCreateRequest,
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> RecordResponse:
    return await record_service.create_record(current_user.id, payload)


@router.post(
    "/bulk",
    response_model=BulkRecordResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Synchronously ingest a batch of transaction records",
)
async def bulk_create_records(
    request: Request,
    payload: RecordBulkCreateRequest,
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> BulkRecordResultResponse:
    # Rate limit bulk submissions
    client_ip = request.client.host if request.client else "unknown"
    await limiter.check_rate_limit(
        key=f"bulk_records:{current_user.id}:{client_ip}",
        max_requests=settings.RATE_LIMIT_BULK_PER_MINUTE,
        window_seconds=60,
    )
    return await record_service.bulk_create_records(current_user.id, payload)


@router.get(
    "",
    response_model=PaginatedResponse[RecordResponse],
    summary="List transaction records with filtering, allowlisted sorting, and pagination",
)
async def list_records(
    account_id: str | None = Query(None, description="Filter by account ID"),
    status: str | None = Query(
        None, description="Filter by status: pending, cleared, flagged, rejected"
    ),
    category: str | None = Query(
        None, description="Filter by category: payment, transfer, refund, withdrawal, deposit"
    ),
    currency: str | None = Query(None, description="Filter by 3-letter currency code"),
    min_amount: Decimal | None = Query(None, ge=0, description="Minimum transaction amount"),
    max_amount: Decimal | None = Query(None, ge=0, description="Maximum transaction amount"),
    start_date: datetime | None = Query(None, description="Occurred at or after timestamp (UTC)"),
    end_date: datetime | None = Query(None, description="Occurred at or before timestamp (UTC)"),
    sort_by: str = Query(
        default="occurred_at",
        description="Sort field: occurred_at, amount, created_at, transaction_id, status",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc", description="Sort direction: asc or desc"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=1000, description="Page size"),
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> PaginatedResponse[RecordResponse]:
    filters = RecordFilterParams(
        account_id=account_id,
        status=status,
        category=category,
        currency=currency,
        min_amount=min_amount,
        max_amount=max_amount,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return await record_service.list_records(current_user.id, filters)


@router.get(
    "/{record_id}",
    response_model=RecordResponse,
    summary="Retrieve a transaction record by ID",
)
async def get_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> RecordResponse:
    return await record_service.get_record(record_id, current_user.id)


@router.patch(
    "/{record_id}",
    response_model=RecordResponse,
    summary="Update transaction record details",
)
async def update_record(
    record_id: uuid.UUID,
    payload: RecordUpdateRequest,
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> RecordResponse:
    return await record_service.update_record(record_id, current_user.id, payload)


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transaction record",
)
async def delete_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    record_service: RecordService = Depends(get_record_service),
) -> None:
    await record_service.delete_record(record_id, current_user.id)
