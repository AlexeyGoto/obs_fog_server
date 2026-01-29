"""
Tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, test_user_data: dict):
    """Test successful user registration."""
    response = await client.post("/api/v1/auth/register", json=test_user_data)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == test_user_data["email"]
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user_data: dict):
    """Test registration with duplicate email."""
    # Register first time
    response = await client.post("/api/v1/auth/register", json=test_user_data)
    assert response.status_code == 201

    # Try to register again
    response = await client.post("/api/v1/auth/register", json=test_user_data)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_password_mismatch(client: AsyncClient):
    """Test registration with mismatched passwords."""
    data = {
        "email": "test@example.com",
        "password": "password123",
        "password_confirm": "different123",
    }
    response = await client.post("/api/v1/auth/register", json=data)

    assert response.status_code == 400
    assert "do not match" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Test registration with weak password."""
    data = {
        "email": "test@example.com",
        "password": "short",
        "password_confirm": "short",
    }
    response = await client.post("/api/v1/auth/register", json=data)

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user_data: dict):
    """Test successful login."""
    # Register user first
    await client.post("/api/v1/auth/register", json=test_user_data)

    # Login
    login_data = {
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    }
    response = await client.post("/api/v1/auth/login", json=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user_data: dict):
    """Test login with wrong password."""
    # Register user first
    await client.post("/api/v1/auth/register", json=test_user_data)

    # Login with wrong password
    login_data = {
        "email": test_user_data["email"],
        "password": "wrongpassword",
    }
    response = await client.post("/api/v1/auth/login", json=login_data)

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with nonexistent email."""
    login_data = {
        "email": "nonexistent@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/auth/login", json=login_data)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, test_user_data: dict):
    """Test getting current user profile when authenticated."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    token = login_response.json()["access_token"]

    # Get profile
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_data["email"]


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    """Test getting current user when not authenticated."""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, test_user_data: dict):
    """Test logout clears cookie."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )

    # Logout
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert "logged out" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, test_user_data: dict):
    """Test password change."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    token = login_response.json()["access_token"]

    # Change password
    new_password = "newpassword123"
    response = await client.post(
        "/api/v1/auth/password",
        json={
            "current_password": test_user_data["password"],
            "new_password": new_password,
            "new_password_confirm": new_password,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    # Verify old password doesn't work
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    assert response.status_code == 401

    # Verify new password works
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": new_password,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, test_user_data: dict):
    """Test token refresh."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    refresh_token = login_response.json()["refresh_token"]

    # Refresh tokens
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
