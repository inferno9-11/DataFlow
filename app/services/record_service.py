import uuid
from decimal import Decimal
from typing import Any

from app.core.errors import NotFoundError
from app.models.record import TransactionRecord
from app.repositories.record_repository import RecordRepository
from app.schemas.common import PaginatedResponse
from app.schemas.record import (
    BulkRecordResultResponse,
    RecordBulkCreateRequest,
    RecordCreateRequest,
    RecordFilterParams,
    RecordResponse,
    RecordUpdateRequest,
)


def compute_risk_score(
    amount: Decimal, category: str, metadata: dict[str, Any] | None = None
) -> float:
    """
    Evaluates transaction risk based on monetary thresholds, transaction category,
    and device/network heuristics.
    """
    score = 0.05
    if amount >= 50000:
        score += 0.50
    elif amount >= 10000:
        score += 0.30
    elif amount >= 2500:
        score += 0.15

    if category in ("withdrawal", "transfer"):
        score += 0.10

    if metadata and isinstance(metadata, dict):
        if metadata.get("is_vpn") or metadata.get("is_tor"):
            score += 0.25
        if metadata.get("device_changed"):
            score += 0.15
        if metadata.get("failed_pin_attempts", 0) > 2:
            score += 0.20

    return min(1.0, max(0.0, round(score, 2)))


def determine_initial_status(risk_score: float) -> str:
    if risk_score >= 0.85:
        return "rejected"
    elif risk_score >= 0.65:
        return "flagged"
    return "cleared"


class RecordService:
    def __init__(self, record_repo: RecordRepository):
        self.record_repo = record_repo

    async def create_record(
        self, user_id: uuid.UUID, payload: RecordCreateRequest
    ) -> RecordResponse:
        # Check idempotency
        if payload.idempotency_key:
            existing = await self.record_repo.get_by_idempotency_key(
                payload.idempotency_key, user_id
            )
            if existing:
                return RecordResponse.model_validate(existing)

        risk_score = compute_risk_score(payload.amount, payload.category, payload.metadata)
        status = determine_initial_status(risk_score)

        record = TransactionRecord(
            user_id=user_id,
            transaction_id=payload.transaction_id,
            account_id=payload.account_id,
            amount=payload.amount,
            currency=payload.currency,
            category=payload.category,
            merchant_name=payload.merchant_name,
            status=status,
            risk_score=risk_score,
            idempotency_key=payload.idempotency_key,
            metadata_json=payload.metadata,
            occurred_at=payload.occurred_at,
        )
        saved = await self.record_repo.create(record)
        return RecordResponse.model_validate(saved)

    async def bulk_create_records(
        self, user_id: uuid.UUID, payload: RecordBulkCreateRequest
    ) -> BulkRecordResultResponse:
        """
        Synchronous bulk ingest for small-to-medium batches.
        Applies idempotency deduplication per user.
        """
        records_to_insert: list[TransactionRecord] = []
        duplicates_skipped = 0
        seen_keys = set()

        for rec in payload.records:
            if rec.idempotency_key:
                if rec.idempotency_key in seen_keys:
                    duplicates_skipped += 1
                    continue
                existing = await self.record_repo.get_by_idempotency_key(
                    rec.idempotency_key, user_id
                )
                if existing:
                    duplicates_skipped += 1
                    continue
                seen_keys.add(rec.idempotency_key)

            risk_score = compute_risk_score(rec.amount, rec.category, rec.metadata)
            status = determine_initial_status(risk_score)

            records_to_insert.append(
                TransactionRecord(
                    user_id=user_id,
                    transaction_id=rec.transaction_id,
                    account_id=rec.account_id,
                    amount=rec.amount,
                    currency=rec.currency,
                    category=rec.category,
                    merchant_name=rec.merchant_name,
                    status=status,
                    risk_score=risk_score,
                    idempotency_key=rec.idempotency_key,
                    metadata_json=rec.metadata,
                    occurred_at=rec.occurred_at,
                )
            )

        inserted = await self.record_repo.bulk_insert(records_to_insert)
        return BulkRecordResultResponse(
            inserted_count=len(inserted),
            failed_count=0,
            duplicates_skipped=duplicates_skipped,
        )

    async def get_record(self, record_id: uuid.UUID, user_id: uuid.UUID) -> RecordResponse:
        record = await self.record_repo.get_by_id(record_id, user_id)
        if not record:
            raise NotFoundError("Record", record_id)
        return RecordResponse.model_validate(record)

    async def list_records(
        self, user_id: uuid.UUID, filters: RecordFilterParams
    ) -> PaginatedResponse[RecordResponse]:
        items, total_count = await self.record_repo.filter_and_paginate(user_id, filters)
        record_responses = [RecordResponse.model_validate(item) for item in items]
        return PaginatedResponse.create(
            items=record_responses,
            total_count=total_count,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def update_record(
        self, record_id: uuid.UUID, user_id: uuid.UUID, payload: RecordUpdateRequest
    ) -> RecordResponse:
        existing = await self.record_repo.get_by_id(record_id, user_id)
        if not existing:
            raise NotFoundError("Record", record_id)

        update_dict = payload.model_dump(exclude_unset=True)
        if "metadata" in update_dict:
            update_dict["metadata_json"] = update_dict.pop("metadata")

        updated = await self.record_repo.update(record_id, user_id, update_dict)
        return RecordResponse.model_validate(updated)

    async def delete_record(self, record_id: uuid.UUID, user_id: uuid.UUID) -> None:
        deleted = await self.record_repo.delete(record_id, user_id)
        if not deleted:
            raise NotFoundError("Record", record_id)
