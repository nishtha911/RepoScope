"""Read-only Day 7 -> Evidence Pack adapter. No LLM call or implicit commit.

Use a clean REPEATABLE READ transaction during concurrent indexing. Snapshot
identity is checked, not invented. Legacy files with NULL snapshot_id become
gaps until indexed with genuine snapshot provenance; never relabel old data.
"""
import ast
from dataclasses import asdict
import json
import textwrap

from reposcope.rag.evidence_pack import (
    ContextSymbol, EvidenceCandidate, EvidencePath, _positive, build_evidence_pack,
)

SOURCE_SEPARATOR = "\n\n--- SOURCE ---\n"


def _snapshot(session, repository_id, snapshot_id):
    from sqlalchemy import text
    return session.execute(text("""
        SELECT id, repository_id, commit_sha, status FROM repository_snapshots
        WHERE id=:snapshot_id AND repository_id=:repository_id
    """),dict(snapshot_id=snapshot_id,repository_id=repository_id)).mappings().first()


def _symbols(session, ids):
    if not ids:
        return []
    from sqlalchemy import bindparam, text
    query = text("""
        SELECT s.id AS symbol_id, s.name, s.qualname, s.kind,
               s.start_line, s.end_line, f.id AS file_id,
               f.path AS file_path, f.repository_id, f.snapshot_id
        FROM symbols s JOIN files f ON f.id=s.file_id
        WHERE s.id IN :ids ORDER BY s.id
    """).bindparams(bindparam("ids",expanding=True))
    return list(session.execute(query,dict(ids=sorted(ids))).mappings())


def _chunks(session, ids):
    if not ids:
        return []
    from sqlalchemy import bindparam, text
    query = text("""
        SELECT id AS chunk_id, symbol_id, repo_id, text FROM chunks
        WHERE id IN :ids ORDER BY id
    """).bindparams(bindparam("ids",expanding=True))
    return list(session.execute(query,dict(ids=sorted(ids))).mappings())


def _source_parts(raw, metadata):
    """Align complete chunk body to persisted definition; do not guess offsets."""
    signature, warnings = None, []
    if SOURCE_SEPARATOR in raw:
        header, _, body = raw.partition(SOURCE_SEPARATOR)
        header = json.loads(header)
        if not isinstance(header,dict):
            raise ValueError("Chunk header must be an object")
        for field in ("file_path","qualname","kind"):
            if header.get(field) != metadata[field]:
                raise ValueError("Chunk header differs from stored symbol metadata")
        signature = header.get("signature")
        if signature is not None and (not isinstance(signature,str) or not signature.strip()):
            raise ValueError("Invalid stored signature")
    else:
        body = raw
        warnings.append("Stored chunk has no structured signature header")
    if not body.strip() or len(body) > 2_000_000:
        raise ValueError("Source body is blank or exceeds the parsing safety limit")
    parsed = ast.parse(textwrap.dedent(body))
    if len(parsed.body) != 1:
        raise ValueError("Chunk is not one complete definition")
    node = parsed.body[0]
    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) or node.name != metadata["name"]:
        raise ValueError("Chunk definition does not match stored symbol")
    if (metadata["kind"] == "class") != isinstance(node,ast.ClassDef):
        raise ValueError("Chunk definition kind does not match stored symbol")
    offset = metadata["start_line"] - node.lineno
    if node.end_lineno is None or offset + node.end_lineno != metadata["end_line"]:
        raise ValueError("Chunk cannot be aligned with the stored definition range")
    count = body.count("\n") + (0 if body.endswith("\n") else 1)
    start, end = offset + 1, offset + count
    if start < 1 or end < start:
        raise ValueError("Invalid aligned content range")
    if metadata["kind"] != "class" and signature is None:
        warnings.append("Callable signature is unavailable; body retained without inventing a signature")
    return body, signature, start, end, warnings


def assemble_evidence_pack(
    session, retrieval, *, snapshot_id: int,
    max_entries: int = 40, max_source_chars: int = 48_000,
):
    """Hydrate metadata for an existing ExpandedRetrievalResult.

    No lexical/vector search is rerun. Existing chunk text is rechecked to catch
    concurrent/stale retrieval. IDs are scoped by the caller-specified snapshot.
    Path metadata is trusted only after all its symbols are scope-checked.
    """
    expansion = retrieval.expansion
    repository_id = expansion.repository_id
    _positive(repository_id,"repository_id")
    _positive(snapshot_id,"snapshot_id")
    snapshot = _snapshot(session,repository_id,snapshot_id)
    if snapshot is None or snapshot["status"] != "ready":
        raise ValueError("A ready snapshot belonging to the repository is required")
    seeds = {seed.symbol_id:seed for seed in expansion.seeds}
    extras = {node.symbol_id:node for node in expansion.symbols}
    if set(seeds) & set(extras):
        raise ValueError("Seeds and expanded symbols overlap")
    paths = {node.symbol_id:tuple(EvidencePath(**asdict(path)) for path in node.paths)
             for node in expansion.symbols}
    referenced = set(seeds) | set(extras)
    for node_paths in paths.values():
        for path in node_paths:
            if path.seed_symbol_id not in seeds:
                raise ValueError("Expansion path refers to an unselected seed")
            referenced.update(path.symbol_ids)
    metadata = {row["symbol_id"]:row for row in _symbols(session,referenced)}
    gaps = set(expansion.gaps)
    for row in metadata.values():
        if row["repository_id"] != repository_id:
            raise ValueError("Graph context contains a foreign repository symbol")
        if row["snapshot_id"] is not None and row["snapshot_id"] != snapshot_id:
            raise ValueError("Graph context contains a different snapshot")
    for node in expansion.symbols:
        row = metadata.get(node.symbol_id)
        if row and (node.name,node.kind,node.file_path) != (row["name"],row["kind"],row["file_path"]):
            raise ValueError("Graph metadata changed; rerun retrieval")
    for symbol_id in sorted(referenced):
        row = metadata.get(symbol_id)
        if row is None or row["snapshot_id"] is None:
            gaps.add(f"Symbol {symbol_id} has no verified snapshot metadata; source omitted")
    context = {}
    for chunk in retrieval.context_chunks:
        if chunk.repo_id != repository_id or chunk.symbol_id not in set(seeds) | set(extras):
            raise ValueError("Context chunk is outside selected repository/symbol scope")
        if chunk.is_seed != (chunk.symbol_id in seeds):
            raise ValueError("Context chunk origin differs from expansion")
        if chunk.is_seed and chunk.chunk_id != seeds[chunk.symbol_id].chunk_id:
            raise ValueError("Seed chunk identity mismatch")
        if chunk.chunk_id in context and context[chunk.chunk_id] != chunk:
            raise ValueError("Conflicting duplicate context chunk")
        context[chunk.chunk_id] = chunk
    stored = {row["chunk_id"]:row for row in _chunks(session,set(context))}
    candidates, represented = [], set()
    for order,chunk in enumerate(context.values()):
        row = metadata.get(chunk.symbol_id)
        if row is None or row["snapshot_id"] != snapshot_id:
            continue
        record = stored.get(chunk.chunk_id)
        if record is None:
            gaps.add(f"Chunk {chunk.chunk_id} is no longer stored; source omitted")
            continue
        if (record["symbol_id"],record["repo_id"],record["text"]) != (chunk.symbol_id,repository_id,chunk.text):
            raise ValueError("Stored chunk changed or has conflicting ownership; rerun retrieval")
        node_paths = paths.get(chunk.symbol_id,())
        if any(any(node not in metadata or metadata[node]["snapshot_id"] != snapshot_id
                   for node in path.symbol_ids) for path in node_paths):
            gaps.add(f"Chunk {chunk.chunk_id} has an unverified path; source omitted")
            continue
        try:
            body,signature,start,end,warnings = _source_parts(chunk.text,row)
        except (ValueError,SyntaxError,TypeError,RecursionError) as exc:
            gaps.add(f"Chunk {chunk.chunk_id} has unverifiable source formatting/range; source omitted")
            continue
        gaps.update(f"Chunk {chunk.chunk_id}: {warning}" for warning in warnings)
        candidates.append(EvidenceCandidate(
            repository_id=repository_id,snapshot_id=snapshot_id,file_id=row["file_id"],
            file_path=row["file_path"],symbol_id=chunk.symbol_id,chunk_id=chunk.chunk_id,
            start_line=start,end_line=end,text=body,name=row["name"],qualname=row["qualname"],
            kind=row["kind"],signature=signature,origin="seed" if chunk.is_seed else "expanded",
            order=order,fused_score=seeds[chunk.symbol_id].fused_score if chunk.is_seed else None,
            paths=node_paths))
        represented.add(chunk.symbol_id)
    for symbol_id in sorted((set(seeds) | set(extras)) - represented):
        gaps.add(f"Symbol {symbol_id} has no citable source in this pack; metadata/path alone is not code evidence")
    if expansion.truncated != bool(expansion.truncation_reasons):
        raise ValueError("Expansion truncation metadata is inconsistent")
    context_symbols = tuple(ContextSymbol(
        symbol_id=symbol_id,file_id=metadata[symbol_id]["file_id"],snapshot_id=snapshot_id,
        file_path=metadata[symbol_id]["file_path"],name=metadata[symbol_id]["name"],
        qualname=metadata[symbol_id]["qualname"],kind=metadata[symbol_id]["kind"],
        is_seed=symbol_id in seeds,paths=tuple(
            path for path in paths.get(symbol_id,())
            if all(node in metadata and metadata[node]["snapshot_id"] == snapshot_id
                   for node in path.symbol_ids)))
        for symbol_id in sorted(set(seeds) | set(extras))
        if symbol_id in metadata and metadata[symbol_id]["snapshot_id"] == snapshot_id)
    return build_evidence_pack(candidates,context_symbols=context_symbols,repository_id=repository_id,snapshot_id=snapshot_id,
                               commit_sha=snapshot["commit_sha"],gaps=tuple(gaps),
                               truncation_reasons=expansion.truncation_reasons,
                               max_entries=max_entries,max_source_chars=max_source_chars)
