"""Offline service/HTTP tests. No real DB connection or embedding request."""
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from fastapi.testclient import TestClient
import pytest

from reposcope.api import repos
from reposcope.contracts.api import SearchResponse
from reposcope.main import app
from reposcope.retrieval import search_service as service
from reposcope.retrieval.gemini_embeddings import (
    INDEX_VERSION, EmbeddingAuthenticationError, EmbeddingConfigurationError,
    EmbeddingQuotaError, EmbeddingTransportError, GeminiEmbeddingError,
)
from reposcope.retrieval.vector import EmbeddingIndexMismatchError


@pytest.fixture
def environment(monkeypatch):
    session = Mock()
    session.get.return_value = SimpleNamespace(id=33)
    session.scalar.return_value = SimpleNamespace(id=9, status="ready", index_version=INDEX_VERSION)
    symbol = SimpleNamespace(id=101, name="run", qualname="Example.run")
    session.execute.return_value.all.return_value = [(symbol, "sample/core.py")]
    for module, name in ((service.pipeline, "search_chunks_hybrid"),
                         (service, "search_chunks_by_lexical"), (service, "search_chunks_by_vector")):
        monkeypatch.setattr(module, name, Mock(side_effect=AssertionError("Unexpected real retriever")))
    return session


def hit(**extra):
    return SimpleNamespace(symbol_id=101, repo_id=33, text="def run(): return 1", score=0.04, **extra)


@pytest.mark.parametrize("mode", ["hybrid", "lexical", "vector"])
def test_dispatches_mode_and_preserves_response_metadata(environment, mode):
    session = environment
    retriever = {"hybrid": service.pipeline.search_chunks_hybrid,
                 "lexical": service.search_chunks_by_lexical,
                 "vector": service.search_chunks_by_vector}[mode]
    retriever.side_effect = None
    retriever.return_value = [hit()]
    response = service.run_repository_search(session, repo_id=33, query=" find run ", mode=mode)
    assert response.query == "find run" and len(response.hits) == 1
    result = response.hits[0]
    assert result.symbol_id == 101 and result.name == "Example.run"
    assert result.file_path == "sample/core.py" and "def run()" in result.snippet
    assert result.score == pytest.approx(1 / 61 if mode == "vector" else 0.04)
    retriever.assert_called_once()
    assert retriever.call_args.kwargs["query"] == "find run"
    if mode == "hybrid":
        assert retriever.call_args.kwargs["candidate_limit"] == 30
    session.commit.assert_not_called()


def test_missing_repository_fails_before_retrieval(environment):
    environment.get.return_value = None
    with pytest.raises(service.SearchNotFoundError):
        service.run_repository_search(environment, repo_id=33, query="query")
    environment.scalar.assert_not_called()


@pytest.mark.parametrize("snapshot", [None, SimpleNamespace(status="pending"), SimpleNamespace(status="failed")])
def test_unready_snapshot_fails_before_retrieval(environment, snapshot):
    environment.scalar.return_value = snapshot
    with pytest.raises(service.SearchNotReadyError):
        service.run_repository_search(environment, repo_id=33, query="query")


@pytest.mark.parametrize("mode", ["hybrid", "vector"])
def test_old_bge_index_rejected_before_semantic_retrieval(environment, mode):
    environment.scalar.return_value.index_version = "python-symbols-bge-small-v1"
    with pytest.raises(EmbeddingIndexMismatchError):
        service.run_repository_search(environment, repo_id=33, query="query", mode=mode)
    environment.execute.assert_not_called()


def test_lexical_mode_can_read_old_index_without_embeddings(environment):
    environment.scalar.return_value.index_version = "python-symbols-bge-small-v1"
    service.search_chunks_by_lexical.side_effect = None
    service.search_chunks_by_lexical.return_value = [hit()]
    response = service.run_repository_search(environment, repo_id=33, query="run", mode="lexical")
    assert response.hits[0].symbol_id == 101
    service.search_chunks_by_vector.assert_not_called()
    service.pipeline.search_chunks_hybrid.assert_not_called()


def test_empty_results_skip_metadata_lookup(environment):
    service.pipeline.search_chunks_hybrid.side_effect = None
    service.pipeline.search_chunks_hybrid.return_value = []
    assert service.run_repository_search(environment, repo_id=33, query="query").hits == []
    environment.execute.assert_not_called()


def test_metadata_mismatch_does_not_silently_drop_results(environment):
    service.pipeline.search_chunks_hybrid.side_effect = None
    service.pipeline.search_chunks_hybrid.return_value = [hit()]
    environment.execute.return_value.all.return_value = []
    with pytest.raises(service.SearchResultError):
        service.run_repository_search(environment, repo_id=33, query="query")


def test_cross_repository_result_is_rejected(environment):
    service.pipeline.search_chunks_hybrid.side_effect = None
    bad = hit()
    bad.repo_id = 999
    service.pipeline.search_chunks_hybrid.return_value = [bad]
    with pytest.raises(service.SearchResultError):
        service.run_repository_search(environment, repo_id=33, query="query")
    environment.execute.assert_not_called()


def test_metadata_query_is_repository_and_snapshot_scoped(environment):
    service.pipeline.search_chunks_hybrid.side_effect = None
    service.pipeline.search_chunks_hybrid.return_value = [hit()]
    service.run_repository_search(environment, repo_id=33, query="query")
    statement = environment.execute.call_args.args[0]
    compiled = statement.compile()
    assert "files.repository_id =" in str(compiled)
    assert "files.snapshot_id =" in str(compiled)
    assert 33 in compiled.params.values() and 9 in compiled.params.values()


@pytest.fixture
def http(monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    monkeypatch.setattr(repos, "SessionLocal", Mock(return_value=session))
    search = Mock(return_value=SearchResponse(query="query", hits=[]))
    monkeypatch.setattr(repos, "run_repository_search", search)
    with TestClient(app) as client:
        yield client, search, session


@pytest.mark.parametrize("mode", ["hybrid", "lexical", "vector"])
def test_http_route_passes_mode_to_service(http, mode):
    client, search, session = http
    response = client.post("/api/repos/33/search", json={"q": "query", "mode": mode})
    assert response.status_code == 200, response.text
    SearchResponse.model_validate(response.json())
    search.assert_called_once_with(session, repo_id=33, query="query", mode=mode, limit=10)


@pytest.mark.parametrize("error,status", [
    (service.SearchNotFoundError("missing"), 404),
    (service.SearchNotReadyError("not ready"), 409),
    (EmbeddingIndexMismatchError("incompatible"), 409),
    (EmbeddingQuotaError("sensitive-provider-detail"), 503),
    (EmbeddingTransportError("sensitive-provider-detail"), 503),
    (EmbeddingAuthenticationError("sensitive-provider-detail"), 503),
    (EmbeddingConfigurationError("sensitive-provider-detail"), 503),
    (GeminiEmbeddingError("sensitive-provider-detail"), 502),
    (service.SearchResultError("sensitive-provider-detail"), 500),
])
def test_http_error_statuses_are_explicit_and_sanitized(http, error, status):
    client, search, session = http
    search.side_effect = error
    response = client.post("/api/repos/33/search", json={"q": "query", "mode": "hybrid"})
    assert response.status_code == status, response.text
    assert response.json()["error"]["status"] == status
    assert "sensitive-provider-detail" not in response.text


def test_invalid_mode_is_rejected_before_service(http):
    client, search, session = http
    assert client.post("/api/repos/33/search", json={"q": "query", "mode": "invalid"}).status_code == 422
    search.assert_not_called()
