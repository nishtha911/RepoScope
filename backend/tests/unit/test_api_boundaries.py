import pytest
from fastapi import FastAPI
from fastapi.exceptions import ResponseValidationError
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from reposcope.contracts.adapters import repository_to_response
from reposcope.contracts.api import (
    AskResponse, FeedbackResponse, HealthResponse, NeighborsResponse,
    RecommendationsResponse, RegisterRepoResponse, RepositoryResponse,
    SearchResponse, SymbolDetailResponse, SymbolListResponse,
)
from reposcope.contracts.pr_report import PRImpactReport
from reposcope.main import app
from reposcope.models.repository import Repository as RepositoryORM

client = TestClient(app)


@pytest.mark.parametrize("method,path,payload,status,model", [
    ("GET", "/api/health", None, 200, HealthResponse),
    ("POST", "/api/repos", {"url": "https://github.com/owner/repo.git"}, 202, RegisterRepoResponse),
    ("GET", "/api/repos/1", None, 200, RepositoryResponse),
    ("GET", "/api/repos/1/symbols", None, 200, SymbolListResponse),
    ("GET", "/api/symbols/101", None, 200, SymbolDetailResponse),
    ("GET", "/api/symbols/101/neighbors", None, 200, NeighborsResponse),
    ("POST", "/api/repos/1/search", {"q": "resolver", "mode": "hybrid"}, 200, SearchResponse),
    ("POST", "/api/repos/1/ask", {"question": "How does resolution work?"}, 200, AskResponse),
    ("POST", "/api/repos/1/pr-impact", {"pr_url": "https://github.com/owner/repo/pull/1"}, 200, PRImpactReport),
    ("GET", "/api/repos/1/recommendations", None, 200, RecommendationsResponse),
    ("POST", "/api/recs/1/feedback", {"action": "accepted"}, 200, FeedbackResponse),
])
def test_response_contracts(method, path, payload, status, model):
    response = client.request(method, path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == status, response.text
    model.model_validate(response.json())


def test_all_api_routes_have_response_models():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            assert route.response_model is not None, route.path


@pytest.mark.parametrize("path", [
    "/api/repos/1/symbols?limit=0", "/api/repos/1/symbols?limit=101",
    "/api/repos/1/symbols?kind=UNKNOWN", "/api/repos/1/symbols?kind=METHOD",
    "/api/repos/1/recommendations?k=0", "/api/repos/1/recommendations?k=101",
    "/api/symbols/1/neighbors?dir=both", "/api/symbols/1/neighbors?types=TESTS",
    "/api/symbols/1/neighbors?types=CALLS,UNKNOWN", "/api/repos/0", "/api/symbols/0",
])
def test_invalid_queries_use_error_envelope(path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path,payload", [
    ("/api/repos", {"url": "https://example.com/a/b"}),
    ("/api/repos", {"url": "https://github.com/a/b", "extra": True}),
    ("/api/repos/1/search", {"q": " "}),
    ("/api/repos/1/search", {"q": "x", "mode": "other"}),
    ("/api/repos/1/ask", {"question": " "}),
    ("/api/repos/1/pr-impact", {"pr_url": "https://github.com/a/b"}),
    ("/api/recs/1/feedback", {"action": "other"}),
])
def test_invalid_requests_use_error_envelope(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_mock_symbol_filter_and_neighbors_filter():
    assert client.get("/api/repos/1/symbols?kind=class").json() == {"symbols": []}
    assert client.get("/api/repos/1/symbols?q=doesnotmatch").json() == {"symbols": []}
    assert client.get("/api/symbols/101/neighbors?types=INHERITS").json() == {"neighbors": []}
    result = client.get("/api/symbols/101/neighbors?dir=in&types=CALLS").json()
    assert result["neighbors"][0]["direction"] == "in"


def test_real_orm_adapter_without_database_connection():
    row = RepositoryORM(id=1, full_name="owner/repo", remote_url="https://github.com/owner/repo")
    response = repository_to_response(
        row, default_branch="main", status="pending", snapshot_id=None,
        head_sha=None, file_count=None, symbol_count=None,
    )
    assert response.name == "owner/repo" and response.id == 1


def test_fastapi_rejects_invalid_output_at_response_boundary():
    probe = FastAPI()

    @probe.get("/probe", response_model=SymbolListResponse)
    def invalid_output():
        return {"symbols": [{"id": 1}]}

    with pytest.raises(ResponseValidationError):
        TestClient(probe).get("/probe")


def test_openapi_uses_documented_symbol_and_feedback_paths():
    paths = app.openapi()["paths"]
    assert "/api/symbols/{symbol_id}" in paths
    assert "/api/recs/{rec_id}/feedback" in paths
    assert "/api/repos/symbols/{symbol_id}" not in paths
    assert "/api/repos/recs/{rec_id}/feedback" not in paths
