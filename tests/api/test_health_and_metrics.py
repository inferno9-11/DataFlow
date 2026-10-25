import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_probe(client: AsyncClient):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_probe(client: AsyncClient):
    resp = await client.get("/health/ready")
    # In test environment, in-memory sqlite is connected, redis may be disconnected (degraded)
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "dependencies" in data
    assert data["dependencies"]["database"] == "connected"


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(client: AsyncClient):
    # Trigger a request first so metrics counter exists
    await client.get("/health/live")

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text_content = resp.text
    assert "dataflow_http_requests_total" in text_content
