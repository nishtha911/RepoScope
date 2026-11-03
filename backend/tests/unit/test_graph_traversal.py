import math
from decimal import Decimal

import networkx as nx
import pytest

from reposcope.graph.networkx_loader import reverse_reachability_networkx
from reposcope.graph.traversal_types import TraversalBudgetExceeded, edge_confidence


def graph(nodes=range(1, 13)):
    g = nx.MultiDiGraph(repository_id=1)
    for node in nodes:
        g.add_node(node, repository_id=1, name=f"f{node}", qualname=f"f{node}",
                   kind="function", file_path="app.py")
    return g


def add(g, source, target, confidence=1.0, kind="CALLS", edge_id=None):
    edge_id = edge_id or (g.number_of_edges() + 1)
    g.add_edge(source, target, key=edge_id, edge_id=edge_id,
               confidence=confidence, kind=kind)


def hits(result):
    return {h.symbol_id: h for h in result.hits}


def test_chain_depth_and_decay():
    g = graph()
    for node in range(2, 7):
        add(g, node, node - 1)
    result = reverse_reachability_networkx(g, 1, 1)
    assert [h.symbol_id for h in result.hits] == [2, 3, 4, 5]
    assert [h.score for h in result.hits] == pytest.approx([1, .8, .64, .512])
    assert hits(result)[5].symbol_path == (1, 2, 3, 4, 5)
    assert hits(result)[5].edge_path == (1, 2, 3, 4)


def test_reverse_direction_not_outgoing():
    g = graph()
    add(g, 2, 1)
    add(g, 1, 3)
    assert set(hits(reverse_reachability_networkx(g, 1, 1))) == {2}


def test_best_path_can_be_longer_than_shortest():
    g = graph()
    add(g, 2, 1, .2)
    add(g, 3, 1)
    add(g, 2, 3)
    add(g, 4, 2, .5)
    add(g, 5, 4)
    add(g, 6, 5)
    add(g, 7, 6)
    result = hits(reverse_reachability_networkx(g, 1, 1))
    assert result[2].score == pytest.approx(.8)
    assert result[2].depth == 2 and result[2].min_depth == 1
    assert result[4].score == pytest.approx(.32)
    # A weaker shorter path to 2 must still be expanded to reach 6 in four hops.
    assert result[6].score == pytest.approx(.0512)
    assert result[6].depth == 4
    assert 7 not in result


def test_cycles_and_self_loops_exclude_root():
    g = graph()
    add(g, 2, 1)
    add(g, 1, 2)
    add(g, 2, 2)
    result = reverse_reachability_networkx(g, 1, 1)
    assert set(hits(result)) == {2}
    assert all(len(set(h.symbol_path)) == len(h.symbol_path) for h in result.hits)


def test_parallel_edge_kinds_preserved():
    g = graph()
    add(g, 2, 1, .5, "CALLS", 1)
    add(g, 2, 1, 1, "INHERITS", 2)
    both = hits(reverse_reachability_networkx(g, 1, 1))
    calls = hits(reverse_reachability_networkx(g, 1, 1, kinds=("CALLS",)))
    assert both[2].score == 1 and both[2].edge_path == (2,)
    assert calls[2].score == .5


def test_null_and_invalid_confidence_are_gaps_zero_is_valid():
    g = graph()
    for node, confidence in [(2, None), (3, float("nan")), (4, 1.5), (5, -.1), (6, 0)]:
        add(g, node, 1, confidence)
    result = reverse_reachability_networkx(g, 1, 1)
    assert result.skipped_confidence_edges == 4
    assert set(hits(result)) == {6}
    assert hits(result)[6].score == 0


def test_cross_repository_edges_are_excluded():
    g = graph()
    g.nodes[2]["repository_id"] = 2
    add(g, 2, 1)
    assert reverse_reachability_networkx(g, 1, 1).hits == ()
    with pytest.raises(ValueError):
        reverse_reachability_networkx(g, 1, 2)


def test_tie_breaking_is_deterministic():
    g = graph()
    add(g, 3, 1, 1, edge_id=10)
    add(g, 2, 1, 1, edge_id=11)
    add(g, 4, 3, 1, edge_id=12)
    add(g, 4, 2, 1, edge_id=13)
    assert hits(reverse_reachability_networkx(g, 1, 1))[4].symbol_path == (1, 2, 4)


@pytest.mark.parametrize("depth", [0, 5, True, "4"])
def test_invalid_depth(depth):
    with pytest.raises(ValueError):
        reverse_reachability_networkx(graph(), 1, 1, max_depth=depth)


def test_missing_root_wrong_repo_and_edge_filter():
    g = graph()
    with pytest.raises(ValueError):
        reverse_reachability_networkx(g, 1, 999)
    with pytest.raises(ValueError):
        reverse_reachability_networkx(g, 2, 1)
    with pytest.raises(ValueError):
        reverse_reachability_networkx(g, 1, 1, kinds=("TESTED_BY",))
    add(g, 2, 1, kind="IMPORTS")
    assert reverse_reachability_networkx(g, 1, 1).hits == ()
    assert set(hits(reverse_reachability_networkx(g, 1, 1, kinds=("IMPORTS",)))) == {2}


def test_budgets_raise_instead_of_returning_partial_results():
    g = graph()
    add(g, 2, 1)
    add(g, 3, 1)
    with pytest.raises(TraversalBudgetExceeded):
        reverse_reachability_networkx(g, 1, 1, max_results=1)
    with pytest.raises(TraversalBudgetExceeded):
        reverse_reachability_networkx(g, 1, 1, max_expansions=1)


@pytest.mark.parametrize("value", [None, True, "0.5", float("inf"), float("nan"), -1, 2])
def test_confidence_validation(value):
    assert edge_confidence(value) is None


def test_decimal_confidence_and_depth_one_no_decay():
    g = graph()
    add(g, 2, 1, Decimal("0.5"))
    add(g, 3, 2, Decimal("0.5"))
    r = hits(reverse_reachability_networkx(g, 1, 1))
    assert r[2].score == .5
    assert r[3].score == .2
