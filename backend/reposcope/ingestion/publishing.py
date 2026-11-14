"""Atomic first-publication and exact-replay support for Python indexes.

No clone, model inference, deletion, schema changes, or implicit re-indexing.
A different existing repository index is rejected, not overwritten.
The transaction publishes all records and marks the job successful together.
"""
from dataclasses import dataclass
from math import isfinite
import re

from sqlalchemy import func, select, text

from reposcope.contracts.parsing import ParsedFile
from reposcope.ingestion.index_preparation import PreparedPythonIndex
from reposcope.jobs.queue import ClaimedJob, LeaseLostError, mark_job_succeeded
from reposcope.models import Chunk, Edge, File, Repository, RepositorySnapshot, Symbol
from reposcope.retrieval.chunker import build_symbol_chunks


class PublicationConflictError(RuntimeError):
    """Existing data cannot safely be treated as this prepared snapshot."""


@dataclass(frozen=True)
class PublishedIndex:
    snapshot_id: int
    file_count: int
    symbol_count: int
    chunk_count: int
    edge_count: int
    skipped_non_symbol_edges: int
    reused: bool


def _signature(path, symbol):
    return (path, symbol.name, symbol.qualname, symbol.kind,
            symbol.start_line, symbol.end_line)


def _validate(prepared):
    if not isinstance(prepared, PreparedPythonIndex):
        raise TypeError("prepared must be a PreparedPythonIndex")
    if not prepared.index_version or len(prepared.index_version) > 100:
        raise ValueError("index_version must contain 1 to 100 characters")
    if not prepared.parsed_files or not prepared.chunks:
        raise ValueError("Refusing an empty prepared index")
    files, symbols, signatures, drafts = {}, {}, {}, {}
    for original in prepared.parsed_files:
        parsed = ParsedFile.model_validate(original.model_dump())
        if parsed.file_path in files:
            raise ValueError("Duplicate parsed file")
        files[parsed.file_path] = parsed
        for symbol in parsed.symbols:
            signature = _signature(parsed.file_path, symbol)
            if symbol.local_key in symbols or signature in signatures:
                raise ValueError("Ambiguous prepared symbol identity")
            symbols[symbol.local_key] = (parsed.file_path, symbol)
            signatures[signature] = symbol.local_key
        for draft in build_symbol_chunks(parsed):
            drafts[draft.symbol_key] = draft
    if len(prepared.chunks) != len(drafts) or len(prepared.embeddings) != len(drafts):
        raise ValueError("Chunk, symbol, or embedding count mismatch")
    chunks, vectors = {}, {}
    for chunk, embedding in zip(prepared.chunks, prepared.embeddings):
        key = chunk.symbol_key
        if key in chunks or key not in drafts or chunk.model_dump() != drafts[key].model_dump():
            raise ValueError("Prepared chunk does not match its parsed definition")
        try:
            values = tuple(float(value) for value in embedding)
            if len(values) != 384 or not all(isfinite(value) for value in values):
                raise ValueError("Invalid vector")
            if sum(value * value for value in values) <= 0:
                raise ValueError("Zero vector")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid embedding") from exc
        chunks[key], vectors[key] = chunk, values
    edges, skipped = set(), 0
    for edge in prepared.analysis.edges:
        source, target = edge.source.symbol_key, edge.target.symbol_key
        if source is None or target is None:
            skipped += 1
            continue
        if source not in symbols or target not in symbols:
            raise ValueError("Resolved edge references an unknown symbol")
        kind = edge.kind
        if not isinstance(kind, str) or not kind or len(kind) > 50:
            raise ValueError("Invalid edge kind")
        edges.add((source, target, kind))
    for key, (_, symbol) in symbols.items():
        if symbol.parent_key is not None:
            if symbol.parent_key not in symbols:
                raise ValueError("Unknown parent symbol")
            edges.add((symbol.parent_key, key, "CONTAINS"))
    return files, symbols, signatures, chunks, vectors, edges, skipped


def _verify_replay(session, repo_id, snapshot, files, symbols, signatures, chunks, vectors, expected_edges):
    stored_files = session.scalars(select(File).where(File.repository_id == repo_id)).all()
    if ({file.path for file in stored_files} != set(files)
            or any(file.snapshot_id != snapshot.id or file.language != "python" for file in stored_files)):
        raise PublicationConflictError("Stored files do not match this snapshot")
    rows = session.execute(select(Symbol, File.path).join(File, Symbol.file_id == File.id)
                           .where(File.repository_id == repo_id)).all()
    key_by_id = {}
    for symbol, path in rows:
        key = signatures.get(_signature(path, symbol))
        if key is None or key in key_by_id.values():
            raise PublicationConflictError("Stored symbols differ from the prepared index")
        key_by_id[symbol.id] = key
    if set(key_by_id.values()) != set(symbols):
        raise PublicationConflictError("Stored symbol coverage differs")
    stored_chunks = session.scalars(select(Chunk).where(Chunk.repo_id == repo_id)).all()
    seen = set()
    for chunk in stored_chunks:
        key = key_by_id.get(chunk.symbol_id)
        if key is None or key in seen or chunk.text != chunks[key].text or chunk.embedding is None:
            raise PublicationConflictError("Stored chunks differ from the prepared index")
        vector = tuple(float(value) for value in chunk.embedding)
        if len(vector) != 384 or any(not isfinite(x) or abs(x-y) > 1e-6
                                     for x, y in zip(vector, vectors[key])):
            raise PublicationConflictError("Stored embeddings differ from the prepared index")
        if chunk.search_vector is None:
            raise PublicationConflictError("Stored lexical index is missing")
        seen.add(key)
    if seen != set(chunks):
        raise PublicationConflictError("Stored chunk coverage differs")
    ids = list(key_by_id)
    stored_edges = session.scalars(select(Edge).where(
        Edge.source_symbol_id.in_(ids) | Edge.target_symbol_id.in_(ids))).all()
    actual_edges = set()
    for edge in stored_edges:
        if edge.source_symbol_id not in key_by_id or edge.target_symbol_id not in key_by_id:
            raise PublicationConflictError("Cross-repository edge prevents exact replay")
        actual_edges.add((key_by_id[edge.source_symbol_id], key_by_id[edge.target_symbol_id], edge.kind))
    if actual_edges != expected_edges or len(stored_edges) != len(expected_edges):
        raise PublicationConflictError("Stored graph differs from the prepared index")


def publish_prepared_index(job: ClaimedJob, prepared: PreparedPythonIndex, *,
                           commit_sha: str, session_factory=None) -> PublishedIndex:
    """Own a short transaction; publish and finish the leased job atomically.

    commit_sha must be obtained from the exact private clone used to prepare
    this bundle. This function does not independently prove Git provenance.
    Index versions identify configuration; change them when indexing policy or
    the embedding model/configuration changes. Historical replacement is not
    supported. Source/target module-only graph edges cannot fit this schema and
    are counted as skipped. Endpoint/test detection is NOT added by this function.
    """
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_sha):
        raise ValueError("commit_sha must be a full lowercase Git object ID")
    files, symbols, signatures, chunks, vectors, edges, skipped = _validate(prepared)
    if session_factory is None:
        from reposcope.db import SessionLocal
        session_factory = SessionLocal
    with session_factory.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        session.execute(text("SET LOCAL statement_timeout = '60s'"))
        repository = session.scalar(select(Repository).where(Repository.id == job.repository_id).with_for_update())
        if repository is None:
            raise PublicationConflictError("Repository no longer exists")
        # Hold ownership through publication. Heartbeats may wait on this row;
        # the final time/token check rolls everything back if the lease expires.
        owned = session.execute(text("""
            SELECT id FROM ingestion_jobs
            WHERE id = :id AND repository_id = :repo_id AND status = 'running'
              AND lease_token = :token AND leased_until > clock_timestamp()
            FOR UPDATE
        """), {"id": job.id, "repo_id": job.repository_id,
                 "token": job.lease_token}).scalar_one_or_none()
        if owned is None:
            raise LeaseLostError(f"Job {job.id} has no matching active lease")
        snapshot = session.scalar(select(RepositorySnapshot).where(
            RepositorySnapshot.repository_id == job.repository_id,
            RepositorySnapshot.commit_sha == commit_sha,
            RepositorySnapshot.index_version == prepared.index_version))
        if snapshot is not None and snapshot.status == "ready":
            _verify_replay(session, job.repository_id, snapshot, files, symbols,
                           signatures, chunks, vectors, edges)
            reused = True
        else:
            existing_files = session.scalar(select(func.count()).select_from(File)
                                            .where(File.repository_id == job.repository_id))
            existing_chunks = session.scalar(select(func.count()).select_from(Chunk)
                                             .where(Chunk.repo_id == job.repository_id))
            other_ready = session.scalar(select(RepositorySnapshot.id).where(
                RepositorySnapshot.repository_id == job.repository_id,
                RepositorySnapshot.status == "ready").limit(1))
            if existing_files or existing_chunks or other_ready is not None:
                raise PublicationConflictError(
                    "Repository already has indexed data; safe replacement is not implemented")
            if snapshot is None:
                snapshot = RepositorySnapshot(repository_id=job.repository_id,
                    commit_sha=commit_sha, index_version=prepared.index_version, status="indexing")
                session.add(snapshot)
                session.flush()
            else:
                snapshot.status = "indexing"
                snapshot.error_message = None
            file_ids, symbol_ids = {}, {}
            for path in sorted(files):
                file = File(repository_id=job.repository_id, snapshot_id=snapshot.id,
                            path=path, language="python")
                session.add(file)
                session.flush()
                file_ids[path] = file.id
            for key, (path, symbol) in symbols.items():
                record = Symbol(file_id=file_ids[path], name=symbol.name,
                    qualname=symbol.qualname, kind=symbol.kind,
                    start_line=symbol.start_line, end_line=symbol.end_line)
                session.add(record)
                session.flush()
                symbol_ids[key] = record.id
            session.add_all([Chunk(symbol_id=symbol_ids[key], repo_id=job.repository_id,
                text=chunk.text, embedding=list(vectors[key])) for key, chunk in chunks.items()])
            session.add_all([Edge(source_symbol_id=symbol_ids[source],
                target_symbol_id=symbol_ids[target], kind=kind, confidence=None)
                for source, target, kind in sorted(edges)])
            session.flush()
            missing_lexical = session.scalar(select(func.count()).select_from(Chunk).where(
                Chunk.repo_id == job.repository_id, Chunk.search_vector.is_(None)))
            if missing_lexical:
                raise PublicationConflictError("Lexical trigger did not populate chunk vectors")
            snapshot.status = "ready"
            snapshot.error_message = None
            snapshot.indexed_at = func.clock_timestamp()
            session.flush()
            reused = False
        snapshot_id = snapshot.id
        # Last write checks the database clock. Failure rolls back ALL index writes.
        mark_job_succeeded(session, job)
    return PublishedIndex(snapshot_id=snapshot_id, file_count=len(files),
        symbol_count=len(symbols), chunk_count=len(chunks), edge_count=len(edges),
        skipped_non_symbol_edges=skipped, reused=reused)
