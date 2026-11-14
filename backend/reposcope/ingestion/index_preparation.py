"""Prepare a Python symbol index without database writes or source execution.

Initial scope: supported UTF-8 Python definitions only. This is NOT a worker,
full multi-language indexer, or historical-snapshot publication mechanism.
"""
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Callable

from reposcope.contracts.chunking import ChunkDraft
from reposcope.contracts.parsing import ParsedFile
from reposcope.ingestion.redaction import redact_secrets
from reposcope.ingestion.scanner import MAX_FILE_SIZE_BYTES, scan_repository
from reposcope.parsing.python_parser import parse_python
from reposcope.retrieval.chunker import build_symbol_chunks

INDEX_VERSION = "python-symbols-bge-small-v1"
EMBEDDING_DIMENSION = 384


class IndexPreparationError(RuntimeError):
    """Preparation failed; the index must not be published as ready."""


@dataclass(frozen=True)
class PreparedPythonIndex:
    parsed_files: tuple[ParsedFile, ...]
    chunks: tuple[ChunkDraft, ...]
    embeddings: tuple[tuple[float, ...], ...]
    analysis: object
    non_python_file_count: int
    redacted_file_count: int
    index_version: str = INDEX_VERSION

    @property
    def symbol_count(self) -> int:
        return sum(len(file.symbols) for file in self.parsed_files)


def _read_scanned_file(root: Path, item) -> bytes:
    # Recheck immediately before reading. The clone/workspace must be private
    # to the worker; these checks are not a sandbox for concurrent hostile writers.
    path = Path(item.absolute_path)
    if path.is_symlink():
        raise IndexPreparationError("A scanned file became a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise IndexPreparationError("A scanned file escaped the repository")
    if resolved.relative_to(root).as_posix() != item.relative_path:
        raise IndexPreparationError("A scanned file path changed")
    with resolved.open("rb") as handle:
        raw = handle.read(MAX_FILE_SIZE_BYTES + 1)
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise IndexPreparationError("A scanned file exceeded the size limit")
    if len(raw) != item.size_bytes:
        raise IndexPreparationError("A scanned file changed size")
    return raw


def _validate_embeddings(rows, expected: int) -> tuple[tuple[float, ...], ...]:
    try:
        rows = list(rows)
        if len(rows) != expected:
            raise ValueError("count mismatch")
        vectors = []
        for row in rows:
            values = tuple(float(value) for value in row)
            if len(values) != EMBEDDING_DIMENSION:
                raise ValueError("dimension mismatch")
            if not all(isfinite(value) for value in values):
                raise ValueError("nonfinite vector")
            if sum(value * value for value in values) <= 0:
                raise ValueError("zero vector")
            vectors.append(values)
        return tuple(vectors)
    except (TypeError, ValueError, OverflowError) as exc:
        raise IndexPreparationError("Embedding count, dimension, or values are invalid") from exc


def prepare_python_index(
    repository_path: Path | str,
    *,
    embedder: Callable | None = None,
    resolver: Callable | None = None,
    check_cancelled: Callable[[], None] | None = None,
    source_roots: tuple[str, ...] = (".",),
    max_python_files: int = 1000,
    max_source_bytes: int = 50 * 1024 * 1024,
    max_chunks: int = 10000,
    embedding_batch_size: int = 32,
) -> PreparedPythonIndex:
    """Build a bounded index in memory; injectable services make tests offline.

    Cancellation is checked between stages/batches, not inside a model inference.
    Scanner-skipped files are outside this stage's coverage. Limits apply after
    scanning; the scanner's own metadata enumeration is not bounded here.
    """
    for name, value in (("max_python_files", max_python_files),
                        ("max_source_bytes", max_source_bytes),
                        ("max_chunks", max_chunks),
                        ("embedding_batch_size", embedding_batch_size)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    root = Path(repository_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository_path must be a directory")
    check = check_cancelled or (lambda: None)
    check()
    scanned = scan_repository(root)
    python_files = [item for item in scanned if item.extension == ".py"]
    if not python_files:
        raise IndexPreparationError("No supported Python files were found")
    if len(python_files) > max_python_files:
        raise IndexPreparationError("Python file count exceeds the configured limit")
    if sum(item.size_bytes for item in python_files) > max_source_bytes:
        raise IndexPreparationError("Python source size exceeds the configured limit")

    parsed_files, chunks = [], []
    redacted_count = 0
    for item in python_files:
        check()
        raw = _read_scanned_file(root, item)
        safe = redact_secrets(raw)
        if sha256(safe).hexdigest() != item.content_hash:
            raise IndexPreparationError("A scanned file changed after scanning")
        # Existing multiline redaction can collapse source lines. Refuse rather
        # than publish citations with incorrect original-file line numbers.
        if safe.count(b"\n") != raw.count(b"\n"):
            raise IndexPreparationError("Redaction changed source line numbering")
        redacted_count += safe != raw
        try:
            parsed = parse_python(safe, file_path=item.relative_path)
            drafts = build_symbol_chunks(parsed)
        except Exception as exc:
            raise IndexPreparationError("Python parsing or chunk construction failed") from exc
        parsed_files.append(parsed)
        chunks.extend(drafts)
        if len(chunks) > max_chunks:
            raise IndexPreparationError("Chunk count exceeds the configured limit")
    if not chunks:
        raise IndexPreparationError("No indexable Python definitions were found")

    check()
    if resolver is None:
        from reposcope.parsing.resolver_pipeline import analyze_python_files
        resolver = analyze_python_files
    analysis = resolver(parsed_files, source_roots=source_roots)
    check()
    if embedder is None:
        from reposcope.retrieval.embeddings import embed_texts
        embedder = embed_texts
    embeddings = []
    for start in range(0, len(chunks), embedding_batch_size):
        check()
        batch = chunks[start:start + embedding_batch_size]
        values = embedder([chunk.text for chunk in batch])
        embeddings.extend(_validate_embeddings(values, len(batch)))
    check()
    return PreparedPythonIndex(
        parsed_files=tuple(parsed_files), chunks=tuple(chunks),
        embeddings=tuple(embeddings), analysis=analysis,
        non_python_file_count=len(scanned) - len(python_files),
        redacted_file_count=redacted_count,
    )
