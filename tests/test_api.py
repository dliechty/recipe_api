
from fastapi.testclient import TestClient
from app.core.config import settings

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Recipe Management API!"}

def test_docs_redirect(client: TestClient):
    response = client.get("/docs")
    assert response.status_code == 200

def test_cors_headers(client: TestClient):
    # Simulate a cross-origin request by setting the Origin header
    headers = {"Origin": "http://localhost:3000"}
    response = client.get("/", headers=headers)
    assert response.status_code == 200
    # The Access-Control-Expose-Headers header should be present and contain X-Total-Count
    assert "access-control-expose-headers" in response.headers
    assert "X-Total-Count" in response.headers["access-control-expose-headers"]


def test_security_headers(client: TestClient):
    """Verify security headers are set on responses."""
    response = client.get("/")
    assert response.status_code == 200

    # Check all security headers are present
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    
    if settings.ENVIRONMENT in ["development", "testing"]:
        expected_csp = (
            "default-src 'self'; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
        )
    else:
        expected_csp = "default-src 'self'"
        
    assert response.headers.get("Content-Security-Policy") == expected_csp
