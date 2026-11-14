"""Offline preparation tests: real parser/chunker, injected fake model/resolver.

No database, network clone, model download, or LLM call is used.
"""
from types import SimpleNamespace

import pytest

from reposcope.ingestion import index_preparation as preparation
from reposcope.ingestion.index_preparation import IndexPreparationError, prepare_python_index


def fake_embeddings(texts):
    return [[1.0] + [0.0] * 383 for _ in texts]


def fake_resolver(parsed_files, *, source_roots):
    return SimpleNamespace(edges=(), results=())


def prepare(path, **options):
    return prepare_python_index(path, embedder=options.pop("embedder", fake_embeddings),
                                resolver=options.pop("resolver", fake_resolver), **options)


@pytest.fixture
def sample(tmp_path):
    (tmp_path / "example.py").write_text(
        "def helper():\n    return 1\n\ndef run():\n    return helper()\n", encoding="utf-8")
    return tmp_path


def test_builds_one_chunk_per_symbol(sample):
    result = prepare(sample)
    assert len(result.parsed_files) == 1
    assert result.symbol_count == len(result.chunks) == len(result.embeddings) == 2
    assert all(len(vector) == 384 for vector in result.embeddings)
    assert {chunk.symbol_key for chunk in result.chunks} == {
        symbol.local_key for symbol in result.parsed_files[0].symbols}


def test_real_resolver_finds_definition_call(sample):
    result = prepare_python_index(sample, embedder=fake_embeddings)
    assert any(edge.source.symbol_key is not None and edge.target.symbol_key is not None
               for edge in result.analysis.edges)


def test_redacts_before_parse_chunk_and_embedding(tmp_path):
    secret = "sample-private-value-123"
    (tmp_path / "example.py").write_text(
        f'def run():\n    api_key = "{secret}"\n    return api_key\n', encoding="utf-8")
    seen = []
    def embed(texts):
        seen.extend(texts)
        return fake_embeddings(texts)
    result = prepare(tmp_path, embedder=embed)
    assert result.redacted_file_count == 1
    assert secret not in result.parsed_files[0].source_text
    assert all(secret not in text for text in seen)
    assert "[REDACTED]" in result.chunks[0].text


def test_rejects_multiline_redaction_that_changes_citation_lines(tmp_path):
    (tmp_path / "example.py").write_text(
        'KEY = """-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"""\ndef run():\n    return 1\n',
        encoding="utf-8")
    with pytest.raises(IndexPreparationError, match="line numbering"):
        prepare(tmp_path)


def test_rejects_invalid_python(tmp_path):
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(IndexPreparationError, match="parsing"):
        prepare(tmp_path)


def test_no_python_or_no_definitions_is_not_success(tmp_path):
    (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
    with pytest.raises(IndexPreparationError, match="No supported Python"):
        prepare(tmp_path)
    (tmp_path / "constants.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(IndexPreparationError, match="No indexable"):
        prepare(tmp_path)


def test_counts_non_python_files_without_parsing_them(sample):
    (sample / "readme.md").write_text("hello", encoding="utf-8")
    result = prepare(sample)
    assert result.non_python_file_count == 1
    assert len(result.parsed_files) == 1


@pytest.mark.parametrize("embedder", [
    lambda texts: [],
    lambda texts: [[1.0] * 383 for _ in texts],
    lambda texts: [[float("nan")] + [0.0] * 383 for _ in texts],
    lambda texts: [[0.0] * 384 for _ in texts],
])
def test_rejects_invalid_embedding_results(sample, embedder):
    with pytest.raises(IndexPreparationError, match="Embedding"):
        prepare(sample, embedder=embedder)


def test_embedding_batches_are_bounded(sample):
    sizes = []
    def embed(texts):
        sizes.append(len(texts))
        return fake_embeddings(texts)
    prepare(sample, embedder=embed, embedding_batch_size=1)
    assert sizes == [1, 1]


def test_limits_fail_instead_of_silently_truncating(sample):
    with pytest.raises(IndexPreparationError, match="source size"):
        prepare(sample, max_source_bytes=1)
    with pytest.raises(IndexPreparationError, match="Chunk count"):
        prepare(sample, max_chunks=1)
    (sample / "second.py").write_text("def second():\n    return 2\n", encoding="utf-8")
    with pytest.raises(IndexPreparationError, match="file count"):
        prepare(sample, max_python_files=1)


def test_detects_file_changed_after_scanning(sample, monkeypatch):
    scanned = preparation.scan_repository(sample)
    (sample / "example.py").write_text(
        "def changed():\n    return 100\n", encoding="utf-8")
    monkeypatch.setattr(preparation, "scan_repository", lambda root: scanned)
    with pytest.raises(IndexPreparationError, match="changed"):
        prepare(sample)


def test_cancellation_stops_preparation(sample):
    def cancelled():
        raise RuntimeError("lease lost")
    with pytest.raises(RuntimeError, match="lease lost"):
        prepare(sample, check_cancelled=cancelled)


def test_complete_function_body_is_retained(sample):
    result = prepare(sample)
    chunk = next(chunk for chunk in result.chunks if chunk.qualname == "run")
    assert "return helper()" in chunk.body_text
    assert chunk.start_line == 4 and chunk.end_line == 5
