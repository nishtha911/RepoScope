from fastapi.testclient import TestClient
from reposcope.main import app

client = TestClient(app)


def test_register_repo():
    r = client.post("/api/repos", json={"url": "https://github.com/fastapi/fastapi"})
    assert r.status_code == 202
    assert r.json()["status"] == "pending"


def test_get_repo():
    r = client.get("/api/repos/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_search_repo():
    r = client.post("/api/repos/1/search", json={"q": "resolver"})
    assert r.status_code == 200
    assert len(r.json()["hits"]) > 0


def test_ask_repo():
    r = client.get("/api/repos/1/symbols")
    assert r.status_code == 200
    assert "symbols" in r.json()
