"""Offline migration fences and hosted-build tests; no API/DB/model work."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from reposcope.retrieval import embeddings, gemini_embeddings, vector
from reposcope.ingestion.index_preparation import INDEX_VERSION, PreparedPythonIndex


def session_with(rows):
    session = Mock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    session.execute.return_value.all.return_value = rows
    session.scalars.return_value = []
    return session


def test_ingestion_and_client_versions_match():
    assert INDEX_VERSION == gemini_embeddings.INDEX_VERSION
    assert PreparedPythonIndex.__dataclass_fields__["index_version"].default == INDEX_VERSION
    assert INDEX_VERSION != "python-symbols-bge-small-v1"


def test_adapter_exposes_hosted_helpers():
    assert embeddings.embed_texts.__module__ == gemini_embeddings.__name__
    assert embeddings.embed_query.__module__ == gemini_embeddings.__name__
    assert embeddings.MODEL_NAME == "gemini-embedding-001"


def test_adapter_refuses_local_model():
    with pytest.raises(RuntimeError, match="no local model"):
        embeddings.get_model()


@pytest.mark.parametrize("rows", [
    [(7, "python-symbols-bge-small-v1", "ready")],
    [(7, INDEX_VERSION, "indexing")],
    [(None, None, None)],
    [(7, INDEX_VERSION, "ready"), (8, INDEX_VERSION, "ready")],
    [(7, INDEX_VERSION, "ready"), (8, "python-symbols-bge-small-v1", "ready")],
])
def test_incompatible_reads_fail_before_provider_or_vector_query(monkeypatch, rows):
    session = session_with(rows)
    provider = Mock(side_effect=AssertionError("Provider must not be called"))
    monkeypatch.setattr(embeddings, "embed_query", provider)
    with pytest.raises(vector.EmbeddingIndexMismatchError):
        vector.search_chunks_by_vector(session, 33, "query")
    provider.assert_not_called()
    session.scalars.assert_not_called()
    session.commit.assert_not_called()


def test_no_files_returns_no_hits_without_provider(monkeypatch):
    session = session_with([])
    provider = Mock()
    monkeypatch.setattr(embeddings, "embed_query", provider)
    assert vector.search_chunks_by_vector(session, 33, "query") == []
    provider.assert_not_called()
    session.scalars.assert_not_called()


def test_compatible_search_scopes_actual_snapshot(monkeypatch):
    session = session_with([(7, INDEX_VERSION, "ready")])
    provider = Mock(return_value=[1.0] + [0.0] * 383)
    monkeypatch.setattr(embeddings, "embed_query", provider)
    vector.search_chunks_by_vector(session, 33, " query ")
    provider.assert_called_once_with("query")
    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "files.snapshot_id =" in str(compiled)
    assert 7 in compiled.params.values() and 33 in compiled.params.values()
    session.commit.assert_not_called()


def test_metadata_check_scopes_file_and_snapshot_ownership():
    session = session_with([(7, INDEX_VERSION, "ready")])
    assert vector._compatible_snapshot_id(session, 33) == 7
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN repository_snapshots" in sql
    assert "repository_snapshots.repository_id = files.repository_id" in sql
    assert "files.repository_id =" in sql


@pytest.mark.parametrize("rows", [[(7, "python-symbols-bge-small-v1", "ready")], []])
def test_legacy_writer_cannot_mix_unversioned_or_old_vectors(monkeypatch, rows):
    session = session_with(rows)
    provider = Mock()
    monkeypatch.setattr(embeddings, "embed_texts", provider)
    with pytest.raises(vector.EmbeddingIndexMismatchError):
        vector.bulk_insert_chunks(session, 33, [SimpleNamespace(text="code", symbol_key="x")], {"x": 1})
    provider.assert_not_called()
    session.add_all.assert_not_called()
    session.commit.assert_not_called()


def test_empty_legacy_write_is_noop():
    session = session_with([])
    vector.bulk_insert_chunks(session, 33, [], {})
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def build_module():
    path = Path(__file__).resolve().parents[2] / "render_build.py"
    spec = importlib.util.spec_from_file_location("gemini_render_build_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hosted_builder_drops_local_ml_but_keeps_http_client():
    pin, remaining = build_module().partition_requirements(
        "torch==2.14.1\nsentence-transformers==6.1.0\npytest==9.1.1\nhttpx>=0.27,<1\nfastembed==0.9.1\n")
    assert pin == "2.14.1"
    assert remaining == ["httpx>=0.27,<1"]


def test_build_main_refuses_local_environment(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    with pytest.raises(RuntimeError, match="only for Render"):
        build_module().main()


def test_adapter_has_no_local_ml_imports():
    tree = ast.parse(Path(embeddings.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all(not name.startswith(("torch", "sentence_transformers", "fastembed", "onnxruntime"))
               for name in imports if name)
