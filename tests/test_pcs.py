"""
Tests for PC management endpoints.
"""
import pytest
from httpx import AsyncClient


async def get_auth_token(client: AsyncClient, user_data: dict) -> str:
    """Helper to register, login and get token."""
    await client.post("/api/v1/auth/register", json=user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"],
        },
    )
    return login_response.json()["access_token"]


@pytest.mark.asyncio
async def test_create_pc(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test creating a new PC."""
    token = await get_auth_token(client, test_user_data)

    response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_pc_data["name"]
    assert "stream_key" in data
    assert len(data["stream_key"]) > 20


@pytest.mark.asyncio
async def test_create_pc_unauthenticated(
    client: AsyncClient,
    test_pc_data: dict,
):
    """Test creating PC without authentication."""
    response = await client.post("/api/v1/pcs", json=test_pc_data)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_pcs(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test listing user's PCs."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )

    # List PCs
    response = await client.get(
        "/api/v1/pcs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == test_pc_data["name"]


@pytest.mark.asyncio
async def test_get_pc_detail(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test getting PC details."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    pc_id = create_response.json()["id"]

    # Get PC detail
    response = await client.get(
        f"/api/v1/pcs/{pc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == test_pc_data["name"]
    assert "rtmp_url" in data
    assert "hls_url" in data


@pytest.mark.asyncio
async def test_update_pc(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test updating PC."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    pc_id = create_response.json()["id"]

    # Update PC
    response = await client.patch(
        f"/api/v1/pcs/{pc_id}",
        json={"name": "Updated PC", "is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated PC"
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_regenerate_stream_key(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test regenerating stream key."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    pc_id = create_response.json()["id"]
    old_key = create_response.json()["stream_key"]

    # Regenerate key
    response = await client.post(
        f"/api/v1/pcs/{pc_id}/regenerate-key",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    new_key = response.json()["stream_key"]
    assert new_key != old_key


@pytest.mark.asyncio
async def test_delete_pc(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test deleting PC."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    pc_id = create_response.json()["id"]

    # Delete PC
    response = await client.delete(
        f"/api/v1/pcs/{pc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    # Verify PC is gone
    response = await client.get(
        f"/api/v1/pcs/{pc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pc_access_control(
    client: AsyncClient,
    test_user_data: dict,
    test_admin_data: dict,
    test_pc_data: dict,
):
    """Test that users can't access other users' PCs."""
    # Create PC as user1
    token1 = await get_auth_token(client, test_user_data)
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token1}"},
    )
    pc_id = create_response.json()["id"]

    # Try to access as user2
    token2 = await get_auth_token(client, test_admin_data)
    response = await client.get(
        f"/api/v1/pcs/{pc_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_pc_sessions(
    client: AsyncClient,
    test_user_data: dict,
    test_pc_data: dict,
):
    """Test listing sessions for a PC."""
    token = await get_auth_token(client, test_user_data)

    # Create a PC
    create_response = await client.post(
        "/api/v1/pcs",
        json=test_pc_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    pc_id = create_response.json()["id"]

    # List sessions (should be empty)
    response = await client.get(
        f"/api/v1/pcs/{pc_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
