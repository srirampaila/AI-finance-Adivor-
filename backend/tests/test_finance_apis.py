"""Comprehensive tests for Phase 7D Core Finance APIs:
Transactions, Goals, Dashboard, Analytics, Notifications, and Settings.
Includes strict cross-user security tests, empty-state tests, and pagination tests.
"""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helper Auth Helpers
# ---------------------------------------------------------------------------

def register_and_get_token(client: TestClient, email: str, name: str, password: str = "SecurePass123!") -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": name, "password": password},
    )
    assert res.status_code == 201, res.text
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200, login_res.text
    return login_res.json()["data"]["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. TRANSACTIONS TESTS
# ---------------------------------------------------------------------------

def test_transaction_crud_and_validation(client: TestClient, db_session: AsyncSession):
    token_a = register_and_get_token(client, "tx_user_a@example.com", "User TX A")
    headers_a = auth_headers(token_a)

    # 1. Create Transaction (Debit)
    create_payload = {
        "title": "Grocery Superstore",
        "category": "Food & Dining",
        "amount": "2500.50",
        "type": "debit",
        "accountName": "HDFC Checking",
        "status": "completed",
    }
    create_res = client.post("/api/v1/transactions", json=create_payload, headers=headers_a)
    assert create_res.status_code == 200, create_res.text
    tx_data = create_res.json()["data"]
    tx_id = tx_data["id"]
    assert tx_data["title"] == "Grocery Superstore"
    assert tx_data["category"] == "Food & Dining"
    assert Decimal(str(tx_data["amount"])) == Decimal("2500.50")
    assert tx_data["type"] == "debit"
    assert tx_data["accountName"] == "HDFC Checking"

    # 2. Reject Invalid Amount (<= 0)
    bad_res = client.post(
        "/api/v1/transactions",
        json={"title": "Bad Tx", "category": "Food", "amount": "-100", "type": "debit"},
        headers=headers_a,
    )
    assert bad_res.status_code == 422

    # 3. Get Single Transaction
    get_res = client.get(f"/api/v1/transactions/{tx_id}", headers=headers_a)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == tx_id

    # 4. Patch Transaction
    patch_res = client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"amount": "2750.00", "status": "pending"},
        headers=headers_a,
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()["data"]
    assert Decimal(str(updated_data["amount"])) == Decimal("2750.00")
    assert updated_data["status"] == "pending"

    # 5. Delete Transaction
    del_res = client.delete(f"/api/v1/transactions/{tx_id}", headers=headers_a)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted"] is True

    # Confirm gone
    get_after_del = client.get(f"/api/v1/transactions/{tx_id}", headers=headers_a)
    assert get_after_del.status_code == 404


def test_transaction_missing_and_malformed_financial_values(client: TestClient, db_session: AsyncSession):
    """Verify rejection of missing, non-numeric, zero, negative, and invalid enum values."""
    token = register_and_get_token(client, "tx_malformed_test@example.com", "Malformed Tester")
    headers = auth_headers(token)

    # 1. Missing amount
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Missing Amount", "category": "Food", "type": "debit"},
        headers=headers,
    )
    assert res.status_code == 422

    # 2. Missing title
    res = client.post(
        "/api/v1/transactions",
        json={"category": "Food", "amount": "100.00", "type": "debit"},
        headers=headers,
    )
    assert res.status_code == 422

    # 3. Missing type
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Missing Type", "category": "Food", "amount": "100.00"},
        headers=headers,
    )
    assert res.status_code == 422

    # 4. Non-numeric amount string
    res = client.post(
        "/api/v1/transactions",
        json={"title": "NaN Amount", "category": "Food", "amount": "not-a-number", "type": "debit"},
        headers=headers,
    )
    assert res.status_code == 422

    # 5. Zero amount (gt=0 constraint)
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Zero Amount", "category": "Food", "amount": 0, "type": "debit"},
        headers=headers,
    )
    assert res.status_code == 422

    # 6. Negative amount
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Negative Amount", "category": "Food", "amount": -150.50, "type": "debit"},
        headers=headers,
    )
    assert res.status_code == 422

    # 7. Invalid transaction type enum
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Invalid Type", "category": "Food", "amount": 100, "type": "wire_transfer"},
        headers=headers,
    )
    assert res.status_code == 422

    # 8. Invalid status enum
    res = client.post(
        "/api/v1/transactions",
        json={"title": "Invalid Status", "category": "Food", "amount": 100, "type": "debit", "status": "settled"},
        headers=headers,
    )
    assert res.status_code == 422


def test_transaction_pagination_and_filtering(client: TestClient, db_session: AsyncSession):
    token = register_and_get_token(client, "tx_filter_user@example.com", "Filter User")
    headers = auth_headers(token)

    # Seed 5 transactions
    categories = ["Food", "Food", "Shopping", "Salary", "Investment"]
    types = ["debit", "debit", "debit", "credit", "credit"]
    amounts = ["100", "200", "300", "5000", "1500"]

    for cat, t_type, amt in zip(categories, types, amounts):
        res = client.post(
            "/api/v1/transactions",
            json={"title": f"Tx {cat}", "category": cat, "amount": amt, "type": t_type},
            headers=headers,
        )
        assert res.status_code == 200

    # 1. Filter by category
    food_res = client.get("/api/v1/transactions?category=Food", headers=headers)
    assert food_res.status_code == 200
    food_data = food_res.json()["data"]
    assert food_data["total"] == 2
    assert len(food_data["items"]) == 2

    # 2. Filter by type (credit)
    credit_res = client.get("/api/v1/transactions?type=credit", headers=headers)
    assert credit_res.status_code == 200
    credit_data = credit_res.json()["data"]
    assert credit_data["total"] == 2

    # 3. Pagination
    page_res = client.get("/api/v1/transactions?page=1&pageSize=2", headers=headers)
    assert page_res.status_code == 200
    page_data = page_res.json()["data"]
    assert len(page_data["items"]) == 2
    assert page_data["total"] == 5
    assert page_data["totalPages"] == 3


def test_transaction_cross_user_isolation(client: TestClient, db_session: AsyncSession):
    token_a = register_and_get_token(client, "tx_owner_a@example.com", "Owner A")
    token_b = register_and_get_token(client, "tx_attacker_b@example.com", "Attacker B")

    # User A creates transaction
    tx_res = client.post(
        "/api/v1/transactions",
        json={"title": "Secret A Transaction", "category": "Private", "amount": "9999", "type": "debit"},
        headers=auth_headers(token_a),
    )
    assert tx_res.status_code == 200
    tx_id = tx_res.json()["data"]["id"]

    # User B attempts GET User A transaction -> 404
    b_get = client.get(f"/api/v1/transactions/{tx_id}", headers=auth_headers(token_b))
    assert b_get.status_code == 404

    # User B attempts PATCH User A transaction -> 404
    b_patch = client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"amount": "1.00"},
        headers=auth_headers(token_b),
    )
    assert b_patch.status_code == 404

    # User B attempts DELETE User A transaction -> 404
    b_del = client.delete(f"/api/v1/transactions/{tx_id}", headers=auth_headers(token_b))
    assert b_del.status_code == 404

    # User B's transaction list should be empty
    b_list = client.get("/api/v1/transactions", headers=auth_headers(token_b))
    assert b_list.status_code == 200
    assert b_list.json()["data"]["total"] == 0


# ---------------------------------------------------------------------------
# 2. GOALS TESTS
# ---------------------------------------------------------------------------

def test_goals_crud_and_progress_calculation(client: TestClient, db_session: AsyncSession):
    token = register_and_get_token(client, "goal_user@example.com", "Goal User")
    headers = auth_headers(token)

    # 1. Create Goal
    create_payload = {
        "name": "Emergency Fund",
        "target": "100000.00",
        "current": "25000.00",
        "color": "#10B981",
        "category": "Savings",
        "status": "in_progress",
    }
    create_res = client.post("/api/v1/goals", json=create_payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    goal_data = create_res.json()["data"]
    goal_id = goal_data["id"]

    assert goal_data["name"] == "Emergency Fund"
    assert Decimal(str(goal_data["target"])) == Decimal("100000.00")
    assert Decimal(str(goal_data["current"])) == Decimal("25000.00")
    assert goal_data["progress"] == 0.25

    # 2. Update Goal Progress
    patch_res = client.patch(
        f"/api/v1/goals/{goal_id}",
        json={"current": "50000.00"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()["data"]
    assert updated_data["progress"] == 0.5

    # 3. List Goals
    list_res = client.get("/api/v1/goals", headers=headers)
    assert list_res.status_code == 200
    goals = list_res.json()["data"]
    assert len(goals) == 1
    assert goals[0]["id"] == goal_id

    # 4. Delete Goal
    del_res = client.delete(f"/api/v1/goals/{goal_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted"] is True


def test_goal_cross_user_isolation(client: TestClient, db_session: AsyncSession):
    token_a = register_and_get_token(client, "goal_user_a@example.com", "Goal A")
    token_b = register_and_get_token(client, "goal_user_b@example.com", "Goal B")

    # User A creates goal
    res = client.post(
        "/api/v1/goals",
        json={"name": "Goal Secret A", "target": "50000.00", "current": "10000.00"},
        headers=auth_headers(token_a),
    )
    goal_id = res.json()["data"]["id"]

    # User B attempts operations
    b_get = client.get(f"/api/v1/goals/{goal_id}", headers=auth_headers(token_b))
    assert b_get.status_code == 404

    b_patch = client.patch(
        f"/api/v1/goals/{goal_id}",
        json={"name": "Hacked"},
        headers=auth_headers(token_b),
    )
    assert b_patch.status_code == 404

    b_del = client.delete(f"/api/v1/goals/{goal_id}", headers=auth_headers(token_b))
    assert b_del.status_code == 404


# ---------------------------------------------------------------------------
# 3. DASHBOARD TESTS
# ---------------------------------------------------------------------------

def test_dashboard_empty_state_and_aggregation(client: TestClient, db_session: AsyncSession):
    token = register_and_get_token(client, "dashboard_user@example.com", "Dashboard User")
    headers = auth_headers(token)

    # 1. Empty State
    dash_empty = client.get("/api/v1/dashboard", headers=headers)
    assert dash_empty.status_code == 200
    data = dash_empty.json()["data"]
    assert Decimal(str(data["netWorth"])) == Decimal("0")
    assert Decimal(str(data["monthlyIncome"])) == Decimal("0")
    assert Decimal(str(data["monthlyExpenses"])) == Decimal("0")
    assert data["transactions"] == []
    assert len(data["insights"]) >= 1

    # 2. Add Transactions
    client.post(
        "/api/v1/transactions",
        json={"title": "Monthly Salary", "category": "Salary", "amount": "10000.00", "type": "credit"},
        headers=headers,
    )
    client.post(
        "/api/v1/transactions",
        json={"title": "Rent Payment", "category": "Housing", "amount": "3000.00", "type": "debit"},
        headers=headers,
    )

    # 3. Verify Dashboard Computed Metrics
    dash_res = client.get("/api/v1/dashboard", headers=headers)
    assert dash_res.status_code == 200
    dash_data = dash_res.json()["data"]

    assert Decimal(str(dash_data["netWorth"])) == Decimal("7000.00")
    assert Decimal(str(dash_data["monthlyIncome"])) == Decimal("10000.00")
    assert Decimal(str(dash_data["monthlyExpenses"])) == Decimal("3000.00")
    assert Decimal(str(dash_data["savings"])) == Decimal("7000.00")
    assert dash_data["summary"]["savingsRate"] == 70.0
    assert len(dash_data["transactions"]) == 2
    assert len(dash_data["spending"]) == 1
    assert dash_data["spending"][0]["category"] == "Housing"


# ---------------------------------------------------------------------------
# 4. ANALYTICS TESTS
# ---------------------------------------------------------------------------

def test_analytics_summary_and_timeframe(client: TestClient, db_session: AsyncSession):
    token = register_and_get_token(client, "analytics_user@example.com", "Analytics User")
    headers = auth_headers(token)

    # 1. Empty Analytics
    empty_res = client.get("/api/v1/analytics?timeframe=6m", headers=headers)
    assert empty_res.status_code == 200
    empty_data = empty_res.json()["data"]
    assert empty_data["timeframe"] == "6m"
    assert Decimal(str(empty_data["totalIncome"])) == Decimal("0")
    assert Decimal(str(empty_data["totalExpenses"])) == Decimal("0")

    # 2. Add transactions
    client.post(
        "/api/v1/transactions",
        json={"title": "Salary", "category": "Income", "amount": "8000.00", "type": "credit"},
        headers=headers,
    )
    client.post(
        "/api/v1/transactions",
        json={"title": "Dining Out", "category": "Food", "amount": "1200.00", "type": "debit"},
        headers=headers,
    )
    client.post(
        "/api/v1/transactions",
        json={"title": "Gadget", "category": "Electronics", "amount": "800.00", "type": "debit"},
        headers=headers,
    )

    # 3. Check Analytics
    res = client.get("/api/v1/analytics?timeframe=1m", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert Decimal(str(data["totalIncome"])) == Decimal("8000.00")
    assert Decimal(str(data["totalExpenses"])) == Decimal("2000.00")
    assert Decimal(str(data["netSavings"])) == Decimal("6000.00")
    assert data["savingsRate"] == 75.0
    assert len(data["categoryBreakdown"]) == 2
    assert len(data["topExpenses"]) == 2


# ---------------------------------------------------------------------------
# 5. NOTIFICATIONS TESTS
# ---------------------------------------------------------------------------

def test_notifications_lifecycle_and_user_isolation(client: TestClient, db_session: AsyncSession):
    token_a = register_and_get_token(client, "notif_user_a@example.com", "Notif A")
    token_b = register_and_get_token(client, "notif_user_b@example.com", "Notif B")

    headers_a = auth_headers(token_a)
    headers_b = auth_headers(token_b)

    # Fetch initial notifications for user A (empty list)
    list_a = client.get("/api/v1/notifications", headers=headers_a)
    assert list_a.status_code == 200
    assert list_a.json()["data"] == []

    # Mark all as read when empty
    read_all = client.post("/api/v1/notifications/read-all", headers=headers_a)
    assert read_all.status_code == 200

    # Clear all when empty
    clear_all = client.post("/api/v1/notifications/clear-all", headers=headers_a)
    assert clear_all.status_code == 200


# ---------------------------------------------------------------------------
# 6. SETTINGS & PROFILE TESTS
# ---------------------------------------------------------------------------

def test_settings_and_profile_management(client: TestClient, db_session: AsyncSession):
    token = register_and_get_token(client, "settings_user@example.com", "Settings User")
    headers = auth_headers(token)

    # 1. Get initial settings (auto-generates defaults)
    get_res = client.get("/api/v1/settings", headers=headers)
    assert get_res.status_code == 200
    settings_data = get_res.json()["data"]
    assert settings_data["profile"]["name"] == "Settings User"
    assert settings_data["profile"]["email"] == "settings_user@example.com"
    assert settings_data["preferences"]["currency"] == "INR"
    assert settings_data["preferences"]["theme"] == "dark"

    # 2. Update Profile
    prof_res = client.post(
        "/api/v1/settings/profile",
        json={"name": "Updated Name", "phone": "+91 9876543210", "bio": "Investor & Builder"},
        headers=headers,
    )
    assert prof_res.status_code == 200
    prof_data = prof_res.json()["data"]
    assert prof_data["name"] == "Updated Name"
    assert prof_data["phone"] == "+91 9876543210"
    assert prof_data["bio"] == "Investor & Builder"

    # 3. Update Preferences
    pref_res = client.post(
        "/api/v1/settings/preferences",
        json={"currency": "USD", "theme": "light", "weeklyDigest": False},
        headers=headers,
    )
    assert pref_res.status_code == 200
    pref_data = pref_res.json()["data"]
    assert pref_data["currency"] == "USD"
    assert pref_data["theme"] == "light"
    assert pref_data["weeklyDigest"] is False

    # 4. Verify combined settings reflection
    final_settings = client.get("/api/v1/settings", headers=headers)
    assert final_settings.status_code == 200
    final_data = final_settings.json()["data"]
    assert final_data["profile"]["name"] == "Updated Name"
    assert final_data["preferences"]["currency"] == "USD"
