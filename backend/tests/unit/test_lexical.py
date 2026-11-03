from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from reposcope.retrieval.lexical import normalize_identifier_text, search_chunks_by_lexical


@pytest.mark.parametrize("value,expected", [
    ("calculateTotal", "calculate total"),
    ("calculate_total", "calculate total"),
    ("HTTPServerError", "http server error"),
    ("parseJSON2Value", "parse json 2 value"),
    ("UserService.get_by_id", "user service get by id"),
    ("__init__", "init"),
    ("", ""),
    ("!@#()", ""),
    ("get_user_id", "get user id"),
])
def test_identifier_normalization(value, expected):
    assert normalize_identifier_text(value) == expected


@pytest.mark.parametrize("query", ["", "   ", "!@#()"])
def test_empty_queries_do_not_query_database(query):
    session = MagicMock()
    assert search_chunks_by_lexical(session, 1, query) == []
    session.execute.assert_not_called()


@pytest.mark.parametrize("repo_id", [0, -1, True, "1"])
def test_invalid_repository_id(repo_id):
    with pytest.raises(ValueError):
        search_chunks_by_lexical(MagicMock(), repo_id, "hello")


@pytest.mark.parametrize("limit", [0, 101, True, "10"])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        search_chunks_by_lexical(MagicMock(), 1, "hello", limit)


def test_invalid_query_type_and_length():
    with pytest.raises(TypeError):
        search_chunks_by_lexical(MagicMock(), 1, None)
    with pytest.raises(ValueError):
        search_chunks_by_lexical(MagicMock(), 1, "x" * 4097)


def test_sqlite_is_explicitly_unsupported():
    session = MagicMock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        search_chunks_by_lexical(session, 1, "hello")


def test_query_is_bound_and_hits_are_structured():
    session = MagicMock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    session.execute.return_value.mappings.return_value.all.return_value = [{
        "chunk_id": 1, "symbol_id": 2, "repo_id": 3, "text": "def hello(): pass",
        "name": "hello", "qualname": "hello", "file_path": "app.py",
        "start_line": 1, "end_line": 1, "score": 0.5,
    }]
    raw_query = "hello'); DROP TABLE symbols; --"
    hits = search_chunks_by_lexical(session, 3, raw_query, 5)
    statement, params = session.execute.call_args.args
    assert raw_query not in str(statement)
    assert params == {"repo_id": 3, "query": raw_query, "limit": 5}
    assert "f.repository_id = :repo_id" in str(statement)
    assert "c.repo_id = :repo_id" in str(statement)
    assert hits[0].symbol_id == 2
    assert hits[0].score == 0.5
