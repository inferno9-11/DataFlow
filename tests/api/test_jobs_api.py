import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.job_repository import JobRepository


@pytest.mark.asyncio
async def test_job_submission_and_inspection(client: AsyncClient, auth_headers: dict):
    payload = {
        "job_type": "bulk_transaction_ingest",
        "records": [
            {
                "transaction_id": "txn_job_1",
                "account_id": "acc_job",
                "amount": 100.0,
                "currency": "USD",
                "category": "payment",
                "merchant_name": "Store A",
            },
            {
                "transaction_id": "txn_job_2",
                "account_id": "acc_job",
                "amount": 200.0,
                "currency": "USD",
                "category": "payment",
                "merchant_name": "Store B",
            },
        ],
        "idempotency_key": "job_idem_001",
    }

    # 1. Submit job (returns 202 Accepted)
    submit_resp = await client.post("/api/v1/jobs", json=payload, headers=auth_headers)
    assert submit_resp.status_code == 202
    job_data = submit_resp.json()
    job_id = job_data["id"]
    assert job_data["status"] == "queued"
    assert job_data["total_records"] == 2

    # 2. Idempotent re-submission returns same job
    idem_resp = await client.post("/api/v1/jobs", json=payload, headers=auth_headers)
    assert idem_resp.status_code == 202
    assert idem_resp.json()["id"] == job_id

    # 3. List jobs
    list_resp = await client.get("/api/v1/jobs", headers=auth_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total_count"] >= 1

    # 4. Get job details
    detail_resp = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == job_id
    assert "errors" in detail_resp.json()


@pytest.mark.asyncio
async def test_job_retry_validation(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    # Create a job directly in db in failed state to test retry API
    payload = {
        "job_type": "bulk_transaction_ingest",
        "records": [
            {
                "transaction_id": "retry_txn",
                "account_id": "a",
                "amount": 10,
                "currency": "USD",
                "category": "payment",
                "merchant_name": "m",
            }
        ],
    }
    submit_resp = await client.post("/api/v1/jobs", json=payload, headers=auth_headers)
    job_id = submit_resp.json()["id"]

    # Attempting to retry a 'queued' job should fail with 400 Bad Request
    bad_retry = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers)
    assert bad_retry.status_code == 400

    # Manually transition job to 'failed' in DB
    job_repo = JobRepository(db_session)
    await job_repo.update_job(uuid.UUID(job_id), {"status": "failed"})
    await db_session.commit()

    # Retry should now succeed
    retry_resp = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers)
    assert retry_resp.status_code == 200
    retried_data = retry_resp.json()
    assert retried_data["status"] == "queued"
    assert retried_data["retry_count"] == 1
