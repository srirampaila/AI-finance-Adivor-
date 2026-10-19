import pytest


@pytest.mark.parametrize(
    "method,endpoint",
    [
        ("GET", "/api/v1/dashboard"),
        ("GET", "/api/v1/transactions"),
        ("GET", "/api/v1/goals"),
        ("GET", "/api/v1/analytics"),
        ("GET", "/api/v1/notifications"),
        ("GET", "/api/v1/settings"),
        ("GET", "/api/v1/investments/portfolios"),
        ("GET", "/api/v1/investments/positions"),
        ("GET", "/api/v1/investments/summary"),
        ("GET", "/api/v1/investments/market"),
        ("GET", "/api/v1/investments/indices"),
        ("GET", "/api/v1/investments/news"),
        ("GET", "/api/v1/investments/sentiment"),
        ("GET", "/api/v1/investments/risk"),
        ("GET", "/api/v1/investments/insights"),
        ("POST", "/api/v1/advisor/chat"),
        ("GET", "/api/v1/advisor/history"),
        ("GET", "/api/v1/reports"),
        ("POST", "/api/v1/reports/generate"),
    ],
)
def test_protected_endpoints_require_auth(client, method, endpoint):
    """Verify that implemented domain endpoints return 401 when unauthenticated."""
    if method == "GET":
        response = client.get(endpoint)
    elif method == "POST":
        response = client.post(endpoint, json={"message": "hello"})
    else:
        response = client.request(method, endpoint)

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_openapi_docs_endpoints(client):
    """Verify that OpenAPI documentation JSON and Swagger UI endpoints are accessible."""
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    openapi_data = openapi_response.json()
    assert openapi_data["info"]["title"] == "AI Finance Advisor"
    assert "/api/v1/health" in openapi_data["paths"]
    assert "/api/v1/transactions" in openapi_data["paths"]
    assert "/api/v1/goals" in openapi_data["paths"]
    assert "/api/v1/dashboard" in openapi_data["paths"]
    assert "/api/v1/analytics" in openapi_data["paths"]
    assert "/api/v1/notifications" in openapi_data["paths"]
    assert "/api/v1/settings" in openapi_data["paths"]
    assert "/api/v1/investments/portfolios" in openapi_data["paths"]
    assert "/api/v1/investments/positions" in openapi_data["paths"]
    assert "/api/v1/investments/summary" in openapi_data["paths"]
    assert "/api/v1/investments/market" in openapi_data["paths"]
    assert "/api/v1/investments/risk" in openapi_data["paths"]
    assert "/api/v1/investments/insights" in openapi_data["paths"]
    assert "/api/v1/advisor/chat" in openapi_data["paths"]
