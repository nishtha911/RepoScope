"""Application embedding interface: hosted Gemini only; no local fallback."""
from reposcope.retrieval.gemini_embeddings import (
    EMBEDDING_DIMENSION,
    INDEX_VERSION,
    MODEL_NAME,
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingQuotaError,
    EmbeddingResponseError,
    EmbeddingTransportError,
    GeminiEmbeddingError,
    embed_query,
    embed_texts,
)


def get_model():
    raise RuntimeError("Hosted embeddings have no local model; use embed_texts or embed_query")
