from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from reposcope.contracts.adapters import repository_to_response
from reposcope.contracts.api import (
    AskRequest, AskResponse, FeedbackRequest, Neighbor, PRImpactRequest,
    RegisterRepoRequest, RepositoryResponse, SearchRequest,
    SymbolDetailResponse, SymbolListItem,
)
from reposcope.contracts.edge import Edge
from reposcope.contracts.symbol import Symbol


def symbol_data():
    return dict(id=1, file_id=2, name="run", kind="method", start_line=3, end_line=5,
                qualname="Worker.run", file_path="worker.py")


def test_symbol_dtos_extend_without_weakening_domain():
    item = SymbolListItem(**symbol_data())
    assert item.file_id == 2
    detail = SymbolDetailResponse(**symbol_data())
    assert detail.signature is None and detail.docstring is None
    assert detail.cyclomatic_complexity is None
    with pytest.raises(ValidationError):
        Symbol(**symbol_data())


@pytest.mark.parametrize("changes", [
    {"kind": "METHOD"}, {"kind": "not_a_kind"}, {"file_id": 0},
    {"end_line": 2}, {"qualname": " "}, {"file_path": " "}, {"unexpected": 1},
])
def test_invalid_symbol_dto(changes):
    with pytest.raises(ValidationError):
        SymbolListItem(**{**symbol_data(), **changes})


def test_symbol_dto_requires_file_id():
    data = symbol_data()
    del data["file_id"]
    with pytest.raises(ValidationError):
        SymbolListItem(**data)


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_complexity(value):
    with pytest.raises(ValidationError):
        SymbolDetailResponse(**symbol_data(), cyclomatic_complexity=value)


@pytest.mark.parametrize("url", [
    "https://github.com/owner/repo", "https://github.com/owner/repo.git",
    "https://github.com/owner/repo/",
])
def test_registration_urls(url):
    assert RegisterRepoRequest(url=url).url == url


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo", "https://example.com/owner/repo",
    "https://github.com/owner", "https://github.com/owner/repo/pull/1",
    "https://user:pass@github.com/owner/repo", "https://github.com:443/owner/repo",
    "https://github.com/owner/repo?token=abc", "https://github.com/owner/repo#fragment",
    "https://github.com/owner/..", "https://github.com/owner/re po", "git@github.com:owner/repo.git",
])
def test_invalid_registration_urls(url):
    with pytest.raises(ValidationError):
        RegisterRepoRequest(url=url)


@pytest.mark.parametrize("url", [
    "https://github.com/owner/repo", "https://github.com/owner/repo/pull/0",
    "https://github.com/owner/repo/pull/x", "https://example.com/owner/repo/pull/1",
    "https://github.com/owner/repo/pull/1/files",
])
def test_invalid_pr_urls(url):
    with pytest.raises(ValidationError):
        PRImpactRequest(pr_url=url)


def test_valid_pr_url():
    assert PRImpactRequest(pr_url="https://github.com/owner/repo/pull/12").pr_url.endswith("/12")


@pytest.mark.parametrize("model,payload", [
    (SearchRequest, {"q": " "}), (SearchRequest, {"q": "x", "mode": "unknown"}),
    (AskRequest, {"question": " "}), (FeedbackRequest, {"action": "unknown"}),
    (SearchRequest, {"q": "x", "extra": True}),
    (SearchRequest, {"q": "x" * 2001}), (AskRequest, {"question": "x" * 10001}),
])
def test_request_validation(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize("action", ["accepted", "dismissed", "not_useful"])
def test_feedback_actions(action):
    assert FeedbackRequest(action=action).action == action


@pytest.mark.parametrize("mode", ["hybrid", "lexical", "vector"])
def test_search_modes(mode):
    assert SearchRequest(q="run", mode=mode).mode == mode


def test_repository_adapter_maps_fields_without_guessing_metadata():
    row = SimpleNamespace(id=1, full_name="owner/repo", remote_url="https://github.com/owner/repo")
    result = repository_to_response(
        row, default_branch="develop", status="ready", snapshot_id=9, head_sha="a" * 40,
        file_count=15, symbol_count=44,
    )
    data = result.model_dump(mode="json")
    assert data["name"] == row.full_name and data["url"] == row.remote_url
    assert data["default_branch"] == "develop" and data["snapshot_id"] == 9
    assert "full_name" not in data and "remote_url" not in data
    with pytest.raises(TypeError):
        repository_to_response(row)


def test_unknown_counts_stay_null():
    row = SimpleNamespace(id=1, full_name="owner/repo", remote_url="https://github.com/owner/repo")
    result = repository_to_response(
        row, default_branch="main", status="pending", snapshot_id=None,
        head_sha=None, file_count=None, symbol_count=None,
    )
    assert result.file_count is None and result.symbol_count is None


@pytest.mark.parametrize("changes", [
    {"file_count": -1}, {"symbol_count": -1}, {"snapshot_id": 0},
    {"snapshot_id": None}, {"head_sha": None},
])
def test_invalid_repository_response(changes):
    data = dict(id=1, name="owner/repo", url="https://github.com/owner/repo",
                snapshot_id=2, head_sha="a" * 40, file_count=0, symbol_count=0)
    with pytest.raises(ValidationError):
        RepositoryResponse(**{**data, **changes})


@pytest.mark.parametrize("confidence", [None, 0, 0.8, 1])
def test_optional_edge_confidence(confidence):
    edge = Edge(source_symbol_id=1, target_symbol_id=2, kind="CALLS", confidence=confidence)
    assert edge.confidence == confidence


@pytest.mark.parametrize("kind", ["TESTS", "calls", "UNKNOWN"])
def test_invalid_edge_kind(kind):
    with pytest.raises(ValidationError):
        Edge(source_symbol_id=1, target_symbol_id=2, kind=kind)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_neighbor_confidence(confidence):
    with pytest.raises(ValidationError):
        Neighbor(symbol_id=1, name="run", relationship_type="CALLS", direction="out", confidence=confidence)


def test_duplicate_evidence_ids_rejected():
    item = dict(evidence_id="E1", snapshot_id=1, file_id=1, file_path="a.py",
                start_line=1, end_line=1, text="pass")
    with pytest.raises(ValidationError):
        AskResponse(answer="test", evidence=[item, item], gaps=[])
