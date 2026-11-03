"""Repository-scoped NetworkX loader and bounded reverse traversal."""
import networkx as nx
from decimal import Decimal

from reposcope.graph.traversal_types import (
    DEFAULT_KINDS, DECAY, ImpactHit, ReachabilityResult,
    TraversalBudgetExceeded, edge_confidence, positive_int, validate_options,
)


def load_repository_graph(session, repository_id, *, max_nodes=100000, max_edges=500000):
    """Load all symbols and internal edges, preserving parallel relationship kinds.

    Read-only/no commit. For a consistent multi-query snapshot use an outer
    REPEATABLE READ transaction. Node/edge limits reject oversized loads.
    """
    from sqlalchemy import text
    positive_int(repository_id, "repository_id")
    positive_int(max_nodes, "max_nodes", 1000000)
    positive_int(max_edges, "max_edges", 2000000)
    nodes = session.execute(text("""
        SELECT s.id AS symbol_id, s.name, s.qualname, s.kind,
               f.path AS file_path, f.repository_id
        FROM symbols s JOIN files f ON f.id = s.file_id
        WHERE f.repository_id = :repo_id
        ORDER BY s.id LIMIT :cap
    """), {"repo_id": repository_id, "cap": max_nodes + 1}).mappings().all()
    if len(nodes) > max_nodes:
        raise TraversalBudgetExceeded("Repository graph exceeds max_nodes")
    edges = session.execute(text("""
        SELECT e.id, e.source_symbol_id, e.target_symbol_id, e.kind, e.confidence
        FROM edges e
        JOIN symbols src ON src.id = e.source_symbol_id
        JOIN files sf ON sf.id = src.file_id
        JOIN symbols dst ON dst.id = e.target_symbol_id
        JOIN files tf ON tf.id = dst.file_id
        WHERE sf.repository_id = :repo_id AND tf.repository_id = :repo_id
        ORDER BY e.id LIMIT :cap
    """), {"repo_id": repository_id, "cap": max_edges + 1}).mappings().all()
    if len(edges) > max_edges:
        raise TraversalBudgetExceeded("Repository graph exceeds max_edges")
    graph = nx.MultiDiGraph(repository_id=repository_id)
    for row in nodes:
        data = dict(row)
        node_id = data.pop("symbol_id")
        graph.add_node(node_id, **data)
    for row in edges:
        graph.add_edge(row["source_symbol_id"], row["target_symbol_id"],
                       key=row["id"], edge_id=row["id"],
                       kind=row["kind"], confidence=row["confidence"])
    return graph


def reverse_reachability_networkx(
    graph, repository_id, root_symbol_id, *, max_depth=4,
    kinds=DEFAULT_KINDS, max_results=10000, max_expansions=100000,
):
    """Enumerate bounded simple reverse paths, selecting best path per symbol.

    Path order is root -> upstream dependent, opposite stored edge direction.
    Score ties: shorter path, lexicographically smaller node path, then edge IDs.
    min_depth is shortest VALID path; depth belongs to the highest-scoring path.
    """
    kinds = validate_options(repository_id, root_symbol_id, max_depth, kinds, max_results)
    positive_int(max_expansions, "max_expansions", 10000000)
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("Expected a NetworkX MultiDiGraph")
    if graph.graph.get("repository_id") != repository_id:
        raise ValueError("Graph repository does not match repository_id")
    if root_symbol_id not in graph or graph.nodes[root_symbol_id].get("repository_id") != repository_id:
        raise ValueError("Root symbol does not belong to the repository")

    def internal(source, target):
        return (graph.nodes[source].get("repository_id") == repository_id
                and graph.nodes[target].get("repository_id") == repository_id)

    skipped = sum(
        1 for source, target, data in graph.edges(data=True)
        if internal(source, target) and data.get("kind") in kinds
        and edge_confidence(data.get("confidence")) is None
    )
    best, minimum = {}, {}
    stack = [(root_symbol_id, 0, Decimal(1), (root_symbol_id,), ())]
    expansions = 0
    while stack:
        current, depth, score, path, edge_path = stack.pop()
        if depth == max_depth:
            continue
        incoming = sorted(graph.in_edges(current, keys=True, data=True),
                          key=lambda row: (row[0], row[3].get("edge_id", row[2])))
        for source, target, edge_key, data in incoming:
            expansions += 1
            if expansions > max_expansions:
                raise TraversalBudgetExceeded("Reverse traversal exceeds max_expansions")
            if not internal(source, target) or data.get("kind") not in kinds or source in path:
                continue
            confidence = edge_confidence(data.get("confidence"))
            if confidence is None:
                continue
            edge_id = data.get("edge_id", edge_key)
            positive_int(edge_id, "edge_id")
            new_depth = depth + 1
            new_score = score * confidence * (Decimal(1) if depth == 0 else DECAY)
            new_path, new_edges = path + (source,), edge_path + (edge_id,)
            candidate = (-new_score, new_depth, new_path, new_edges)
            minimum[source] = min(minimum.get(source, new_depth), new_depth)
            if source not in best or candidate < best[source]:
                best[source] = candidate
            # Do not prune on best[source]: a weaker but shorter path can reach
            # additional dependents within the hop budget.
            stack.append((source, new_depth, new_score, new_path, new_edges))
    if len(best) > max_results:
        raise TraversalBudgetExceeded("Reverse traversal exceeds max_results")
    ordered = sorted(best, key=lambda node: (best[node][0], best[node][1], node,
                                            best[node][2], best[node][3]))
    hits = []
    for node in ordered:
        negative_score, depth, path, edge_path = best[node]
        metadata = graph.nodes[node]
        hits.append(ImpactHit(
            symbol_id=node, name=metadata["name"], qualname=metadata.get("qualname"),
            kind=metadata["kind"], file_path=metadata["file_path"], depth=depth,
            min_depth=minimum[node], score=float(-negative_score),
            symbol_path=path, edge_path=edge_path,
        ))
    return ReachabilityResult(repository_id, root_symbol_id, max_depth, tuple(hits), skipped)
