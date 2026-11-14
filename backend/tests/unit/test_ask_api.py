"""HTTP-only Q&A tests: service is mocked; no DB/provider requests occur."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import pytest

from reposcope.api import repos
from reposcope.contracts.api import AskRequest, AskResponse
from reposcope.contracts.evidence import Evidence
from reposcope.integrations.llm import LLMConfigurationError, LLMError, LLMOutputError, LLMUnavailable
from reposcope.main import app
from reposcope.rag.qa_service import (
    QuestionContextError, QuestionInputError, QuestionNotFoundError, QuestionNotReadyError,
)
from reposcope.rag.validator import CitationValidationError
from reposcope.retrieval.gemini_embeddings import (
    EmbeddingAuthenticationError, EmbeddingConfigurationError, EmbeddingQuotaError,
    EmbeddingTransportError, GeminiEmbeddingError,
)
from reposcope.retrieval.vector import EmbeddingIndexMismatchError


@pytest.fixture
def http(monkeypatch):
    evidence = Evidence(evidence_id="E1", snapshot_id=9, file_id=11, file_path="sample/core.py",
        symbol_id=75, chunk_id=101, start_line=5, end_line=6,
        text="def get_hmm():\n    return 'hmmm...'\n")
    response = AskResponse(answer="get_hmm returns 'hmmm...'. [E1]", evidence=[evidence], gaps=[])
    service = AsyncMock(return_value=SimpleNamespace(response=response))
    monkeypatch.setattr(repos, "answer_question", service)
    factory = Mock(side_effect=AssertionError("The HTTP route must not open sessions directly"))
    monkeypatch.setattr(repos, "SessionLocal", factory)
    with TestClient(app) as client:
        yield client, service, factory


def test_success_keeps_answer_evidence_and_contract(http):
    client, service, factory = http
    response = client.post("/api/repos/33/ask", json={"question": "What does get_hmm return?"})
    assert response.status_code == 200, response.text
    body = AskResponse.model_validate(response.json())
    assert "[E1]" in body.answer and body.evidence[0].snapshot_id == 9
    assert body.evidence[0].symbol_id == 75 and body.timings is None
    service.assert_awaited_once_with(factory, 33, "What does get_hmm return?")
    factory.assert_not_called()


def test_refusal_preserves_explicit_gaps(http):
    client, service, factory = http
    service.return_value = SimpleNamespace(response=AskResponse(
        answer="The retrieved evidence is insufficient to answer reliably.", evidence=[],
        gaps=["Source does not establish deployment behavior"]))
    response = client.post("/api/repos/33/ask", json={"question": "What happened in production?"})
    assert response.status_code == 200
    assert response.json()["evidence"] == [] and response.json()["gaps"]


@pytest.mark.parametrize("error,status", [
    (QuestionInputError("private-marker"), 422),
    (QuestionNotFoundError("private-marker"), 404),
    (QuestionNotReadyError("private-marker"), 409),
    (QuestionContextError("private-marker"), 409),
    (EmbeddingIndexMismatchError("private-marker"), 409),
    (EmbeddingQuotaError("private-marker"), 503),
    (EmbeddingTransportError("private-marker"), 503),
    (EmbeddingAuthenticationError("private-marker"), 503),
    (EmbeddingConfigurationError("private-marker"), 503),
    (LLMConfigurationError("private-marker"), 503),
    (LLMUnavailable("private-marker"), 503),
    (CitationValidationError("private-marker"), 502),
    (LLMOutputError("private-marker"), 502),
    (GeminiEmbeddingError("private-marker"), 502),
    (LLMError("private-marker"), 502),
])
def test_failures_return_sanitized_error_not_partial_answer(http, error, status):
    client, service, factory = http
    service.side_effect = error
    response = client.post("/api/repos/33/ask", json={"question": "question"})
    assert response.status_code == status, response.text
    assert response.json()["error"]["status"] == status
    assert "private-marker" not in response.text
    assert "answer" not in response.json()


@pytest.mark.parametrize("payload", [
    {"question": ""}, {"question": " "}, {"question": "x" * 4097},
    {"question": "question", "extra": True}, {},
])
def test_bad_input_is_rejected_before_service(http, payload):
    client, service, factory = http
    response = client.post("/api/repos/33/ask", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    service.assert_not_awaited()
    factory.assert_not_called()


def test_invalid_repo_id_is_rejected_before_service(http):
    client, service, factory = http
    assert client.post("/api/repos/0/ask", json={"question": "question"}).status_code == 422
    service.assert_not_awaited()


def test_contract_and_openapi_agree_on_question_limit():
    assert AskRequest.model_json_schema()["properties"]["question"]["maxLength"] == 4096
    schema = app.openapi()["components"]["schemas"]["AskRequest"]
    assert schema["properties"]["question"]["maxLength"] == 4096
