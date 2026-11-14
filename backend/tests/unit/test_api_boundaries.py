"""HTTP-contract unit tests with isolated repository-session fixtures.

PostgreSQL SQL execution, transaction atomicity, and query result correctness
are integration-test responsibilities, not claims made by these mocked tests.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from reposcope.api import repos
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

@pytest.fixture(autouse=True)
def isolated_repository_session(monkeypatch):
    """Only this module: replace the route's DB boundary, not route functions.

    These are HTTP-contract unit tests. Returned rows are fixtures, not proof
    that the SQL executes correctly. PostgreSQL behavior needs integration tests.
    Unexpected DB calls fail immediately instead of reaching the configured DB.
    """
    session = MagicMock(name="isolated_repository_session")
    for method in ("get", "scalar", "scalars", "execute", "add", "flush"):
        getattr(session, method).side_effect = AssertionError(
            f"Unconfigured database operation: {method}")
    session.__enter__.return_value = session
    factory = MagicMock(name="isolated_session_factory", return_value=session)
    factory.begin.return_value = session
    monkeypatch.setattr(repos, "SessionLocal", factory)
    return session


def fixture_symbol():
    return SimpleNamespace(id=101, file_id=11, name="resolver",
        qualname="resolver", kind="function", start_line=10, end_line=20)


def rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    result.first.return_value = rows[0] if rows else None
    return result



@pytest.mark.parametrize("method,path,payload,status,model", [
    ("GET", "/api/health", None, 200, HealthResponse),
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


def test_symbol_filter_and_neighbors_filter_arguments(isolated_repository_session):
    session = isolated_repository_session
    edge = SimpleNamespace(kind="CALLS", confidence=0.9)
    session.execute.side_effect = [rows_result([]), rows_result([]),
                                  rows_result([]), rows_result([(edge, fixture_symbol())])]
    assert client.get("/api/repos/1/symbols?kind=class").json() == {"symbols": []}
    assert client.get("/api/repos/1/symbols?q=doesnotmatch").json() == {"symbols": []}
    assert client.get("/api/symbols/101/neighbors?types=INHERITS").json() == {"neighbors": []}
    response = client.get("/api/symbols/101/neighbors?dir=in&types=CALLS")
    assert response.status_code == 200
    assert response.json()["neighbors"][0]["direction"] == "in"
    statements = [call.args[0] for call in session.execute.call_args_list]
    params = [statement.compile().params for statement in statements]
    assert "class" in params[0].values()
    assert "%doesnotmatch%" in params[1].values()
    assert ["INHERITS"] in params[2].values()
    assert ["CALLS"] in params[3].values()


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


@pytest.mark.parametrize("method,path,payload,model", [
    ("GET", "/api/repos/1", None, RepositoryResponse),
    ("GET", "/api/repos/1/symbols", None, SymbolListResponse),
    ("GET", "/api/symbols/101", None, SymbolDetailResponse),
    ("GET", "/api/symbols/101/neighbors", None, NeighborsResponse),
    ("POST", "/api/repos/1/search", {"q": "resolver", "mode": "hybrid"}, SearchResponse),
])
def test_database_backed_response_contracts(method, path, payload, model,
                                          isolated_repository_session):
    session = isolated_repository_session
    symbol = fixture_symbol()
    if path == "/api/repos/1":
        session.get.side_effect = None
        session.get.return_value = RepositoryORM(id=1, full_name="owner/repo",
                                                remote_url="https://github.com/owner/repo")
        session.scalar.side_effect = [SimpleNamespace(id=7, status="ready", commit_sha="a" * 40), 1, 1]
    else:
        row = ((SimpleNamespace(kind="CALLS", confidence=0.9), symbol)
               if path.endswith("/neighbors") else (symbol, "backend/resolver.py"))
        session.execute.side_effect = None
        session.execute.return_value = rows_result([row])
    response = client.request(method, path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == 200, response.text
    body = response.json()
    model.model_validate(body)
    if path == "/api/repos/1":
        assert body["id"] == 1 and body["snapshot_id"] == 7
        assert body["file_count"] == 1 and body["symbol_count"] == 1
    elif path.endswith("/symbols"):
        assert body["symbols"][0]["id"] == 101
        assert body["symbols"][0]["file_path"] == "backend/resolver.py"
    elif path.endswith("/neighbors"):
        assert body["neighbors"][0]["relationship_type"] == "CALLS"
        assert body["neighbors"][0]["direction"] == "out"
    elif path.endswith("/search"):
        assert body["query"] == payload["q"]
        assert body["hits"][0]["symbol_id"] == 101
    else:
        assert body["id"] == 101 and body["start_line"] == 10


def test_registration_response_contract_and_enqueue_arguments(isolated_repository_session, monkeypatch):
    session = isolated_repository_session
    session.scalars.side_effect = None
    session.scalars.return_value.all.return_value = []
    session.scalar.side_effect = [None, 0]  # No ready snapshot; no existing files.
    added = []
    session.add.side_effect = added.append
    def flush():
        assert len(added) == 1
        added[0].id = 42
    session.flush.side_effect = flush
    executed = []
    def execute(statement, params=None):
        sql = str(statement)
        executed.append((sql, params))
        result = MagicMock()
        if sql.startswith("SET LOCAL") or "pg_advisory_xact_lock" in sql:
            return result
        if "status IN ('queued', 'running')" in sql:
            result.mappings.return_value.one_or_none.return_value = None
            return result
        if "SELECT status FROM ingestion_jobs WHERE id=:id" in sql:
            assert params == {"id": 70}
            result.scalar_one.return_value = "queued"
            return result
        raise AssertionError(f"Unexpected registration SQL: {sql}")
    session.execute.side_effect = execute
    enqueue = MagicMock(return_value=70)
    monkeypatch.setattr(repos, "enqueue_job", enqueue)
    response = client.post("/api/repos", json={"url": "https://github.com/owner/repo.git"})
    assert response.status_code == 202, response.text
    body = response.json()
    RegisterRepoResponse.model_validate(body)
    assert body["repo_id"] == 42 and body["status"] == "pending"
    assert "70" in body["message"]
    assert added[0].remote_url == "https://github.com/owner/repo"
    assert added[0].full_name == "owner/repo"
    enqueue.assert_called_once_with(session, 42, f"register:{repos.INDEX_VERSION}", max_attempts=3)
    assert any("pg_advisory_xact_lock" in sql for sql, _ in executed)
    assert session.__exit__.call_count == 1
    assert session.__exit__.call_args.args == (None, None, None)


@pytest.mark.parametrize("path,payload,message", [
    ("/api/repos/1/ask", {"question": "How does resolution work?"}, "Repository Q&A is unavailable"),
    ("/api/repos/1/pr-impact", {"pr_url": "https://github.com/owner/repo/pull/1"}, "PR URL analysis is unavailable"),
])
def test_unconfigured_features_return_documented_error(path, payload, message,
                                                      isolated_repository_session):
    response = client.post(path, json=payload)
    assert response.status_code == 501, response.text
    error = response.json()["error"]
    assert error["code"] == "NOT_IMPLEMENTED"
    assert error["status"] == 501
    assert message in error["message"]
    isolated_repository_session.execute.assert_not_called()
    isolated_repository_session.get.assert_not_called()


@pytest.mark.parametrize("path", ["/api/repos/999999", "/api/symbols/999999"])
def test_missing_record_returns_404_without_real_database(path, isolated_repository_session):
    session = isolated_repository_session
    if path.startswith("/api/repos/"):
        session.get.side_effect = None
        session.get.return_value = None
    else:
        session.execute.side_effect = None
        session.execute.return_value = rows_result([])
    response = client.get(path)
    assert response.status_code == 404, response.text
    assert "was not found" in response.json()["error"]["message"]
