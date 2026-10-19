"""Comprehensive tests for Authentication, Password Security, JWT Lifecycle, and Protected Endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.settings import UserSettings
from app.models.user import User


# ==========================================
# 1. Registration Tests
# ==========================================

@pytest.mark.asyncio
async def test_registration_success_atomic(client: TestClient, db_session: AsyncSession):
    """Test successful registration: Argon2 hashing, atomic UserSettings, sanitized response."""
    payload = {
        "email": "sarah.connor@example.com",
        "password": "super-secure-password-2026",
        "name": "Sarah Connor",
        "currency": "USD",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["success"] is True
    user_data = data["data"]
    assert user_data["email"] == "sarah.connor@example.com"
    assert user_data["name"] == "Sarah Connor"
    assert user_data["currency"] == "USD"
    assert "password" not in user_data
    assert "password_hash" not in user_data

    # Verify user exists in database with Argon2 hash
    stmt = select(User).where(User.email == "sarah.connor@example.com")
    result = await db_session.execute(stmt)
    user_in_db = result.scalar_one_or_none()

    assert user_in_db is not None
    assert user_in_db.password_hash != "super-secure-password-2026"
    assert user_in_db.password_hash.startswith("$argon2")
    assert verify_password("super-secure-password-2026", user_in_db.password_hash) is True

    # Verify default UserSettings was created atomically
    settings_stmt = select(UserSettings).where(UserSettings.user_id == user_in_db.id)
    settings_res = await db_session.execute(settings_stmt)
    settings_in_db = settings_res.scalar_one_or_none()
    assert settings_in_db is not None
    assert settings_in_db.currency == "USD"


@pytest.mark.asyncio
async def test_registration_duplicate_email(client: TestClient, db_session: AsyncSession):
    """Test duplicate registration returns 409 Conflict with EMAIL_ALREADY_REGISTERED."""
    existing_user = User(
        email="existing@example.com",
        name="Existing User",
        password_hash=hash_password("password123"),
    )
    db_session.add(existing_user)
    await db_session.commit()

    payload = {
        "email": "existing@example.com",
        "password": "another-password",
        "name": "Duplicate User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409

    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_registration_validation_rules(client: TestClient):
    """Test password length requirement (>= 8 chars) and invalid email format."""
    # Password too short (< 8 chars)
    short_pw_payload = {
        "email": "test@example.com",
        "password": "short",
        "name": "Test User",
    }
    res1 = client.post("/api/v1/auth/register", json=short_pw_payload)
    assert res1.status_code == 422

    # Invalid email format
    invalid_email_payload = {
        "email": "not-an-email",
        "password": "validpassword123",
        "name": "Test User",
    }
    res2 = client.post("/api/v1/auth/register", json=invalid_email_payload)
    assert res2.status_code == 422


# ==========================================
# 2. Login Tests
# ==========================================

@pytest.mark.asyncio
async def test_login_success(client: TestClient, db_session: AsyncSession):
    """Test login with valid credentials returns JWT access token and user."""
    raw_password = "correct-horse-battery-staple"
    user = User(
        email="login.test@example.com",
        name="Login Tester",
        password_hash=hash_password(raw_password),
    )
    db_session.add(user)
    await db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login.test@example.com", "password": raw_password},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["email"] == "login.test@example.com"
    assert "password_hash" not in data["user"]


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: TestClient, db_session: AsyncSession):
    """Test login failure on wrong password or nonexistent email (uniform 401 response)."""
    user = User(
        email="known.user@example.com",
        name="Known User",
        password_hash=hash_password("actual-password-123"),
    )
    db_session.add(user)
    await db_session.commit()

    # Wrong password
    res1 = client.post(
        "/api/v1/auth/login",
        json={"email": "known.user@example.com", "password": "wrong-password"},
    )
    assert res1.status_code == 401
    assert res1.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # Unknown email
    res2 = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown.user@example.com", "password": "any-password"},
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ==========================================
# 3. Current User & Protected Route Tests
# ==========================================

@pytest.mark.asyncio
async def test_get_current_user_profile(client: TestClient, db_session: AsyncSession):
    """Test GET /api/v1/auth/me with valid Bearer token."""
    user = User(
        email="me.user@example.com",
        name="Me User",
        password_hash=hash_password("valid-password"),
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == user.id
    assert data["data"]["email"] == "me.user@example.com"


def test_get_current_user_missing_or_malformed_token(client: TestClient):
    """Test 401 error responses for missing or malformed tokens."""
    # Missing header
    res1 = client.get("/api/v1/auth/me")
    assert res1.status_code == 401
    assert res1.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Malformed header scheme
    res2 = client.get("/api/v1/auth/me", headers={"Authorization": "Basic 12345"})
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "INVALID_TOKEN"

    # Invalid JWT string
    res3 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert res3.status_code == 401
    assert res3.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_expired_token_rejected(client: TestClient, db_session: AsyncSession):
    """Test that expired JWT returns 401 TOKEN_EXPIRED."""
    user = User(
        email="expired@example.com",
        name="Expired User",
        password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.commit()

    # Create expired token
    expired_token = create_access_token(
        user.id,
        expires_delta=timedelta(seconds=-10),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_inactive_user_rejected(client: TestClient, db_session: AsyncSession):
    """Test that inactive users are rejected during login and /me access."""
    inactive_user = User(
        email="inactive@example.com",
        name="Inactive User",
        password_hash=hash_password("password123"),
        is_active=False,
    )
    db_session.add(inactive_user)
    await db_session.commit()

    # Login rejection
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "password123"},
    )
    assert login_res.status_code == 401
    assert login_res.json()["error"]["code"] == "USER_INACTIVE"

    # /me access rejection
    token = create_access_token(inactive_user.id)
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 401
    assert me_res.json()["error"]["code"] == "USER_INACTIVE"


# ==========================================
# 4. Token Tampering & Security
# ==========================================

def test_tampered_jwt_signature_rejected():
    """Test that token signed with a different secret is rejected."""
    fake_token = jwt.encode(
        {"sub": "user-123", "exp": datetime.now(timezone.utc) + timedelta(hours=1), "type": "access"},
        "wrong-secret-key",
        algorithm="HS256",
    )
    with pytest.raises(Exception) as exc_info:
        decode_access_token(fake_token)
    assert exc_info.value.code == "INVALID_TOKEN"


def test_wrong_token_type_rejected():
    """Test that non-access token type is rejected."""
    refresh_token = jwt.encode(
        {"sub": "user-123", "exp": datetime.now(timezone.utc) + timedelta(hours=1), "type": "refresh"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(Exception) as exc_info:
        decode_access_token(refresh_token)
    assert exc_info.value.code == "INVALID_TOKEN"


def test_logout_endpoint(client: TestClient):
    """Test logout endpoint returns 200 OK acknowledgment."""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_complete_authenticated_lifecycle_in_isolated_fixture(client: TestClient, db_session: AsyncSession):
    """
    Test the complete end-to-end user journey in an isolated test fixture:
    1. Register new user
    2. Login and retrieve JWT
    3. Access /auth/me
    4. Access initial empty /dashboard
    5. Add income and expense transactions
    6. Verify updated /dashboard metrics and spending breakdown
    7. Query /transactions with pagination
    8. Logout
    """
    email = "lifecycle.user@example.com"
    password = "LifecyclePass2026!"
    name = "Lifecycle Tester"

    # 1. Register
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name, "currency": "INR"},
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["data"]["email"] == email

    # 2. Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token = login_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Current user profile
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["data"]["name"] == name

    # 4. Initial empty Dashboard
    dash_init = client.get("/api/v1/dashboard", headers=headers)
    assert dash_init.status_code == 200
    init_data = dash_init.json()["data"]
    assert Decimal(str(init_data["netWorth"])) == Decimal("0")
    assert Decimal(str(init_data["monthlyIncome"])) == Decimal("0")
    assert Decimal(str(init_data["monthlyExpenses"])) == Decimal("0")
    assert init_data["transactions"] == []

    # 5. Add transactions
    tx1_res = client.post(
        "/api/v1/transactions",
        json={"title": "Salary", "amount": 80000.0, "category": "Salary", "type": "credit"},
        headers=headers,
    )
    assert tx1_res.status_code == 200

    tx2_res = client.post(
        "/api/v1/transactions",
        json={"title": "Rent", "amount": 25000.0, "category": "Housing", "type": "debit"},
        headers=headers,
    )
    assert tx2_res.status_code == 200

    # 6. Verify updated Dashboard
    dash_updated = client.get("/api/v1/dashboard", headers=headers)
    assert dash_updated.status_code == 200
    up_data = dash_updated.json()["data"]
    assert Decimal(str(up_data["netWorth"])) == Decimal("55000.00")
    assert Decimal(str(up_data["monthlyIncome"])) == Decimal("80000.00")
    assert Decimal(str(up_data["monthlyExpenses"])) == Decimal("25000.00")
    assert Decimal(str(up_data["savings"])) == Decimal("55000.00")
    assert up_data["summary"]["savingsRate"] == 68.8
    assert len(up_data["transactions"]) == 2
    assert len(up_data["spending"]) == 1
    assert up_data["spending"][0]["category"] == "Housing"

    # 7. Query Transactions list
    tx_list = client.get("/api/v1/transactions", headers=headers)
    assert tx_list.status_code == 200
    assert tx_list.json()["data"]["total"] == 2

    # 8. Logout
    logout_res = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200

