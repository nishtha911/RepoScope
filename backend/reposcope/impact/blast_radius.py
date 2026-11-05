"""Snapshot-scoped deterministic multi-source reverse breadth-first traversal.

This is structural reachability, not a probability of failure or a risk score.
"""
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
import networkx as nx
from reposcope.graph.traversal_types import TraversalBudgetExceeded, edge_confidence, positive_int

PROPAGATION_KINDS = frozenset({"CALLS", "INHERITS", "USES"})


@dataclass(frozen=True)
class BlastRadiusHit:
    symbol_id: int
    file_id: int
    file_path: str
    kind: str
    name: str
    min_depth: int
    depth: int
    weight: float
    seed_symbol_id: int
    symbol_path: tuple[int, ...]
    edge_path: tuple[int, ...]
    relationship_path: tuple[str, ...]
    is_endpoint: bool
    is_database_model: bool


@dataclass(frozen=True)
class EndpointExposure:
    module_symbol_id: int
    endpoint_symbol_id: int
    edge_id: int
    confidence: float | None


@dataclass(frozen=True)
class BlastRadiusResult:
    repository_id: int
    snapshot_id: int
    seed_symbol_ids: tuple[int, ...]
    hits: tuple[BlastRadiusHit, ...]
    affected_file_ids: tuple[int, ...]
    affected_endpoint_ids: tuple[int, ...]
    affected_database_model_ids: tuple[int, ...]
    skipped_confidence_edge_ids: tuple[int, ...]
    depth_limited: bool
    endpoint_exposures: tuple[EndpointExposure, ...]
    warnings: tuple[str, ...]


def blast_radius(graph, repository_id, snapshot_id, modified_symbol_ids, *,
                 max_depth=4, decay=0.8, max_results=10000, max_expansions=100000):
    """Queue bounded simple paths from all seeds; retain the strongest per node.

    All seeds have weight 1. At depth d>=1, weight is product(confidences)
    * decay**(d-1). min_depth and best-path depth are deliberately separate.
    Seeds are included, deduplicated. Budget exhaustion raises, never silently
    returns partial success. Missing/invalid confidence is skipped and reported.
    EXPOSES is metadata only: module membership does not imply all sibling
    endpoints depend on an affected handler. Endpoint CALLS links are reversed
    like ordinary calls. Database models use an explicit node flag.
    """
    positive_int(repository_id, "repository_id")
    positive_int(snapshot_id, "snapshot_id")
    positive_int(max_depth, "max_depth", 8)
    positive_int(max_results, "max_results", 100000)
    positive_int(max_expansions, "max_expansions", 10000000)
    decay_value = edge_confidence(decay)
    if decay_value is None:
        raise ValueError("decay must be finite and between 0 and 1")
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("Expected MultiDiGraph")
    if graph.graph.get("repository_id") != repository_id or graph.graph.get("snapshot_id") != snapshot_id:
        raise ValueError("Graph repository/snapshot mismatch")
    if isinstance(modified_symbol_ids, (str, bytes)):
        raise ValueError("Pass an iterable of symbol IDs")
    seeds_raw = tuple(modified_symbol_ids)
    for seed in seeds_raw:
        positive_int(seed, "modified_symbol_id")
    seeds = tuple(sorted(set(seeds_raw)))
    for sid, node in graph.nodes(data=True):
        positive_int(sid, "symbol_id")
        if node.get("repository_id") != repository_id or node.get("snapshot_id") != snapshot_id:
            raise ValueError("Foreign or unscoped graph node")
        positive_int(node.get("file_id"), "file_id")
        if not all(isinstance(node.get(k), str) and node[k].strip() for k in ("file_path", "kind", "name")):
            raise ValueError("Missing graph node metadata")
    if any(seed not in graph for seed in seeds):
        raise ValueError("Modified symbol missing from selected snapshot")
    ids = set()
    for _, _, key, edge in graph.edges(keys=True, data=True):
        eid = edge.get("edge_id", key)
        positive_int(eid, "edge_id")
        if eid in ids:
            raise ValueError("Edge IDs must be unique")
        ids.add(eid)
    queue = deque((seed, 0, Decimal(1), (seed,), (), ()) for seed in seeds)
    best, minimum, skipped = {}, {}, set()
    expansions = 0
    limited = False
    while queue:
        current, depth, weight, path, edge_path, kinds = queue.popleft()
        candidate = (-weight, depth, path, edge_path)
        minimum[current] = min(minimum.get(current, depth), depth)
        if current not in best or candidate < best[current][0]:
            best[current] = (candidate, weight, path, edge_path, kinds)
        if len(best) > max_results:
            raise TraversalBudgetExceeded("Blast radius exceeds max_results")
        incoming = sorted(graph.in_edges(current, keys=True, data=True),
                          key=lambda e: (e[0], e[3].get("edge_id", e[2])))
        for source, _, key, edge in incoming:
            if edge.get("kind") not in PROPAGATION_KINDS or source in path:
                continue
            expansions += 1
            if expansions > max_expansions:
                raise TraversalBudgetExceeded("Blast radius exceeds max_expansions")
            eid = edge.get("edge_id", key)
            confidence = edge_confidence(edge.get("confidence"))
            if confidence is None:
                skipped.add(eid)
                continue
            if depth == max_depth:
                if source not in minimum:
                    limited = True
                continue
            new_weight = weight * confidence * (Decimal(1) if depth == 0 else decay_value)
            queue.append((source, depth + 1, new_weight, path + (source,),
                          edge_path + (eid,), kinds + (edge["kind"],)))
    hits = []
    for sid in sorted(best):
        _, weight, path, edges, kinds = best[sid]
        node = graph.nodes[sid]
        hits.append(BlastRadiusHit(sid, node["file_id"], node["file_path"], node["kind"],
            node["name"], minimum[sid], len(edges), float(weight), path[0], path,
            edges, kinds, node["kind"] == "endpoint", node.get("is_database_model") is True))
    endpoints = {h.symbol_id for h in hits if h.is_endpoint}
    exposures = []
    for source, target, key, edge in graph.edges(keys=True, data=True):
        if edge.get("kind") == "EXPOSES" and target in endpoints:
            confidence = edge_confidence(edge.get("confidence"))
            exposures.append(EndpointExposure(source, target, edge.get("edge_id", key),
                             float(confidence) if confidence is not None else None))
    return BlastRadiusResult(repository_id, snapshot_id, seeds, tuple(hits),
        tuple(sorted({h.file_id for h in hits})),
        tuple(h.symbol_id for h in hits if h.is_endpoint),
        tuple(h.symbol_id for h in hits if h.is_database_model),
        tuple(sorted(skipped)), limited,
        tuple(sorted(exposures, key=lambda e: (e.endpoint_symbol_id, e.edge_id))),
        ("Static reachability is not runtime impact or test coverage.",))


def load_snapshot_graph(session, repository_id, snapshot_id, *, database_model_ids=(),
                        max_nodes=100000, max_edges=500000):
    """Read-only loader, both edge ends scoped to the same selected snapshot.

    Use a clean read session in an outer REPEATABLE READ transaction for a
    consistent PostgreSQL multi-query view. Does not commit or set isolation.
    Model IDs must come from verified model detection; class kind is insufficient.
    """
    from sqlalchemy import text
    positive_int(repository_id, "repository_id")
    positive_int(snapshot_id, "snapshot_id")
    positive_int(max_nodes, "max_nodes", 1000000)
    positive_int(max_edges, "max_edges", 2000000)
    params = {"repo": repository_id, "snap": snapshot_id}
    snapshot = session.execute(text("SELECT status, commit_sha FROM repository_snapshots WHERE id=:snap AND repository_id=:repo"), params).mappings().one_or_none()
    if snapshot is None or snapshot["status"] != "ready":
        raise ValueError("Selected repository snapshot must exist and be ready")
    nodes = session.execute(text("""
        SELECT s.id, s.file_id, s.name, s.qualname, s.kind, s.start_line,
               s.end_line, f.path AS file_path
        FROM symbols s JOIN files f ON f.id=s.file_id
        WHERE f.repository_id=:repo AND f.snapshot_id=:snap
        ORDER BY s.id LIMIT :cap
    """), {**params, "cap": max_nodes + 1}).mappings().all()
    if len(nodes) > max_nodes:
        raise TraversalBudgetExceeded("Snapshot exceeds max_nodes")
    edges = session.execute(text("""
        SELECT e.id, e.source_symbol_id, e.target_symbol_id, e.kind, e.confidence
        FROM edges e
        JOIN symbols s ON s.id=e.source_symbol_id JOIN files sf ON sf.id=s.file_id
        JOIN symbols t ON t.id=e.target_symbol_id JOIN files tf ON tf.id=t.file_id
        WHERE sf.repository_id=:repo AND tf.repository_id=:repo
          AND sf.snapshot_id=:snap AND tf.snapshot_id=:snap
        ORDER BY e.id LIMIT :cap
    """), {**params, "cap": max_edges + 1}).mappings().all()
    if len(edges) > max_edges:
        raise TraversalBudgetExceeded("Snapshot exceeds max_edges")
    models = tuple(database_model_ids)
    for mid in models:
        positive_int(mid, "database_model_id")
    node_ids = {r["id"] for r in nodes}
    if not set(models) <= node_ids:
        raise ValueError("Database model IDs outside selected snapshot")
    graph = nx.MultiDiGraph(repository_id=repository_id, snapshot_id=snapshot_id, commit_sha=snapshot["commit_sha"])
    for row in nodes:
        attrs = dict(row)
        sid = attrs.pop("id")
        graph.add_node(sid, **attrs, repository_id=repository_id, snapshot_id=snapshot_id,
                       is_database_model=sid in models)
    for row in edges:
        graph.add_edge(row["source_symbol_id"], row["target_symbol_id"], key=row["id"],
                       edge_id=row["id"], kind=row["kind"], confidence=row["confidence"])
    return graph


def analyze_snapshot_blast_radius(session, repository_id, snapshot_id, modified_symbol_ids,
                                 *, database_model_ids=(), max_nodes=100000,
                                 max_edges=500000, **options):
    graph = load_snapshot_graph(session, repository_id, snapshot_id,
        database_model_ids=database_model_ids, max_nodes=max_nodes, max_edges=max_edges)
    return blast_radius(graph, repository_id, snapshot_id, modified_symbol_ids, **options)


@dataclass(frozen=True)
class DiffSeedResolution:
    side: str
    seed_symbol_ids: tuple[int, ...]
    gaps: tuple[str, ...]


def resolve_diff_seeds(diff_report, graph, side, local_key_to_symbol_id):
    """Validate caller-provided base/head local-key bindings against graph metadata.

    Call separately for base and head, using the corresponding snapshot graph.
    Revision SHA must exactly match. Missing bindings are explicit gaps. Never
    match by name alone or reuse a head ID for a removed base symbol.
    """
    if side not in ("base", "head"):
        raise ValueError("side must be base or head")
    revision = getattr(diff_report, f"{side}_revision")
    if not revision or revision != graph.graph.get("commit_sha"):
        raise ValueError("Diff side revision must match graph commit_sha")
    seeds, gaps = set(), []
    if diff_report.gaps:
        gaps.append("Upstream diff mapper reported gaps; seed set may be incomplete")
    for change in diff_report.changes:
        version = getattr(change, f"{side}_symbol")
        if version is None:
            continue
        sid = local_key_to_symbol_id.get(version.local_key)
        if sid is None:
            gaps.append(f"Missing {side} persisted ID binding: {version.local_key}")
            continue
        positive_int(sid, "bound_symbol_id")
        if sid not in graph:
            raise ValueError("Bound symbol missing from selected graph")
        node = graph.nodes[sid]
        actual = (node.get("file_path"), node.get("qualname"), node.get("kind"),
                  node.get("start_line"), node.get("end_line"))
        expected = (version.path, version.qualname, version.kind,
                    version.start_line, version.end_line)
        if actual != expected:
            raise ValueError("Diff binding does not match side-specific symbol metadata")
        seeds.add(sid)
    return DiffSeedResolution(side, tuple(sorted(seeds)), tuple(sorted(set(gaps))))
