"""Incremental Python graph service. No commits; caller retains state after commit.

A complete source inventory detects deletion. Only changed bytes reach the
Python symbol parser; only reverse-dependent files have references re-resolved.
Global lookup indices and derived relationships are refreshed for correctness.
State is an explicit in-memory baseline, not a durable indexing job checkpoint.
Snapshot-owned file graphs are deliberately rejected.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import delete, or_, select

from reposcope.contracts.parsing import ParsedFile
from reposcope.graph.builder import (
    GraphPlan, PersistedGraph, build_graph_plan, persist_graph_plan,
)
from reposcope.models.chunk import Chunk
from reposcope.models.edge import Edge
from reposcope.models.file import File
from reposcope.models.repository import Repository
from reposcope.models.symbol import Symbol
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.resolver_pipeline import analyze_python_files


@dataclass(frozen=True)
class IncrementalState:
    parsed_files: Mapping[str, ParsedFile]
    graph: PersistedGraph
    source_roots: tuple[str, ...]


@dataclass(frozen=True)
class IncrementalUpdate:
    state: IncrementalState
    added: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]
    resolved_paths: tuple[str, ...]
    invalidated_chunk_ids: tuple[int, ...] = ()

    @property
    def changed_paths(self):
        return tuple(sorted(set(self.added + self.modified + self.deleted)))


def _inventory(sources):
    if not isinstance(sources, Mapping):
        raise TypeError("sources must map repository-relative Python paths to bytes")
    copied = dict(sources)
    for path, content in copied.items():
        if (not isinstance(path, str) or not path or "\\" in path
                or ":" in path or path.startswith("/")
                or any(part in {"", ".", ".."} for part in path.split("/"))
                or PurePosixPath(path).suffix != ".py"):
            raise ValueError("Expected repository-relative POSIX .py paths")
        if not isinstance(content, bytes):
            raise TypeError("Source values must be bytes")
    return dict(sorted(copied.items()))


def _state(parsed, graph, roots):
    return IncrementalState(
        MappingProxyType({p: f.model_copy(deep=True) for p, f in parsed.items()}),
        graph, tuple(roots),
    )


def initialize_incremental_graph(session, repository_id, sources, *, source_roots=(".",)):
    """Index a fresh repository. Keep returned state only after outer commit."""
    inventory = _inventory(sources)
    parsed = {p: parse_python(b, file_path=p) for p, b in inventory.items()}
    roots = tuple(source_roots)
    graph = persist_graph_plan(session, repository_id, build_graph_plan(
        list(parsed.values()), source_roots=roots,
    ))
    return _state(parsed, graph, roots)


def attach_incremental_state(parsed_files, graph, *, source_roots=(".",)):
    """Attach to a freshly persisted Day 8 graph using its original parser records.

    Never reconstruct source content from symbol rows. Database consistency is
    checked when updating; source roots must match those used for the graph.
    """
    repo = build_repo_index(list(parsed_files), source_roots=source_roots)
    expected = build_graph_plan(list(repo.files_by_path.values()), source_roots=source_roots)
    if expected != graph.plan:
        raise ValueError("Parser baseline does not match persisted graph plan")
    return _state(repo.files_by_path, graph, repo.source_roots)


def _dependencies(parsed, roots):
    repo = build_repo_index(list(parsed.values()), source_roots=roots)
    dependencies = {p: set() for p in parsed}
    for path, record in parsed.items():
        module = repo.module_for_file(path)
        name = module.module_name or ""
        package = name if PurePosixPath(path).name == "__init__.py" else name.rpartition(".")[0]
        requests = set()
        for node in ast.walk(ast.parse(record.source_text, filename=path)):
            if isinstance(node, ast.Import):
                requests.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    components = package.split(".") if package else []
                    up = node.level - 1
                    if up >= len(components):
                        continue
                    prefix = ".".join(components[:len(components) - up])
                    base = ".".join(x for x in (prefix, node.module) if x)
                else:
                    base = node.module or ""
                if base:
                    requests.add(base)
                    requests.update(base + "." + a.name for a in node.names if a.name != "*")
        # Include all candidates and package prefixes, even for unresolved imports.
        for candidate, modules in repo.modules_by_name.items():
            if any(candidate == request or candidate.startswith(request + ".")
                   or request.startswith(candidate + ".") for request in requests):
                dependencies[path].update(m.file_path for m in modules)
    return dependencies


def _affected(before, after, roots, changed, old_results):
    reverse = {}
    for parsed in (before, after):
        for source, targets in _dependencies(parsed, roots).items():
            for target in targets:
                reverse.setdefault(target, set()).add(source)
    for result in old_results:
        for target in result.targets:
            reverse.setdefault(target.file_path, set()).add(result.reference.file_path)
    affected = set(changed)
    pending = list(affected)
    while pending:
        for dependent in reverse.get(pending.pop(), ()):
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    return affected & set(after)


def _symbol_values(node):
    return dict(name=node.name, qualname=node.qualname, kind=node.kind,
                start_line=node.start_line, end_line=node.end_line)


def _validated_database(session, state):
    graph = state.graph
    repository = session.scalar(select(Repository).where(
        Repository.id == graph.repository_id).with_for_update())
    if repository is None:
        raise ValueError("Repository does not exist")
    files = {f.path: f for f in session.scalars(select(File).where(
        File.repository_id == graph.repository_id)).all()}
    if {p: f.id for p, f in files.items()} != dict(graph.file_ids):
        raise ValueError("Stale baseline: file inventory changed")
    if any(f.snapshot_id is not None for f in files.values()):
        raise ValueError("Snapshot-owned graphs require a snapshot-aware update")
    symbols = list(session.scalars(select(Symbol).where(
        Symbol.file_id.in_([f.id for f in files.values()]))).all())
    by_id = {s.id: s for s in symbols}
    if set(by_id) != set(graph.node_ids.values()):
        raise ValueError("Stale baseline: symbols changed")
    for node in graph.plan.nodes:
        symbol = by_id.get(graph.node_ids.get(node.key))
        if symbol is None or symbol.file_id != files[node.path].id or any(
                getattr(symbol, field) != value for field, value in _symbol_values(node).items()):
            raise ValueError("Stale baseline: symbol metadata changed")
    ids = list(by_id)
    edges = list(session.scalars(select(Edge).where(or_(
        Edge.source_symbol_id.in_(ids), Edge.target_symbol_id.in_(ids)))).all())
    if any(e.source_symbol_id not in by_id or e.target_symbol_id not in by_id for e in edges):
        raise ValueError("Cross-repository edges are not supported")
    expected = {(graph.node_ids[e.source_key], graph.node_ids[e.target_key], e.kind): e.confidence
                for e in graph.plan.edges}
    actual = {(e.source_symbol_id, e.target_symbol_id, e.kind): e.confidence for e in edges}
    if actual != expected:
        raise ValueError("Stale baseline: edges changed")
    return files, by_id, edges


def update_incremental_graph(session, state, sources):
    """Apply a COMPLETE source inventory, including deletion, inside a savepoint.

    The old state is never mutated. Adopt update.state only after committing the
    outer transaction; discard it on rollback. No watcher or chunk regeneration
    is implicit. invalidated_chunk_ids reports retrieval rows removed by update.
    """
    inventory = _inventory(sources)
    before = state.parsed_files
    if set(before) != set(state.graph.plan.paths):
        raise ValueError("Invalid parser baseline inventory")
    added = set(inventory) - set(before)
    deleted = set(before) - set(inventory)
    modified = {p for p in set(inventory) & set(before)
                if hashlib.sha256(inventory[p]).hexdigest() != before[p].source_sha256}
    dirty = added | modified | deleted
    parsed = {p: f for p, f in before.items() if p not in deleted}
    for path in sorted(added | modified):
        parsed[path] = parse_python(inventory[path], file_path=path)
    parsed = dict(sorted(parsed.items()))
    affected = _affected(before, parsed, state.source_roots, dirty, state.graph.plan.results) if dirty else set()
    if dirty:
        analysis = analyze_python_files(
            list(parsed.values()), source_roots=state.source_roots,
            reference_paths=affected, cached_results=state.graph.plan.results,
        )
        plan = build_graph_plan(list(parsed.values()), source_roots=state.source_roots, _analysis=analysis)
    else:
        plan = state.graph.plan
    with session.begin_nested():
        files, symbols, existing_edges = _validated_database(session, state)
        if not dirty:
            return IncrementalUpdate(state, (), (), (), ())
        old_nodes = {n.key: n for n in state.graph.plan.nodes}
        new_nodes = {n.key: n for n in plan.nodes}
        for key, node in old_nodes.items():
            if node.path not in dirty and new_nodes.get(key) != node:
                raise ValueError("Unexpected node change outside dirty files")
        removed_ids = {state.graph.node_ids[k] for k, n in old_nodes.items() if n.path in dirty}
        chunk_ids = tuple(sorted(session.scalars(select(Chunk.id).where(
            Chunk.symbol_id.in_(removed_ids))).all()))
        for edge in existing_edges:
            if edge.source_symbol_id in removed_ids or edge.target_symbol_id in removed_ids:
                session.delete(edge)
        session.flush()
        session.execute(delete(Chunk).where(Chunk.symbol_id.in_(removed_ids)))
        for symbol_id in removed_ids:
            session.delete(symbols[symbol_id])
        session.flush()
        for path in sorted(deleted):
            session.delete(files.pop(path))
        session.flush()
        for path in sorted(added):
            files[path] = File(repository_id=state.graph.repository_id, path=path, language="python")
            session.add(files[path])
        session.flush()
        node_ids = {k: v for k, v in state.graph.node_ids.items() if old_nodes[k].path not in dirty}
        for node in plan.nodes:
            if node.path in dirty:
                symbol = Symbol(file_id=files[node.path].id, **_symbol_values(node))
                session.add(symbol)
                session.flush()
                node_ids[node.key] = symbol.id
        desired = {(node_ids[e.source_key], node_ids[e.target_key], e.kind): e.confidence for e in plan.edges}
        kept = {(e.source_symbol_id, e.target_symbol_id, e.kind): e for e in existing_edges
                if e.source_symbol_id not in removed_ids and e.target_symbol_id not in removed_ids}
        for identity, edge in kept.items():
            if identity not in desired:
                session.delete(edge)
            elif edge.confidence != desired[identity]:
                edge.confidence = desired[identity]
        session.flush()
        for identity, confidence in desired.items():
            if identity not in kept:
                session.add(Edge(source_symbol_id=identity[0], target_symbol_id=identity[1],
                                 kind=identity[2], confidence=confidence))
        session.flush()
        graph = PersistedGraph(
            state.graph.repository_id, MappingProxyType({p: f.id for p, f in files.items()}),
            MappingProxyType(node_ids), len(desired), plan,
        )
        next_state = _state(parsed, graph, state.source_roots)
    return IncrementalUpdate(next_state, tuple(sorted(added)), tuple(sorted(modified)),
                             tuple(sorted(deleted)), tuple(sorted(affected)), chunk_ids)
