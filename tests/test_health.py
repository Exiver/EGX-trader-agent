from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_health_check_return_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "egx-advisor"


def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()