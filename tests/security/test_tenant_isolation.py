import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tenant_isolation_prevents_cross_user_access(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
):
    # User 1 creates a private record
    payload = {
        "transaction_id": "u1_secret_txn",
        "account_id": "acc_private",
        "amount": 999.99,
        "currency": "USD",
        "category": "payment",
        "merchant_name": "Private Merchant",
    }
    u1_create = await client.post("/api/v1/records", json=payload, headers=auth_headers)
    assert u1_create.status_code == 201
    record_id = u1_create.json()["id"]

    # User 1 creates a private job
    job_payload = {
        "job_type": "bulk_transaction_ingest",
        "records": [payload],
    }
    u1_job = await client.post("/api/v1/jobs", json=job_payload, headers=auth_headers)
    assert u1_job.status_code == 202
    job_id = u1_job.json()["id"]

    # 1. User 2 attempts to GET User 1's record -> 404
    u2_get_record = await client.get(f"/api/v1/records/{record_id}", headers=second_user_headers)
    assert u2_get_record.status_code == 404
    assert u2_get_record.json()["error"]["code"] == "NOT_FOUND"

    # 2. User 2 attempts to PATCH User 1's record -> 404
    u2_patch = await client.patch(
        f"/api/v1/records/{record_id}",
        json={"merchant_name": "Hacked Merchant"},
        headers=second_user_headers,
    )
    assert u2_patch.status_code == 404

    # 3. User 2 attempts to DELETE User 1's record -> 404
    u2_delete = await client.delete(f"/api/v1/records/{record_id}", headers=second_user_headers)
    assert u2_delete.status_code == 404

    # 4. User 2 lists records -> User 1's record is NOT present
    u2_list = await client.get("/api/v1/records", headers=second_user_headers)
    assert u2_list.status_code == 200
    u2_records = [r["id"] for r in u2_list.json()["items"]]
    assert record_id not in u2_records

    # 5. User 2 attempts to inspect User 1's job -> 404
    u2_get_job = await client.get(f"/api/v1/jobs/{job_id}", headers=second_user_headers)
    assert u2_get_job.status_code == 404

    # 6. User 2 attempts to retry User 1's job -> 404
    u2_retry_job = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=second_user_headers)
    assert u2_retry_job.status_code == 404
