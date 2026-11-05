"""Build and persist one fresh repository code graph; caller owns commit."""

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import select

from reposcope.contracts.detection import DetectionResult
from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import ResolutionResult
from reposcope.contracts.test_linking import TestLinkingResult
from reposcope.graph.store import GraphStore
from reposcope.models.file import File
from reposcope.models.repository import Repository
from reposcope.parsing.detectors import (
    derive_model_uses,
    detect_routes,
)
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.repository_models import (
    detect_repository_models,
)
from reposcope.parsing.resolver_pipeline import analyze_python_files
from reposcope.parsing.test_detector import detect_test_links


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
    detection: DetectionResult = field(
        default_factory=DetectionResult
    )
    test_linking: TestLinkingResult = field(
        default_factory=TestLinkingResult
    )

    @property
    def gaps(self):
        """Resolver gaps; detector gaps remain separately available."""
        return tuple(
            result
            for result in self.results
            if result.status in {"AMBIGUOUS", "UNRESOLVED"}
        )


@dataclass(frozen=True)
class PersistedGraph:
    repository_id: int
    file_ids: Mapping[str, int]
    node_ids: Mapping[str, int]
    edge_count: int
    plan: GraphPlan


def target_key(target):
    return (
        target.module_key
        if target.target_kind == "module"
        else target.symbol_key
    )


def _derived_reference_key(edge):
    """Stable identity for one derived relationship's source evidence."""
    evidence = edge.evidence

    return json.dumps(
        [
            "derived",
            evidence.file_path,
            evidence.start_byte,
            evidence.end_byte,
            evidence.rule_id,
            edge.kind,
            edge.source_key,
            edge.target_key,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_graph_plan(
    parsed_files: list[ParsedFile],
    *,
    source_roots=(".",),
    _analysis=None,
):
    # Revalidate parser records before any database mutation.
    repo = build_repo_index(
        parsed_files,
        source_roots=source_roots,
    )
    analysis = _analysis if _analysis is not None else analyze_python_files(
        list(repo.files_by_path.values()),
        source_roots=source_roots,
    )

    # Use resolver-produced edges only. Endpoint dispatch and other
    # derived relationships must not become test-link call paths.
    test_linking = detect_test_links(
        list(repo.files_by_path.values()),
        analysis.edges,
    )

    nodes = []
    endpoints = []
    models = []
    derived_edges = []
    detection_gaps = []

    for path, parsed in repo.files_by_path.items():
        module = repo.module_for_file(path)

        # Module-level references need a real graph owner.
        nodes.append(
            NodeDraft(
                key=module.module_key,
                path=path,
                name=module.module_name or path,
                qualname="__module__",
                kind="module",
                start_line=1,
                end_line=max(
                    1,
                    len(parsed.source_text.splitlines()),
                ),
            )
        )

        for symbol in parsed.symbols:
            nodes.append(
                NodeDraft(
                    key=symbol.local_key,
                    path=path,
                    name=symbol.name,
                    qualname=symbol.qualname,
                    kind=symbol.kind,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
            )

        routes = detect_routes(
            parsed,
            module_key=module.module_key,
        )

        endpoints.extend(routes.endpoints)
        derived_edges.extend(routes.edges)
        detection_gaps.extend(routes.gaps)

        for endpoint in routes.endpoints:
            nodes.append(
                NodeDraft(
                    key=endpoint.key,
                    path=path,
                    name=f"{endpoint.method} {endpoint.path}",
                    # Registration identity prevents collisions when the
                    # same method/path is declared more than once.
                    qualname=f"__endpoint__:{endpoint.key}",
                    kind="endpoint",
                    start_line=endpoint.evidence.start_line,
                    end_line=endpoint.evidence.end_line,
                )
            )

    # Repository-level classification consumes resolved base-class
    # references, allowing supported project bases to live in other files.
    model_detection = detect_repository_models(
        list(repo.files_by_path.values()),
        analysis.results,
    )

    models.extend(model_detection.models)
    detection_gaps.extend(model_detection.gaps)

    model_uses = derive_model_uses(
        analysis.results,
        models,
    )

    derived_edges.extend(model_uses.edges)
    detection_gaps.extend(model_uses.gaps)

    detection = DetectionResult(
        endpoints=tuple(endpoints),
        models=tuple(models),
        edges=tuple(derived_edges),
        gaps=tuple(detection_gaps),
    )

    nodes.sort(
        key=lambda node: (
            node.path,
            node.start_line,
            node.kind,
            node.key,
        )
    )

    node_keys = {node.key for node in nodes}

    if len(node_keys) != len(nodes):
        raise ValueError("Duplicate graph node keys")

    merged = {}

    def merge_edge(
        source,
        target,
        kind,
        confidence,
        reference_key,
    ):
        if source not in node_keys or target not in node_keys:
            raise ValueError(
                "Graph edge references a node outside the validated graph"
            )

        identity = (source, target, kind)
        previous_confidence, references = merged.setdefault(
            identity,
            (confidence, set()),
        )

        references.add(reference_key)

        merged[identity] = (
            max(previous_confidence, confidence),
            references,
        )

    for edge in analysis.edges:
        merge_edge(
            target_key(edge.source),
            target_key(edge.target),
            edge.kind,
            edge.confidence,
            edge.reference_key,
        )

    for edge in detection.edges:
        merge_edge(
            edge.source_key,
            edge.target_key,
            edge.kind,
            edge.confidence,
            _derived_reference_key(edge),
        )

    # Merge test associations by implementation -> test. Distinct call
    # paths retain distinct reference keys even when the stored edge is
    # shared. Complete structured evidence lives in plan.test_linking.
    for link in test_linking.links:
        reference_key = json.dumps(
            [
                "test_link",
                link.rule,
                link.test_key,
                link.implementation_key,
                list(link.call_path),
                list(link.reference_keys),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

        merge_edge(
            link.implementation_key,
            link.test_key,
            "TESTED_BY",
            link.confidence,
            reference_key,
        )

    edges = tuple(
        EdgeDraft(
            source_key=identity[0],
            target_key=identity[1],
            kind=identity[2],
            confidence=confidence,
            reference_keys=tuple(sorted(references)),
        )
        for identity, (confidence, references)
        in sorted(merged.items())
    )

    return GraphPlan(
        paths=tuple(repo.files_by_path),
        nodes=tuple(nodes),
        edges=edges,
        results=analysis.results,
        detection=detection,
        test_linking=test_linking,
    )


def persist_graph_plan(
    session,
    repository_id: int,
    plan: GraphPlan,
):
    """Fresh graph only. Savepoint, no commits, no destructive replacement.

    Caller must commit/rollback its outer transaction. This is not an
    incremental indexer. A repository with files is rejected to protect
    chunks and snapshots.
    """
    keys = [node.key for node in plan.nodes]

    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate graph node keys")

    path_set = set(plan.paths)

    if len(path_set) != len(plan.paths) or any(
        node.path not in path_set
        for node in plan.nodes
    ):
        raise ValueError("Invalid graph file inventory")

    node_set = set(keys)

    if any(
        edge.source_key not in node_set
        or edge.target_key not in node_set
        for edge in plan.edges
    ):
        raise ValueError("Dangling graph edge")

    with session.begin_nested():
        repository = session.scalars(
            select(Repository)
            .where(Repository.id == repository_id)
            .with_for_update()
        ).first()

        if repository is None:
            raise ValueError("Repository does not exist")

        existing_file = session.scalars(
            select(File.id)
            .where(File.repository_id == repository_id)
            .limit(1)
        ).first()

        if existing_file is not None:
            raise ValueError(
                "Repository already has files; "
                "automatic replacement is disabled"
            )

        file_objects = {
            path: File(
                repository_id=repository_id,
                path=path,
                language="python",
            )
            for path in plan.paths
        }

        session.add_all(file_objects.values())
        session.flush()

        store = GraphStore(session=session)

        stored = store.bulk_insert_symbols(
            [
                dict(
                    file_id=file_objects[node.path].id,
                    name=node.name,
                    qualname=node.qualname,
                    kind=node.kind,
                    start_line=node.start_line,
                    end_line=node.end_line,
                )
                for node in plan.nodes
            ]
        )

        node_ids = {
            node.key: symbol.id
            for node, symbol in zip(plan.nodes, stored)
        }

        inserted = store.bulk_insert_edges(
            [
                dict(
                    source_symbol_id=node_ids[edge.source_key],
                    target_symbol_id=node_ids[edge.target_key],
                    kind=edge.kind,
                    confidence=edge.confidence,
                )
                for edge in plan.edges
            ]
        )

        result = PersistedGraph(
            repository_id=repository_id,
            file_ids=MappingProxyType(
                {
                    path: file.id
                    for path, file in file_objects.items()
                }
            ),
            node_ids=MappingProxyType(node_ids),
            edge_count=len(inserted),
            plan=plan,
        )

    return result


def persist_python_graph(
    session,
    repository_id,
    parsed_files,
    *,
    source_roots=(".",),
):
    return persist_graph_plan(
        session,
        repository_id,
        build_graph_plan(
            parsed_files,
            source_roots=source_roots,
        ),
    )


def canonical_graph(session, repository_id):
    """ID-independent graph for golden comparisons."""
    store = GraphStore(session=session)

    files = list(
        session.scalars(
            select(File).where(
                File.repository_id == repository_id
            )
        ).all()
    )

    paths = {
        file.id: file.path
        for file in files
    }

    symbols = store.get_symbols_by_repository_id(repository_id)

    labels = {
        symbol.id: (
            paths[symbol.file_id],
            symbol.kind,
            symbol.qualname,
            symbol.start_line,
            symbol.end_line,
        )
        for symbol in symbols
    }

    if any(
        label[2] is None
        for label in labels.values()
    ):
        raise ValueError(
            "Canonical graph requires qualified names"
        )

    if len(set(labels.values())) != len(labels):
        raise ValueError(
            "Stored node labels are not unique; identity is ambiguous"
        )

    edges = store.get_edges_for_repository(repository_id)

    return {
        "files": sorted(paths.values()),
        "nodes": [
            list(label)
            for label in sorted(labels.values())
        ],
        "edges": sorted(
            [
                [
                    list(labels[edge.source_symbol_id]),
                    list(labels[edge.target_symbol_id]),
                    edge.kind,
                    edge.confidence,
                ]
                for edge in edges
            ]
        ),
    }


def resolution_report(plan):
    """Explicit report; persist separately for durable provenance.

    Detector records live on the graph plan and in this report.
    Symbol/edge database rows do not store the complete detector payload.
    """
    return {
        "counts": {
            status: sum(
                result.status == status
                for result in plan.results
            )
            for status in (
                "EXACT",
                "INFERRED",
                "AMBIGUOUS",
                "UNRESOLVED",
            )
        },
        "results": [
            result.model_dump(mode="json")
            for result in plan.results
        ],
        "edge_evidence": [
            {
                "source_key": edge.source_key,
                "target_key": edge.target_key,
                "kind": edge.kind,
                "confidence": edge.confidence,
                "reference_keys": list(edge.reference_keys),
            }
            for edge in plan.edges
        ],
        "detection": plan.detection.model_dump(mode="json"),
        "test_linking": plan.test_linking.model_dump(mode="json"),
    }
