"""Comprehensive test suite for Reports domain API."""

import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


def register_and_login(client: TestClient, email: str, name: str = "Test User") -> dict:
    """Helper to register, login, and obtain authorization headers."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePassword123!", "name": name},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert res.status_code == 200
    token = res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_reports_require_authentication(client: TestClient):
    """Verify that reports endpoints reject unauthenticated requests with 401."""
    # List reports
    res = client.get("/api/v1/reports")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Generate report
    res = client.post("/api/v1/reports/generate", json={"type": "summary", "period": "October 2026"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Get single report
    res = client.get("/api/v1/reports/nonexistent_id")
    assert res.status_code == 401

    # Download report CSV
    res = client.get("/api/v1/reports/nonexistent_id/download")
    assert res.status_code == 401


def test_reports_empty_financial_history(client: TestClient, db_session: AsyncSession):
    """Verify report behavior when user has zero transaction records."""
    headers = register_and_login(client, "empty_rep_user@example.com", "Empty Tester")

    # 1. Initial list is empty
    list_res = client.get("/api/v1/reports", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()["data"]
    assert data == []

    # 2. Generate report on empty history
    gen_res = client.post(
        "/api/v1/reports/generate",
        json={"type": "summary", "period": "October 2026"},
        headers=headers,
    )
    assert gen_res.status_code == 201
    rep = gen_res.json()["data"]
    assert rep["type"] == "summary"
    assert rep["status"] == "Ready"
    assert "downloadUrl" in rep or "download_url" in rep
    assert rep["period"] == "October 2026"

    # 3. Download CSV for empty dataset
    down_url = rep.get("downloadUrl") or rep.get("download_url")
    down_res = client.get(down_url, headers=headers)
    assert down_res.status_code == 200
    assert "text/csv" in down_res.headers["content-type"]
    assert "No transactions found" in down_res.text


def test_reports_successful_generation_and_calculation(client: TestClient, db_session: AsyncSession):
    """Verify report generation with actual transactions and check financial aggregations."""
    headers = register_and_login(client, "active_rep_user@example.com", "Active Tester")

    # Seed 2 transactions (1 credit, 1 debit)
    client.post(
        "/api/v1/transactions",
        json={"title": "Tech Consulting", "amount": 100000.0, "category": "Consulting", "type": "credit"},
        headers=headers,
    )
    client.post(
        "/api/v1/transactions",
        json={"title": "Office Rent", "amount": 30000.0, "category": "Office", "type": "debit"},
        headers=headers,
    )

    # 1. Generate spending report
    gen_res = client.post(
        "/api/v1/reports/generate",
        json={"type": "spending", "period": "October 2026"},
        headers=headers,
    )
    assert gen_res.status_code == 201
    rep_spending = gen_res.json()["data"]
    assert rep_spending["type"] == "spending"
    assert rep_spending["status"] == "Ready"

    # 2. Generate summary report
    gen_summary = client.post(
        "/api/v1/reports/generate",
        json={"type": "summary", "period": "October 2026"},
        headers=headers,
    )
    assert gen_summary.status_code == 201
    rep_summary = gen_summary.json()["data"]
    assert rep_summary["type"] == "summary"

    # 3. Verify reports list now contains both
    list_res = client.get("/api/v1/reports", headers=headers)
    assert list_res.status_code == 200
    reports = list_res.json()["data"]
    assert len(reports) == 2
    types = [r["type"] for r in reports]
    assert "spending" in types
    assert "summary" in types

    # 4. Download and parse CSV for calculations
    down_url = rep_summary.get("downloadUrl") or rep_summary.get("download_url")
    down_res = client.get(down_url, headers=headers)
    assert down_res.status_code == 200

    csv_reader = csv.reader(io.StringIO(down_res.text))
    rows = list(csv_reader)

    # Assert calculations in CSV
    row_dict = {r[0]: r[1] for r in rows if len(r) == 2}
    assert row_dict.get("Total Income (Credits)") == "100000.00"
    assert row_dict.get("Total Expenses (Debits)") == "30000.00"
    assert row_dict.get("Net Cashflow / Savings") == "70000.00"
    assert row_dict.get("Savings Rate") == "70.0%"
    assert row_dict.get("Total Transactions") == "2"

    # 5. Generate and verify Tax report CSV contains estimate disclaimer
    tax_gen = client.post(
        "/api/v1/reports/generate",
        json={"type": "tax", "period": "FY 2025-2026"},
        headers=headers,
    )
    assert tax_gen.status_code == 201
    tax_down = client.get(tax_gen.json()["data"]["downloadUrl"], headers=headers)
    assert tax_down.status_code == 200
    assert "Preliminary Tax Year Cashflow Projection (Estimate Only)" in tax_down.text
    assert "All tax figures are informational ledger classifications, not formal tax returns." in tax_down.text

    # 6. Generate and verify Portfolio report CSV contains holdings section
    port_gen = client.post(
        "/api/v1/reports/generate",
        json={"type": "portfolio", "period": "Q3 2026"},
        headers=headers,
    )
    assert port_gen.status_code == 201
    port_down = client.get(port_gen.json()["data"]["downloadUrl"], headers=headers)
    assert port_down.status_code == 200
    assert "Investment Portfolio Performance & Holdings" in port_down.text


def test_reports_date_range_validation(client: TestClient, db_session: AsyncSession):
    """Verify validation of valid and invalid date ranges."""
    headers = register_and_login(client, "date_rep_user@example.com", "Date Tester")

    # 1. Valid date range
    valid_res = client.post(
        "/api/v1/reports/generate",
        json={
            "type": "summary",
            "period": "Q1 2026",
            "startDate": "2026-01-01T00:00:00Z",
            "endDate": "2026-03-31T23:59:59Z",
        },
        headers=headers,
    )
    assert valid_res.status_code == 201

    # 2. Invalid date range (start after end)
    invalid_res = client.post(
        "/api/v1/reports/generate",
        json={
            "type": "summary",
            "period": "Invalid Range",
            "startDate": "2026-12-31T00:00:00Z",
            "endDate": "2026-01-01T00:00:00Z",
        },
        headers=headers,
    )
    assert invalid_res.status_code == 422


def test_reports_invalid_report_type(client: TestClient, db_session: AsyncSession):
    """Verify that unsupported report types are rejected with 422."""
    headers = register_and_login(client, "invalid_type_user@example.com", "Invalid Tester")

    res = client.post(
        "/api/v1/reports/generate",
        json={"type": "crypto_derivatives", "period": "October 2026"},
        headers=headers,
    )
    assert res.status_code == 422


def test_reports_cross_user_isolation(client: TestClient, db_session: AsyncSession):
    """Verify that user A's reports are never accessible or leaked to user B."""
    headers_a = register_and_login(client, "rep_user_a@example.com", "User A")
    headers_b = register_and_login(client, "rep_user_b@example.com", "User B")

    # User A creates a report
    gen_a = client.post(
        "/api/v1/reports/generate",
        json={"type": "tax", "period": "FY 2025-2026"},
        headers=headers_a,
    )
    assert gen_a.status_code == 201
    rep_a_id = gen_a.json()["data"]["id"]

    # User B attempts to read User A's report metadata -> 404
    b_get = client.get(f"/api/v1/reports/{rep_a_id}", headers=headers_b)
    assert b_get.status_code == 404

    # User B attempts to download User A's report CSV -> 404
    b_down = client.get(f"/api/v1/reports/{rep_a_id}/download", headers=headers_b)
    assert b_down.status_code == 404

    # User B's list should be empty
    b_list = client.get("/api/v1/reports", headers=headers_b)
    assert b_list.status_code == 200
    assert len(b_list.json()["data"]) == 0
