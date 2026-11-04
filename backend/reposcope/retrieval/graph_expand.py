"""Pure intent-based expansion of ranked hybrid seeds over a repository graph.

No database, embeddings, configuration imports, or graph mutation. Paths retain
original edge IDs and explicit traversal directions. Fused scores are NOT edge
confidences. Defaults are context budgets, not completeness guarantees.
"""
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
import math
from numbers import Real
from typing import TYPE_CHECKING, Literal

import networkx as nx

if TYPE_CHECKING:
    from reposcope.retrieval.pipeline import HybridHit

ExpansionIntent = Literal["callers", "implementation", "inheritance", "endpoints", "general"]
Direction = Literal["incoming", "outgoing"]


@dataclass(frozen=True)
class ExpansionSeed:
    symbol_id: int
    chunk_id: int
    fused_score: float
    rank: int


@dataclass(frozen=True)
class ExpansionPath:
    seed_symbol_id: int
    symbol_ids: tuple[int, ...]
    edge_ids: tuple[int, ...]
    edge_kinds: tuple[str, ...]
    directions: tuple[Direction, ...]
    confidence: float


@dataclass(frozen=True)
class ExpandedSymbol:
    symbol_id: int
    name: str
    qualname: str | None
    kind: str
    file_path: str
    depth: int
    paths: tuple[ExpansionPath, ...]


@dataclass(frozen=True)
class GraphExpansionResult:
    repository_id: int
    intent: ExpansionIntent
    seeds: tuple[ExpansionSeed, ...]
    symbols: tuple[ExpandedSymbol, ...]
    gaps: tuple[str, ...]
    truncated: bool
    truncation_reasons: tuple[str, ...]


# Explicit sequences prevent unintentional direction changes at hop two.
_CI = ("CALLS", "incoming")
_CO = ("CALLS", "outgoing")
_UO = ("USES", "outgoing")
_IO = ("INHERITS", "outgoing")
_EI = ("EXPOSES", "incoming")
_EO = ("EXPOSES", "outgoing")
_PATTERNS = {
    "callers": ((_CI,), (_CI, _CI)),
    "implementation": ((_CO,), (_CO, _CO), (_UO,), (_CO, _UO)),
    "inheritance": ((_IO,), (_IO, _IO)),
    "endpoints": ((_CI,), (_CI, _CI), (_CI, _EI), (_EI,), (_EO,), (_EO, _CO), (_CO,)),
}
_PATTERNS["general"] = tuple(dict.fromkeys(
    pattern for patterns in tuple(_PATTERNS.values()) for pattern in patterns
))


def _integer(value, name, *, minimum=1, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _confidence(value):
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    if not math.isfinite(float(value)):
        return None
    value = Decimal(str(value))
    return value if Decimal(0) <= value <= Decimal(1) else None


def _path_order(path):
    return (-path.confidence, len(path.edge_ids), path.symbol_ids,
            path.edge_ids, path.edge_kinds, path.directions)


def _node_owned(graph, node, repository_id):
    return node in graph and graph.nodes[node].get("repository_id") == repository_id


def _raw_edges(graph, current, direction):
    adjacency = graph.pred[current] if direction == "incoming" else graph.succ[current]
    for neighbor in sorted(adjacency):
        for key in sorted(adjacency[neighbor], key=lambda value: (type(value).__name__, str(value))):
            data = adjacency[neighbor][key]
            source, target = ((neighbor, current) if direction == "incoming" else (current, neighbor))
            yield source, target, key, data


def _typed_step(graph, source, target, kind, intent, direction):
    source_kind = graph.nodes[source].get("kind")
    target_kind = graph.nodes[target].get("kind")
    if kind == "EXPOSES":
        return source_kind == "module" and target_kind == "endpoint"
    if kind == "INHERITS":
        return source_kind == "class" and target_kind == "class"
    # Endpoint-intent outgoing CALLS represents route dispatch, not arbitrary
    # outgoing handler/service dependencies. Incoming CALLS can find handlers.
    if intent == "endpoints" and kind == "CALLS" and direction == "outgoing":
        return source_kind == "endpoint" and target_kind in {"function", "method"}
    return True


def expand_graph(
    graph: nx.MultiDiGraph,
    repository_id: int,
    fused_hits: Sequence["HybridHit"],
    *,
    intent: ExpansionIntent,
    seed_limit: int = 8,
    max_depth: int = 2,
    max_neighbors_per_seed: int = 20,
    max_expanded_symbols: int = 80,
    max_expansions: int = 10_000,
    min_confidence: float = 0.0,
) -> GraphExpansionResult:
    """Return additional context, keeping seeds separate.

    Input must be ranked best-first. Seed rank is the original hit position.
    Keep the best path per (seed, extra symbol), at most eight paths per symbol.
    Path confidence is the product of edge confidences; no impact-score decay.
    Per-seed selection: confidence DESC, depth ASC, stable identities.
    Global selection: best contributing seed rank, then that path's ordering.
    Budgets return explicitly truncated context; loader/database errors propagate.
    """
    _integer(repository_id, "repository_id")
    _integer(seed_limit, "seed_limit", maximum=8)
    _integer(max_depth, "max_depth", minimum=0, maximum=2)
    _integer(max_neighbors_per_seed, "max_neighbors_per_seed", maximum=1000)
    _integer(max_expanded_symbols, "max_expanded_symbols", maximum=10000)
    _integer(max_expansions, "max_expansions", maximum=1000000)
    threshold = _confidence(min_confidence)
    if threshold is None:
        raise ValueError("min_confidence must be a finite number in [0,1]")
    if intent not in _PATTERNS:
        raise ValueError("Unsupported expansion intent")
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("graph must be a MultiDiGraph")
    if graph.graph.get("repository_id") != repository_id:
        raise ValueError("Graph repository does not match repository_id")
    if not isinstance(fused_hits, Sequence) or isinstance(fused_hits, (str, bytes)):
        raise TypeError("fused_hits must be a ranked sequence of HybridHit-like records")
    if len(fused_hits) > 1000:
        raise ValueError("Too many fused hits; pass bounded hybrid retrieval output")

    gaps, reasons = set(), set()
    seeds, selected, chunk_metadata = [], set(), {}
    previous_score = float("inf")
    for rank, hit in enumerate(fused_hits, start=1):
        try:
            symbol_id, chunk_id, repo_id, score = hit.symbol_id, hit.chunk_id, hit.repo_id, hit.score
        except AttributeError as exc:
            raise TypeError("Each fused hit requires symbol_id, chunk_id, repo_id and score") from exc
        _integer(symbol_id, "seed symbol_id")
        _integer(chunk_id, "seed chunk_id")
        _integer(repo_id, "seed repo_id")
        if repo_id != repository_id:
            raise ValueError("Fused hit belongs to another repository")
        if isinstance(score, bool) or not isinstance(score, (Real, Decimal)) or not math.isfinite(float(score)) or score < 0:
            raise ValueError("Fused scores must be finite nonnegative numbers")
        score = float(score)
        if score > previous_score:
            raise ValueError("fused_hits must be ranked best-first")
        previous_score = score
        metadata = (symbol_id, repo_id)
        if chunk_id in chunk_metadata and chunk_metadata[chunk_id] != metadata:
            raise ValueError("Inconsistent symbol ownership for a chunk")
        chunk_metadata[chunk_id] = metadata
        if len(seeds) == seed_limit or symbol_id in selected:
            continue
        if not _node_owned(graph, symbol_id, repository_id):
            gaps.add(f"Seed symbol {symbol_id} is unavailable in the repository graph")
            continue
        seeds.append(ExpansionSeed(symbol_id, chunk_id, score, rank))
        selected.add(symbol_id)

    rank_by_seed = {seed.symbol_id: seed.rank for seed in seeds}
    retained = {}
    expansions, stop = 0, False
    for seed in seeds:
        if stop:
            break
        best = {}
        frontier = deque([(seed.symbol_id, (seed.symbol_id,), (), (), (), Decimal(1), ())])
        while frontier and not stop:
            current, node_path, edge_path, edge_kinds, directions, confidence, tokens = frontier.popleft()
            if len(edge_path) >= max_depth:
                continue
            choices = sorted({pattern[len(tokens)] for pattern in _PATTERNS[intent]
                              if len(pattern) > len(tokens) and pattern[:len(tokens)] == tokens})
            for edge_kind, direction in choices:
                for source, target, key, data in _raw_edges(graph, current, direction):
                    if expansions >= max_expansions:
                        reasons.add("max_expansions")
                        stop = True
                        break
                    expansions += 1
                    if data.get("kind") != edge_kind:
                        continue
                    if not _node_owned(graph, source, repository_id) or not _node_owned(graph, target, repository_id):
                        continue
                    neighbor = source if direction == "incoming" else target
                    if neighbor in node_path or not _typed_step(graph, source, target, edge_kind, intent, direction):
                        continue
                    edge_id = data.get("edge_id", key)
                    if isinstance(edge_id, bool) or not isinstance(edge_id, int) or edge_id < 1:
                        gaps.add("A relevant graph edge has no valid edge ID")
                        continue
                    edge_confidence = _confidence(data.get("confidence"))
                    if edge_confidence is None:
                        gaps.add(f"Edge {edge_id} has missing or invalid confidence")
                        continue
                    product = confidence * edge_confidence
                    if product < threshold:
                        continue
                    next_nodes, next_edges = node_path + (neighbor,), edge_path + (edge_id,)
                    next_kinds, next_directions = edge_kinds + (edge_kind,), directions + (direction,)
                    path = ExpansionPath(seed.symbol_id, next_nodes, next_edges, next_kinds,
                                         next_directions, float(product))
                    if neighbor not in selected:
                        if neighbor not in best or _path_order(path) < _path_order(best[neighbor]):
                            best[neighbor] = path
                    frontier.append((neighbor, next_nodes, next_edges, next_kinds,
                                     next_directions, product, tokens + ((edge_kind, direction),)))
                if stop:
                    break
        ordered = sorted(best, key=lambda node: (_path_order(best[node]), node))
        if len(ordered) > max_neighbors_per_seed:
            reasons.add("max_neighbors_per_seed")
        for node in ordered[:max_neighbors_per_seed]:
            retained.setdefault(node, []).append(best[node])

    def global_order(node):
        path = min(retained[node], key=lambda p: (rank_by_seed[p.seed_symbol_id], _path_order(p)))
        return (rank_by_seed[path.seed_symbol_id], _path_order(path), node)

    ordered = sorted(retained, key=global_order)
    if len(ordered) > max_expanded_symbols:
        reasons.add("max_expanded_symbols")
    symbols = []
    for node in ordered[:max_expanded_symbols]:
        metadata = graph.nodes[node]
        if any(not isinstance(metadata.get(field), str) or not metadata[field]
               for field in ("name", "kind", "file_path")):
            raise ValueError(f"Expanded symbol {node} has incomplete metadata")
        paths = tuple(sorted(retained[node], key=lambda p: (rank_by_seed[p.seed_symbol_id], _path_order(p))))
        symbols.append(ExpandedSymbol(node, metadata["name"], metadata.get("qualname"),
                                      metadata["kind"], metadata["file_path"],
                                      min(len(p.edge_ids) for p in paths), paths))
    if intent == "endpoints" and seeds:
        found = any(graph.nodes[seed.symbol_id].get("kind") == "endpoint" for seed in seeds)
        found |= any(symbol.kind == "endpoint" for symbol in symbols)
        if not found:
            gaps.add("No endpoint was found in the retained context; this does not prove no endpoint exists")
    return GraphExpansionResult(repository_id, intent, tuple(seeds), tuple(symbols),
                                tuple(sorted(gaps)), bool(reasons), tuple(sorted(reasons)))
