"""Offline HTTP-mocked tests: no provider requests, database writes, or models."""
import importlib
import json
import math
from unittest.mock import Mock

import httpx
import pytest

from reposcope.retrieval import gemini_embeddings as embeddings

VECTOR = [2.0] + [0.0] * 383
FAKE_KEY = "synthetic-unit-test-key-not-a-real-secret"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(embeddings.time, "sleep", Mock())
    def unexpected():
        raise AssertionError("Test must configure a MockTransport; real network is forbidden")
    monkeypatch.setattr(embeddings, "_new_client", unexpected)


def transport(monkeypatch, handler):
    monkeypatch.setattr(embeddings, "_new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


def success():
    return httpx.Response(200, json={"embedding": {"values": VECTOR}})


def test_document_requests_use_correct_task_and_preserve_order(monkeypatch):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["x-goog-api-key"] == FAKE_KEY
        assert FAKE_KEY not in str(request.url)
        assert not request.url.query
        assert body["taskType"] == "RETRIEVAL_DOCUMENT"
        assert body["outputDimensionality"] == 384
        return success()
    transport(monkeypatch, handler)
    actual = embeddings.embed_texts(["def first(): pass", "def second(): pass"])
    assert len(actual) == 2 and all(len(vector) == 384 for vector in actual)
    assert [call["content"]["parts"][0]["text"] for call in calls] == [
        "def first(): pass", "def second(): pass"]
    assert actual[0] == [1.0] + [0.0] * 383


def test_query_uses_native_code_task_without_bge_prefix(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert body["taskType"] == "CODE_RETRIEVAL_QUERY"
        assert body["content"]["parts"] == [{"text": "find validation"}]
        return success()
    transport(monkeypatch, handler)
    assert embeddings.embed_query(" find validation ") == [1.0] + [0.0] * 383


def test_empty_documents_need_no_key_or_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert embeddings.embed_texts([]) == []


@pytest.mark.parametrize("operation", [lambda: embeddings.embed_query("query"),
                                      lambda: embeddings.embed_texts(["document"])])
def test_missing_key_fails_before_network(monkeypatch, operation):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(embeddings.EmbeddingConfigurationError):
        operation()


@pytest.mark.parametrize("text", ["", "   ", "x" * 4097])
def test_invalid_queries_fail_before_network(text):
    with pytest.raises(ValueError):
        embeddings.embed_query(text)


def test_nonstring_query_fails_before_network():
    with pytest.raises(TypeError):
        embeddings.embed_query(None)


@pytest.mark.parametrize("batch_size", [0, 101, True, "32"])
def test_invalid_batch_size_fails_before_network(batch_size):
    with pytest.raises(ValueError):
        embeddings.embed_texts(["document"], batch_size=batch_size)


@pytest.mark.parametrize("values", [[1.0], [0.0] * 384, [float("inf")] + [0.0] * 383,
                                  [float("nan")] + [0.0] * 383, [True] + [0.0] * 383,
                                  ["not-a-number"] + [0.0] * 383, None])
def test_invalid_vectors_are_rejected(values):
    with pytest.raises(embeddings.EmbeddingResponseError):
        embeddings._normalize(values)


def test_output_has_unit_norm():
    vector = embeddings._normalize([1.0] * 384)
    assert len(vector) == 384
    assert math.hypot(*vector) == pytest.approx(1.0)


@pytest.mark.parametrize("response", [httpx.Response(200, text="not-json"),
    httpx.Response(200, json={}), httpx.Response(200, json=[]),
    httpx.Response(200, json={"embedding": None})])
def test_malformed_response_fails_without_retry(monkeypatch, response):
    handler = Mock(return_value=response)
    transport(monkeypatch, handler)
    with pytest.raises(embeddings.EmbeddingResponseError):
        embeddings.embed_query("query")
    assert handler.call_count == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_errors_are_not_retried_or_leaked(monkeypatch, status):
    handler = Mock(return_value=httpx.Response(status, text=f"private code and {FAKE_KEY}"))
    transport(monkeypatch, handler)
    with pytest.raises(embeddings.GeminiEmbeddingError) as caught:
        embeddings.embed_query("private code")
    assert handler.call_count == 1
    assert FAKE_KEY not in str(caught.value) and "private code" not in str(caught.value)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_errors_retry_only_once(monkeypatch, status):
    responses = iter([httpx.Response(status), success()])
    handler = Mock(side_effect=lambda _: next(responses))
    transport(monkeypatch, handler)
    assert len(embeddings.embed_query("query")) == 384
    assert handler.call_count == 2
    embeddings.time.sleep.assert_called_once_with(1.0)


def test_exhausted_quota_is_sanitized_and_bounded(monkeypatch):
    handler = Mock(return_value=httpx.Response(429, text=FAKE_KEY))
    transport(monkeypatch, handler)
    with pytest.raises(embeddings.EmbeddingQuotaError) as caught:
        embeddings.embed_query("query")
    assert handler.call_count == 2 and FAKE_KEY not in str(caught.value)


def test_long_retry_after_does_not_block_worker(monkeypatch):
    handler = Mock(return_value=httpx.Response(429, headers={"Retry-After": "3600"}))
    transport(monkeypatch, handler)
    with pytest.raises(embeddings.EmbeddingQuotaError):
        embeddings.embed_query("query")
    assert handler.call_count == 1
    embeddings.time.sleep.assert_not_called()


def test_transport_error_is_bounded_and_sanitized(monkeypatch):
    handler = Mock(side_effect=httpx.ConnectError(FAKE_KEY))
    transport(monkeypatch, handler)
    with pytest.raises(embeddings.EmbeddingTransportError) as caught:
        embeddings.embed_query("query")
    assert handler.call_count == 2 and FAKE_KEY not in str(caught.value)


def test_failed_later_document_does_not_return_partial_result(monkeypatch):
    responses = iter([success(), httpx.Response(400)])
    transport(monkeypatch, lambda _: next(responses))
    with pytest.raises(embeddings.GeminiEmbeddingError):
        embeddings.embed_texts(["first", "second"])


def test_index_version_distinguishes_old_bge_vectors():
    assert embeddings.INDEX_VERSION != "python-symbols-bge-small-v1"
    assert "gemini-embedding-001" in embeddings.INDEX_VERSION
    assert "d384" in embeddings.INDEX_VERSION


def test_import_has_no_model_or_key_requirement(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    importlib.reload(embeddings)
    assert embeddings.MODEL_NAME == "gemini-embedding-001"
