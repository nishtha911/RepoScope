from reposcope.evaluation.baseline import (
    build_baseline_index,
    fixed_size_chunks,
    recall_at_k,
    search_baseline,
)


def embed(texts):
    return [[float(len(text)), float(text.count("needle"))] for text in texts]


def query_embedding(text):
    return [float(len(text)), float(text.count("needle"))]


def test_fixed_size_chunking_is_deterministic_and_non_overlapping():
    assert fixed_size_chunks("a.py", "abcdefgh", chunk_size=3) == [
        (0, 3, "abc"),
        (3, 6, "def"),
        (6, 8, "gh"),
    ]


def test_baseline_search_uses_vectors_only():
    index = build_baseline_index(
        [("a.py", "plain text"), ("b.py", "needle needle")],
        embed_texts=embed,
        chunk_size=100,
    )

    hits = search_baseline(index, "needle", embed_query=query_embedding)

    assert hits[0].chunk.source == "b.py"
    assert hits[0].score > hits[1].score


def test_baseline_recall_is_measurable():
    index = build_baseline_index(
        [("a.py", "plain text"), ("b.py", "needle needle")],
        embed_texts=embed,
        chunk_size=100,
    )

    assert recall_at_k(
        index,
        [("needle", {2})],
        embed_query=query_embedding,
        k=1,
    ) == 1.0
