"""Build and persist one fresh repository code graph; caller owns commit."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import select

from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import ResolutionResult
from reposcope.graph.store import GraphStore
from reposcope.models.file import File
from reposcope.models.repository import Repository
from reposcope.models.symbol import Symbol
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.resolver_pipeline import analyze_python_files


@dataclass(frozen=True)
class NodeDraft:
    key: str
    path: str
    name: str
    qualname: str
    kind: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class EdgeDraft:
    source_key: str
    target_key: str
    kind: str
    confidence: float
    reference_keys: tuple[str, ...]


@dataclass(frozen=True)
class GraphPlan:
    paths: tuple[str, ...]
    nodes: tuple[NodeDraft, ...]
    edges: tuple[EdgeDraft, ...]
    results: tuple[ResolutionResult, ...]

    @property
    def gaps(self):
        return tuple(r for r in self.results if r.status in {"AMBIGUOUS", "UNRESOLVED"})


@dataclass(frozen=True)
class PersistedGraph:
    repository_id: int
    file_ids: Mapping[str, int]
    node_ids: Mapping[str, int]
    edge_count: int
    plan: GraphPlan


def target_key(target):
    return target.module_key if target.target_kind == "module" else target.symbol_key


def build_graph_plan(parsed_files: list[ParsedFile], *, source_roots=(".",)):
    # Index construction owns/revalidates parser records before any DB mutation.
    repo = build_repo_index(parsed_files, source_roots=source_roots)
    analysis = analyze_python_files(list(repo.files_by_path.values()), source_roots=source_roots)
    nodes = []
    for path, parsed in repo.files_by_path.items():
        module = repo.module_for_file(path)
        # Synthetic module node: distinct identity, so module-level calls/imports
        # are persisted without inventing a function owner or dropping the edge.
        nodes.append(NodeDraft(module.module_key, path, module.module_name or path,
                               "__module__", "module", 1,
                               max(1, len(parsed.source_text.splitlines()))))
        for symbol in parsed.symbols:
            nodes.append(NodeDraft(symbol.local_key, path, symbol.name, symbol.qualname,
                                   symbol.kind, symbol.start_line, symbol.end_line))
    nodes.sort(key=lambda n: (n.path, n.start_line, n.kind, n.key))
    node_keys = {n.key for n in nodes}
    merged = {}
    for edge in analysis.edges:
        source, target = target_key(edge.source), target_key(edge.target)
        if source not in node_keys or target not in node_keys:
            raise ValueError("Resolver edge references a node outside the validated graph")
        identity = (source, target, edge.kind)
        confidence, refs = merged.setdefault(identity, (edge.confidence, set()))
        refs.add(edge.reference_key)
        merged[identity] = (max(confidence, edge.confidence), refs)
    edges = tuple(EdgeDraft(*identity, confidence, tuple(sorted(refs)))
                  for identity, (confidence, refs) in sorted(merged.items()))
    return GraphPlan(tuple(repo.files_by_path), tuple(nodes), edges, analysis.results)


def persist_graph_plan(session, repository_id: int, plan: GraphPlan):
    """Fresh graph only. Savepoint, no commits, no destructive replacement.

    Caller must commit/rollback its outer transaction. This is not an incremental
    indexer. A repository with files is rejected to protect chunks and snapshots.
    """
    keys = [node.key for node in plan.nodes]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate graph node keys")
    path_set = set(plan.paths)
    if len(path_set) != len(plan.paths) or any(n.path not in path_set for n in plan.nodes):
        raise ValueError("Invalid graph file inventory")
    node_set = set(keys)
    if any(e.source_key not in node_set or e.target_key not in node_set for e in plan.edges):
        raise ValueError("Dangling graph edge")
    with session.begin_nested():
        repository = session.scalars(select(Repository).where(
            Repository.id == repository_id).with_for_update()).first()
        if repository is None:
            raise ValueError("Repository does not exist")
        if session.scalars(select(File.id).where(
            File.repository_id == repository_id).limit(1)).first() is not None:
            raise ValueError("Repository already has files; automatic replacement is disabled")
        file_objects = {path: File(repository_id=repository_id, path=path, language="python")
                        for path in plan.paths}
        session.add_all(file_objects.values())
        session.flush()
        store = GraphStore(session=session)
        stored = store.bulk_insert_symbols([
            dict(file_id=file_objects[n.path].id, name=n.name, qualname=n.qualname,
                 kind=n.kind, start_line=n.start_line, end_line=n.end_line)
            for n in plan.nodes
        ])
        node_ids = {n.key: symbol.id for n, symbol in zip(plan.nodes, stored)}
        inserted = store.bulk_insert_edges([
            dict(source_symbol_id=node_ids[e.source_key], target_symbol_id=node_ids[e.target_key],
                 kind=e.kind, confidence=e.confidence) for e in plan.edges
        ])
        result = PersistedGraph(repository_id,
                                MappingProxyType({p: f.id for p, f in file_objects.items()}),
                                MappingProxyType(node_ids), len(inserted), plan)
    return result


def persist_python_graph(session, repository_id, parsed_files, *, source_roots=(".",)):
    return persist_graph_plan(session, repository_id,
                              build_graph_plan(parsed_files, source_roots=source_roots))


def canonical_graph(session, repository_id):
    """ID-independent graph for golden comparisons, including qualified names."""
    store = GraphStore(session=session)
    files = list(session.scalars(select(File).where(File.repository_id == repository_id)).all())
    paths = {f.id: f.path for f in files}
    symbols = store.get_symbols_by_repository_id(repository_id)
    labels = {s.id: (paths[s.file_id], s.kind, s.qualname, s.start_line, s.end_line)
              for s in symbols}
    if any(label[2] is None for label in labels.values()):
        raise ValueError("Canonical graph requires qualified names")
    if len(set(labels.values())) != len(labels):
        raise ValueError("Stored node labels are not unique; identity is ambiguous")
    edges = store.get_edges_for_repository(repository_id)
    return {
        "files": sorted(paths.values()),
        "nodes": [list(label) for label in sorted(labels.values())],
        "edges": sorted([[list(labels[e.source_symbol_id]), list(labels[e.target_symbol_id]),
                           e.kind, e.confidence] for e in edges]),
    }


def resolution_report(plan):
    """Explicit report; persist this separately if durable gap/provenance is needed."""
    return {"counts": {status: sum(r.status == status for r in plan.results)
                       for status in ("EXACT", "INFERRED", "AMBIGUOUS", "UNRESOLVED")},
            "results": [r.model_dump(mode="json") for r in plan.results],
            "edge_evidence": [{"source_key": e.source_key, "target_key": e.target_key,
                               "kind": e.kind, "confidence": e.confidence,
                               "reference_keys": list(e.reference_keys)} for e in plan.edges]}
