import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ProcessingJob
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.repositories.record_repository import RecordRepository
from app.schemas.record import RecordFilterParams
from app.workers.job_processor import process_job
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_worker_process_successful_batch(db_session: AsyncSession, test_user: User):
    job_repo = JobRepository(db_session)

    records = [
        {
            "transaction_id": f"txn_worker_{i}",
            "account_id": "acc_worker",
            "amount": 200.0,
            "currency": "USD",
            "category": "payment",
            "merchant_name": "Worker Merchant",
        }
        for i in range(3)
    ]

    job = ProcessingJob(
        user_id=test_user.id,
        job_type="bulk_transaction_ingest",
        status="queued",
        total_records=len(records),
        payload_records=records,
    )
    saved_job = await job_repo.create(job)
    await db_session.commit()

    # Process job via worker logic injecting test session factory
    result = await process_job(saved_job.id, session_factory=TestingSessionLocal)
    assert result["status"] == "completed"
    assert result["processed_records"] == 3
    assert result["failed_records"] == 0

    # Verify records persisted in DB
    record_repo = RecordRepository(db_session)
    filters = RecordFilterParams(account_id="acc_worker")
    items, total = await record_repo.filter_and_paginate(test_user.id, filters)
    assert total == 3


@pytest.mark.asyncio
async def test_worker_process_partial_failure_batch(db_session: AsyncSession, test_user: User):
    job_repo = JobRepository(db_session)

    # 1 valid, 1 invalid category, 1 duplicate transaction_id
    records = [
        {
            "transaction_id": "txn_valid_1",
            "account_id": "acc_mixed",
            "amount": 100.0,
            "currency": "USD",
            "category": "payment",
            "merchant_name": "Valid Store",
        },
        {
            "transaction_id": "txn_invalid_cat",
            "account_id": "acc_mixed",
            "amount": 50.0,
            "currency": "USD",
            "category": "bad_category_xyz",
            "merchant_name": "Invalid Store",
        },
        {
            "transaction_id": "txn_valid_1",  # Duplicate within batch
            "account_id": "acc_mixed",
            "amount": 75.0,
            "currency": "USD",
            "category": "payment",
            "merchant_name": "Duplicate Store",
        },
    ]

    job = ProcessingJob(
        user_id=test_user.id,
        job_type="bulk_transaction_ingest",
        status="queued",
        total_records=len(records),
        payload_records=records,
    )
    saved_job = await job_repo.create(job)
    await db_session.commit()

    result = await process_job(saved_job.id, session_factory=TestingSessionLocal)
    assert result["status"] == "partially_failed"
    assert result["processed_records"] == 1
    assert result["failed_records"] == 2

    # Verify error diagnostics
    refreshed_job = await job_repo.get_by_id(saved_job.id, test_user.id, include_errors=True)
    assert len(refreshed_job.item_errors) == 2
    error_codes = [err.error_code for err in refreshed_job.item_errors]
    assert "VALIDATION_ERROR" in error_codes
    assert "DUPLICATE_TRANSACTION_ID" in error_codes
