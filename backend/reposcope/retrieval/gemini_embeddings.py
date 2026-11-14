"""Hosted Gemini embeddings; no model downloads, database access, or local ML.

This module is not active until callers explicitly import it. Credentials are
read at request time, never placed in URLs, and never included in our errors.
"""
import math
import os
import time

import httpx

MODEL_NAME = "gemini-embedding-001"
EMBEDDING_DIMENSION = 384
INDEX_VERSION = "python-symbols-gemini-embedding-001-d384-codequery-v1"
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:embedContent"
_MAX_ATTEMPTS = 2
_MAX_RETRY_DELAY_SECONDS = 10.0
_RETRYABLE = {429, 500, 502, 503, 504}


class GeminiEmbeddingError(RuntimeError):
    """Sanitized embedding failure; never log provider response bodies."""


class EmbeddingConfigurationError(GeminiEmbeddingError):
    pass


class EmbeddingAuthenticationError(GeminiEmbeddingError):
    pass


class EmbeddingQuotaError(GeminiEmbeddingError):
    pass


class EmbeddingTransportError(GeminiEmbeddingError):
    pass


class EmbeddingResponseError(GeminiEmbeddingError):
    pass


def _api_key():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise EmbeddingConfigurationError("GEMINI_API_KEY is missing")
    return key


def _new_client():
    # These are per-phase network timeouts, not a total job deadline.
    return httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0, pool=5.0),
                        follow_redirects=False)


def _normalize(values):
    if not isinstance(values, list) or len(values) != EMBEDDING_DIMENSION:
        raise EmbeddingResponseError("Unexpected embedding dimension")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise EmbeddingResponseError("Embedding values must be numbers")
    try:
        vector = [float(value) for value in values]
        norm = math.hypot(*vector)
    except (ValueError, TypeError, OverflowError):
        raise EmbeddingResponseError("Invalid embedding values") from None
    if not all(math.isfinite(value) for value in vector) or not math.isfinite(norm) or norm <= 0:
        raise EmbeddingResponseError("Embedding must be finite and nonzero")
    return [value / norm for value in vector]


def _validate_text(text, maximum):
    if not isinstance(text, str):
        raise TypeError("Embedding input must be a string")
    if not text.strip() or len(text) > maximum:
        raise ValueError("Embedding input is empty or exceeds the configured character limit")


def _request(client, key, text, task_type):
    payload = {"content": {"parts": [{"text": text}]},
               "taskType": task_type, "outputDimensionality": EMBEDDING_DIMENSION}
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = client.post(_ENDPOINT, headers={"x-goog-api-key": key}, json=payload)
        except httpx.TransportError:
            if attempt + 1 < _MAX_ATTEMPTS:
                time.sleep(1.0)
                continue
            raise EmbeddingTransportError("Gemini embedding transport failed after bounded attempts") from None
        status = response.status_code
        if status == 200:
            try:
                data = response.json()
                values = data.get("embedding", {}).get("values")
            except (ValueError, AttributeError, TypeError):
                raise EmbeddingResponseError("Malformed Gemini embedding response") from None
            return _normalize(values)
        if status in {401, 403}:
            raise EmbeddingAuthenticationError("Gemini embedding credentials or project access were rejected")
        if status in _RETRYABLE and attempt + 1 < _MAX_ATTEMPTS:
            try:
                delay = float(response.headers.get("Retry-After", "1"))
            except (TypeError, ValueError):
                delay = 1.0
            if math.isfinite(delay) and 0 <= delay <= _MAX_RETRY_DELAY_SECONDS:
                time.sleep(delay)
                continue
        if status == 429:
            raise EmbeddingQuotaError("Gemini embedding quota unavailable; retry later")
        # Never include response.text, input text, request headers, or API keys.
        raise GeminiEmbeddingError(f"Gemini embedding request failed with HTTP {status}")
    raise GeminiEmbeddingError("Gemini embedding attempts exhausted")


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Sequential document requests; preserve input order and normalize outputs.

    batch_size is retained for compatibility and validation. It is not a
    provider-side batch size: each text uses the already verified embedContent
    endpoint. At most two attempts are made per text; partial results are not
    returned if a later request fails. Quota usage may include retried requests.
    """
    if not isinstance(texts, list):
        raise TypeError("texts must be a list")
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be an integer from 1 to 100")
    if len(texts) > 10000:
        raise ValueError("Too many embedding inputs")
    for text in texts:
        _validate_text(text, 100000)
    if not texts:
        return []
    key = _api_key()
    with _new_client() as client:
        return [_request(client, key, text, "RETRIEVAL_DOCUMENT") for text in texts]


def embed_query(query: str) -> list[float]:
    """Native code-query task; do not add the old BGE query prefix."""
    _validate_text(query, 4096)
    key = _api_key()
    with _new_client() as client:
        return _request(client, key, query.strip(), "CODE_RETRIEVAL_QUERY")
