import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from reposcope.retrieval.vector import search_chunks_by_vector


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Replace only the embedding module for this test."""
    module = ModuleType("reposcope.retrieval.embeddings")

    embed_query_mock = Mock(
        return_value=[0.1] * 384,
    )

    module.embed_query = embed_query_mock

    monkeypatch.setitem(
        sys.modules,
        "reposcope.retrieval.embeddings",
        module,
    )

    return embed_query_mock


def make_session(dialect_name="postgresql"):
    session = Mock()

    session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name=dialect_name),
    )

    session.scalars.return_value = []

    return session


def test_vector_search_returns_session_results(fake_embeddings):
    session = make_session()

    expected = [
        SimpleNamespace(
            id=10,
            symbol_id=101,
            repo_id=1,
            text="example source",
        ),
    ]

    session.scalars.return_value = expected

    actual = search_chunks_by_vector(
        session,
        repo_id=1,
        query=" resolve calls ",
        limit=5,
    )

    assert actual == expected

    fake_embeddings.assert_called_once_with("resolve calls")
    session.scalars.assert_called_once()
    session.commit.assert_not_called()


def test_vector_query_is_scoped_and_excludes_null_embeddings(
    fake_embeddings,
):
    session = make_session()

    search_chunks_by_vector(
        session,
        repo_id=7,
        query="payment validation",
        limit=5,
    )

    statement = session.scalars.call_args.args[0]

    compiled = statement.compile(
        dialect=postgresql.dialect(),
    )

    sql = " ".join(str(compiled).split())

    assert "JOIN symbols" in sql
    assert "JOIN files" in sql

    assert "chunks.repo_id =" in sql
    assert "files.repository_id =" in sql

    assert "chunks.embedding IS NOT NULL" in sql

    # pgvector cosine-distance operator.
    assert "<=>" in sql

    assert "ORDER BY" in sql
    assert "chunks.id ASC" in sql
    assert "LIMIT" in sql

    assert 7 in compiled.params.values()
    assert 5 in compiled.params.values()

    fake_embeddings.assert_called_once_with(
        "payment validation"
    )


def test_empty_query_skips_embeddings_and_database(
    fake_embeddings,
):
    session = make_session()

    actual = search_chunks_by_vector(
        session,
        repo_id=1,
        query="   ",
    )

    assert actual == []

    fake_embeddings.assert_not_called()
    session.get_bind.assert_not_called()
    session.scalars.assert_not_called()


def test_non_postgresql_session_is_rejected_before_embedding(
    fake_embeddings,
):
    session = make_session("sqlite")

    with pytest.raises(
        RuntimeError,
        match="requires PostgreSQL",
    ):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query="resolve",
        )

    fake_embeddings.assert_not_called()
    session.scalars.assert_not_called()


@pytest.mark.parametrize("repo_id", [0, -1, True, "1"])
def test_invalid_repository_skips_embeddings_and_database(
    fake_embeddings,
    repo_id,
):
    session = make_session()

    with pytest.raises(ValueError, match="repo_id"):
        search_chunks_by_vector(
            session,
            repo_id=repo_id,
            query="resolve",
        )

    fake_embeddings.assert_not_called()
    session.get_bind.assert_not_called()
    session.scalars.assert_not_called()


@pytest.mark.parametrize("limit", [0, 101, True, "10"])
def test_invalid_limit_skips_embeddings_and_database(
    fake_embeddings,
    limit,
):
    session = make_session()

    with pytest.raises(ValueError, match="limit"):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query="resolve",
            limit=limit,
        )

    fake_embeddings.assert_not_called()
    session.get_bind.assert_not_called()
    session.scalars.assert_not_called()


def test_non_string_query_is_rejected(fake_embeddings):
    session = make_session()

    with pytest.raises(TypeError, match="query"):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query=None,
        )

    fake_embeddings.assert_not_called()
    session.scalars.assert_not_called()


def test_oversized_query_is_rejected(fake_embeddings):
    session = make_session()

    with pytest.raises(ValueError, match="4096"):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query="x" * 4097,
        )

    fake_embeddings.assert_not_called()
    session.scalars.assert_not_called()


def test_embedding_failure_is_not_hidden(fake_embeddings):
    session = make_session()

    fake_embeddings.side_effect = RuntimeError(
        "Embedding unavailable"
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding unavailable",
    ):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query="resolve",
        )

    session.scalars.assert_not_called()


def test_database_failure_is_not_hidden(fake_embeddings):
    session = make_session()

    session.scalars.side_effect = RuntimeError(
        "Database unavailable"
    )

    with pytest.raises(
        RuntimeError,
        match="Database unavailable",
    ):
        search_chunks_by_vector(
            session,
            repo_id=1,
            query="resolve",
        )

    fake_embeddings.assert_called_once_with("resolve")
    session.commit.assert_not_called()