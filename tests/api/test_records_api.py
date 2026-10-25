import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_record_crud_lifecycle(client: AsyncClient, auth_headers: dict):
    # 1. Create Record
    payload = {
        "transaction_id": "txn_test_100",
        "account_id": "acc_main",
        "amount": 250.00,
        "currency": "USD",
        "category": "payment",
        "merchant_name": "Digital Services Inc",
        "idempotency_key": "idem_test_100",
    }
    create_resp = await client.post("/api/v1/records", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    record_id = created_data["id"]
    assert created_data["transaction_id"] == "txn_test_100"
    assert created_data["status"] == "cleared"
    assert created_data["risk_score"] > 0.0

    # 2. Idempotent re-submission returns identical record without duplication
    idem_resp = await client.post("/api/v1/records", json=payload, headers=auth_headers)
    assert idem_resp.status_code == 201
    assert idem_resp.json()["id"] == record_id

    # 3. Retrieve single record
    get_resp = await client.get(f"/api/v1/records/{record_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == record_id

    # 4. Patch record
    patch_resp = await client.patch(
        f"/api/v1/records/{record_id}",
        json={"merchant_name": "Updated Merchant Name", "status": "flagged"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["merchant_name"] == "Updated Merchant Name"
    assert patch_resp.json()["status"] == "flagged"

    # 5. List with filters
    list_resp = await client.get(
        "/api/v1/records?status=flagged&page=1&page_size=10",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total_count"] >= 1
    assert len(list_data["items"]) >= 1

    # 6. Delete record
    del_resp = await client.delete(f"/api/v1/records/{record_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # 7. Subsequent retrieval returns 404
    get_again = await client.get(f"/api/v1/records/{record_id}", headers=auth_headers)
    assert get_again.status_code == 404
    assert get_again.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_bulk_record_ingestion_api(client: AsyncClient, auth_headers: dict):
    bulk_payload = {
        "records": [
            {
                "transaction_id": f"txn_bulk_{i}",
                "account_id": "acc_bulk",
                "amount": 50.0 + i,
                "currency": "USD",
                "category": "payment",
                "merchant_name": f"Bulk Merchant {i}",
            }
            for i in range(5)
        ]
    }
    resp = await client.post("/api/v1/records/bulk", json=bulk_payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["inserted_count"] == 5
    assert data["failed_count"] == 0
