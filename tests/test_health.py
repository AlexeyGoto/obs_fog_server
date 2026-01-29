"""
Tests for health check and basic endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/healthz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns HTML page."""
    response = await client.get("/")

    assert response.status_code == 200
    # Root now returns HTML (home page)
    assert "text/html" in response.headers.get("content-type", "")
    assert b"OBS Fog" in response.content
