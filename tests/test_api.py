
from fastapi.testclient import TestClient
from app.main import app

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Recipe Management API!"}

def test_docs_redirect(client: TestClient):
    response = client.get("/docs")
    assert response.status_code == 200
