import re

import pytest
from fastapi.testclient import TestClient

from reposcope.contracts.api import (
    AskResponse, ErrorResponse, FeedbackResponse, NeighborsResponse,
    RegisterRepoResponse, RepositoryResponse, SearchResponse,
    SymbolDetailResponse, SymbolListResponse,
)
from reposcope.main import app

client = TestClient(app)


def test_register_repo():
    r = client.post("/api/repos", json={"url": "https://github.com/fastapi/fastapi"})
    assert r.status_code == 202
    response = RegisterRepoResponse.model_validate(r.json())
    assert response.status == "pending"
    assert "no ingestion job was enqueued" in response.message


def test_get_repo():
    r = client.get("/api/repos/1")
    assert r.status_code == 200
    response = RepositoryResponse.model_validate(r.json())
    assert response.id == 1
    assert response.name == "nishtha911/RepoScope"
    assert str(response.url) == "https://github.com/nishtha911/RepoScope"
    assert response.head_sha == "d631c3f98581ab3ebdb0c8daa28cc8bf122f749a"
    assert response.snapshot_id == 1


def test_search_repo():
    r = client.post("/api/repos/1/search", json={"q": "resolver"})
    assert r.status_code == 200
    response = SearchResponse.model_validate(r.json())
    assert response.query == "resolver" and response.hits


def test_ask_repo():
    question = "How does resolution work?"
    r = client.post("/api/repos/1/ask", json={"question": question})
    assert r.status_code == 200
    response = AskResponse.model_validate(r.json())
    assert question in response.answer
    assert response.evidence
    cited = set(re.findall(r"\[(E[1-9][0-9]*)\]", response.answer))
    supplied = {item.evidence_id for item in response.evidence}
    assert cited and cited <= supplied
    assert "E2" not in cited


def test_symbol_list_is_tested_separately_from_ask():
    r = client.get("/api/repos/1/symbols")
    assert r.status_code == 200
    response = SymbolListResponse.model_validate(r.json())
    assert response.symbols[0].file_id > 0


@pytest.mark.parametrize("path,model", [
    ("/api/symbols/101", SymbolDetailResponse),
    ("/api/symbols/101/neighbors", NeighborsResponse),
])
def test_correct_symbol_paths(path, model):
    r = client.get(path)
    assert r.status_code == 200
    model.model_validate(r.json())


def test_correct_feedback_path():
    r = client.post("/api/recs/1/feedback", json={"action": "accepted"})
    assert r.status_code == 200
    response = FeedbackResponse.model_validate(r.json())
    assert response.id == 1 and response.action == "accepted"


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/repos/1/ask", {"question": " "}),
    ("POST", "/api/repos/1/search", {"q": "run", "mode": "invalid"}),
    ("POST", "/api/recs/1/feedback", {"action": "invalid"}),
    ("GET", "/api/repos/1/symbols?limit=0", None),
    ("GET", "/api/symbols/101/neighbors?dir=both", None),
])
def test_invalid_inputs_have_validated_error_envelopes(method, path, payload):
    r = client.request(method, path, **({"json": payload} if payload is not None else {}))
    assert r.status_code == 422
    response = ErrorResponse.model_validate(r.json())
    assert response.error.code == "VALIDATION_ERROR"
    assert response.error.status == 422


def test_symbol_impact_is_planned_not_a_fake_analysis():
    assert "/api/symbols/{symbol_id}/impact" not in app.openapi()["paths"]
    r = client.get("/api/symbols/101/impact?depth=3")
    assert r.status_code == 404
    response = ErrorResponse.model_validate(r.json())
    assert response.error.code == "NOT_FOUND"
