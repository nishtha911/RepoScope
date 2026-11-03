from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from reposcope.retrieval import pipeline
from reposcope.retrieval.pipeline import search_chunks_by_exact


# Exact-symbol retrieval tests.


def test_exact_search_returns_chunks_from_the_session():
    session = Mock()

    expected = [
        SimpleNamespace(id=10, symbol_id=101, repo_id=1),
    ]

    session.scalars.return_value = expected

    actual = search_chunks_by_exact(
        session,
        repo_id=1,
        query="resolve_calls",
        limit=10,
    )

    assert actual == expected
    session.scalars.assert_called_once()
    session.commit.assert_not_called()


def test_exact_search_constructs_scoped_parameterized_query():
    session = Mock()
    session.scalars.return_value = []

    search_chunks_by_exact(
        session,
        repo_id=7,
        query=" SymbolResolver.resolve_calls ",
        limit=5,
    )

    statement = session.scalars.call_args.args[0]

    compiled = statement.compile(
        dialect=postgresql.dialect(),
    )

    sql = " ".join(str(compiled).split())
    parameters = compiled.params

    assert "JOIN symbols" in sql
    assert "JOIN files" in sql

    assert "chunks.repo_id =" in sql
    assert "files.repository_id =" in sql

    assert "symbols.name =" in sql
    assert "symbols.qualname =" in sql

    assert "ORDER BY CASE" in sql
    assert "chunks.id ASC" in sql
    assert "LIMIT" in sql

    assert "SymbolResolver.resolve_calls" in parameters.values()

    # User input must be bound rather than inserted into SQL text.
    assert "SymbolResolver.resolve_calls" not in sql

    assert 7 in parameters.values()
    assert 5 in parameters.values()


def test_empty_query_does_not_execute_sql():
    session = Mock()

    assert search_chunks_by_exact(session, 1, "   ") == []

    session.scalars.assert_not_called()


@pytest.mark.parametrize("repo_id", [0, -1, True, "1"])
def test_invalid_repository_is_rejected_before_query(repo_id):
    session = Mock()

    with pytest.raises(ValueError, match="repo_id"):
        search_chunks_by_exact(session, repo_id, "resolve")

    session.scalars.assert_not_called()


@pytest.mark.parametrize("limit", [0, 101, True, "10"])
def test_invalid_limit_is_rejected_before_query(limit):
    session = Mock()

    with pytest.raises(ValueError, match="limit"):
        search_chunks_by_exact(
            session,
            1,
            "resolve",
            limit=limit,
        )

    session.scalars.assert_not_called()


def test_non_string_query_is_rejected():
    session = Mock()

    with pytest.raises(TypeError, match="query"):
        search_chunks_by_exact(session, 1, None)

    session.scalars.assert_not_called()


def test_oversized_query_is_rejected():
    session = Mock()

    with pytest.raises(ValueError, match="4096"):
        search_chunks_by_exact(session, 1, "x" * 4097)

    session.scalars.assert_not_called()


# Hybrid retrieval fixtures and tests.


def make_chunk(chunk_id, *, repo_id=1, text=None):
    return SimpleNamespace(
        id=chunk_id,
        symbol_id=chunk_id + 1000,
        repo_id=repo_id,
        text=text if text is not None else f"source {chunk_id}",
    )


def make_lexical_hit(chunk_id, *, repo_id=1, text=None):
    return SimpleNamespace(
        chunk_id=chunk_id,
        symbol_id=chunk_id + 1000,
        repo_id=repo_id,
        text=text if text is not None else f"source {chunk_id}",
    )


def stub_retrievers(monkeypatch, *, exact, lexical, vector):
    exact_mock = Mock(return_value=exact)
    lexical_mock = Mock(return_value=lexical)
    vector_mock = Mock(return_value=vector)

    monkeypatch.setattr(
        pipeline,
        "search_chunks_by_exact",
        exact_mock,
    )

    monkeypatch.setattr(
        pipeline,
        "search_chunks_by_lexical",
        lexical_mock,
    )

    monkeypatch.setattr(
        pipeline,
        "_search_vector_chunks",
        vector_mock,
    )

    return exact_mock, lexical_mock, vector_mock


def test_hybrid_fuses_all_three_rankings(monkeypatch):
    session = Mock()

    retrievers = stub_retrievers(
        monkeypatch,
        exact=[make_chunk(10), make_chunk(20)],
        lexical=[
            make_lexical_hit(20),
            make_lexical_hit(10),
        ],
        vector=[make_chunk(30), make_chunk(10)],
    )

    hits = pipeline.search_chunks_hybrid(
        session,
        repo_id=1,
        query=" resolve ",
        limit=3,
        candidate_limit=10,
    )

    assert [hit.chunk_id for hit in hits] == [10, 20, 30]

    assert hits[0].score == pytest.approx(
        1 / 61 + 1 / 62 + 1 / 62
    )

    assert hits[1].score == pytest.approx(
        1 / 62 + 1 / 61
    )

    assert hits[2].score == pytest.approx(1 / 61)

    assert hits[0].symbol_id == 1010
    assert hits[0].repo_id == 1
    assert hits[0].text == "source 10"

    for retriever in retrievers:
        retriever.assert_called_once_with(
            session,
            repo_id=1,
            query="resolve",
            limit=10,
        )

    session.commit.assert_not_called()


def test_hybrid_empty_query_skips_all_retrievers(monkeypatch):
    retrievers = stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[],
    )

    assert pipeline.search_chunks_hybrid(
        Mock(),
        1,
        "   ",
    ) == []

    for retriever in retrievers:
        retriever.assert_not_called()


def test_hybrid_all_empty_results(monkeypatch):
    stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[],
    )

    assert pipeline.search_chunks_hybrid(
        Mock(),
        1,
        "resolve",
    ) == []


def test_hybrid_applies_final_limit(monkeypatch):
    stub_retrievers(
        monkeypatch,
        exact=[make_chunk(10), make_chunk(20)],
        lexical=[make_lexical_hit(20)],
        vector=[make_chunk(30)],
    )

    hits = pipeline.search_chunks_hybrid(
        Mock(),
        1,
        "resolve",
        limit=1,
        candidate_limit=3,
    )

    assert len(hits) == 1
    assert hits[0].chunk_id == 20


def test_hybrid_rejects_cross_repository_candidates(monkeypatch):
    stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[make_chunk(10, repo_id=2)],
    )

    with pytest.raises(ValueError, match="another repository"):
        pipeline.search_chunks_hybrid(
            Mock(),
            1,
            "resolve",
        )


def test_hybrid_rejects_inconsistent_chunk_metadata(monkeypatch):
    stub_retrievers(
        monkeypatch,
        exact=[make_chunk(10)],
        lexical=[
            make_lexical_hit(
                10,
                text="different source",
            ),
        ],
        vector=[],
    )

    with pytest.raises(ValueError, match="inconsistent metadata"):
        pipeline.search_chunks_hybrid(
            Mock(),
            1,
            "resolve",
        )


def test_hybrid_does_not_hide_retriever_failure(monkeypatch):
    _, _, vector_mock = stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[],
    )

    vector_mock.side_effect = RuntimeError(
        "Embedding unavailable"
    )

    with pytest.raises(RuntimeError, match="Embedding unavailable"):
        pipeline.search_chunks_hybrid(
            Mock(),
            1,
            "resolve",
        )


def test_hybrid_rejects_candidate_limit_below_result_limit(
    monkeypatch,
):
    retrievers = stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[],
    )

    with pytest.raises(ValueError, match="at least limit"):
        pipeline.search_chunks_hybrid(
            Mock(),
            1,
            "resolve",
            limit=10,
            candidate_limit=5,
        )

    for retriever in retrievers:
        retriever.assert_not_called()


@pytest.mark.parametrize("k", [0, -1, True, "60"])
def test_hybrid_rejects_invalid_k(monkeypatch, k):
    retrievers = stub_retrievers(
        monkeypatch,
        exact=[],
        lexical=[],
        vector=[],
    )

    with pytest.raises(ValueError, match="k must"):
        pipeline.search_chunks_hybrid(
            Mock(),
            1,
            "resolve",
            k=k,
        )

    for retriever in retrievers:
        retriever.assert_not_called()