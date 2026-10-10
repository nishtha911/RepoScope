from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model

def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed a batch of document texts."""
    if not texts:
        return []
    
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()

def embed_query(query: str) -> list[float]:
    """Embed a search query with the required query prefix."""
    model = get_model()
    embeddings = model.encode(
        [QUERY_PREFIX + query],
        batch_size=1,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embeddings[0].tolist()