from dataclasses import dataclass

import networkx as nx
import pytest

from reposcope.retrieval.graph_expand import expand_graph


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    symbol_id: int
    repo_id: int = 1
    score: float = 1.0
    text: str = "code"


def graph():
    g = nx.MultiDiGraph(repository_id=1)
    for node in range(1, 31):
        kind = "endpoint" if node == 3 else "module" if node == 4 else "class" if node in {7,8,9,10} else "function"
        g.add_node(node, repository_id=1, name=f"n{node}", qualname=f"n{node}", kind=kind, file_path="app.py")
    return g


def edge(g, source, target, kind="CALLS", confidence=1.0):
    edge_id = g.number_of_edges() + 1
    g.add_edge(source, target, key=edge_id, edge_id=edge_id, kind=kind, confidence=confidence)


def fixture():
    g = graph()
    for source,target,kind in [(2,1,"CALLS"),(3,2,"CALLS"),(4,3,"EXPOSES"),
                               (1,5,"CALLS"),(5,6,"CALLS"),(1,9,"USES"),
                               (8,7,"INHERITS"),(7,10,"INHERITS")]:
        edge(g,source,target,kind)
    return g


def indexed(result):
    return {symbol.symbol_id:symbol for symbol in result.symbols}


def test_callers_use_incoming_calls_two_hops():
    result = expand_graph(fixture(),1,[Hit(1,1)],intent="callers")
    found = indexed(result)
    assert set(found) == {2,3}
    assert found[3].paths[0].symbol_ids == (1,2,3)
    assert found[3].paths[0].directions == ("incoming","incoming")
    assert not result.truncated


def test_implementation_uses_outgoing_calls_and_models():
    found = indexed(expand_graph(fixture(),1,[Hit(1,1)],intent="implementation"))
    assert set(found) == {5,6,9}
    assert found[9].paths[0].edge_kinds == ("USES",)


def test_inheritance_only_parent_classes():
    found = indexed(expand_graph(fixture(),1,[Hit(8,8)],intent="inheritance"))
    assert set(found) == {7,10}
    assert found[10].depth == 2


@pytest.mark.parametrize("seed,expected", [(1,{2,3}),(2,{3,4}),(4,{2,3}),(3,{2,4})])
def test_endpoint_policy_matches_actual_detector_convention(seed,expected):
    result = expand_graph(fixture(),1,[Hit(seed,seed)],intent="endpoints")
    assert set(indexed(result)) == expected
    assert not result.gaps


def test_general_does_not_zigzag_to_unrelated_sibling():
    g = fixture()
    edge(g,2,11)
    found = indexed(expand_graph(g,1,[Hit(1,1)],intent="general"))
    assert {2,3,5,6,9} <= set(found)
    assert 11 not in found


def test_eight_unique_seeds_preserve_rank_and_ignore_duplicate_symbol():
    hits = [Hit(100,1,score=1),Hit(101,1,score=.99)]
    hits += [Hit(node,node,score=.9-node/100) for node in range(2,11)]
    result = expand_graph(graph(),1,hits,intent="callers")
    assert [seed.symbol_id for seed in result.seeds] == list(range(1,9))
    assert [seed.rank for seed in result.seeds][:2] == [1,3]
    assert not result.truncated


def test_missing_seed_is_a_gap_and_next_valid_hit_is_used():
    result = expand_graph(graph(),1,[Hit(999,999),Hit(1,1,score=.5)],intent="callers")
    assert [s.symbol_id for s in result.seeds] == [1]
    assert result.gaps


def test_multiple_seed_provenance_deduplicates_context():
    g = graph()
    edge(g,1,5)
    edge(g,5,6)
    found = indexed(expand_graph(g,1,[Hit(1,1),Hit(5,5,score=.5)],intent="implementation"))
    assert set(found) == {6}
    assert {p.seed_symbol_id for p in found[6].paths} == {1,5}
    assert found[6].depth == 1


def test_cycles_and_self_loops_do_not_repeat_nodes():
    g = graph()
    edge(g,1,5)
    edge(g,5,1)
    edge(g,5,5)
    result = expand_graph(g,1,[Hit(1,1)],intent="implementation")
    assert set(indexed(result)) == {5}
    assert all(len(set(p.symbol_ids)) == len(p.symbol_ids) for s in result.symbols for p in s.paths)


def test_best_confidence_path_retained_per_seed_and_symbol():
    g = graph()
    edge(g,1,5,confidence=.2)
    edge(g,1,6)
    edge(g,6,5)
    found = indexed(expand_graph(g,1,[Hit(1,1)],intent="implementation"))
    assert found[5].paths[0].symbol_ids == (1,6,5)
    assert found[5].paths[0].confidence == 1
    assert found[5].depth == 2


def test_confidence_product_threshold_without_impact_decay():
    g = graph()
    edge(g,1,5,confidence=.8)
    edge(g,5,6,confidence=.8)
    found = indexed(expand_graph(g,1,[Hit(1,1)],intent="implementation",min_confidence=.6))
    assert found[6].paths[0].confidence == pytest.approx(.64)
    found = indexed(expand_graph(g,1,[Hit(1,1)],intent="implementation",min_confidence=.7))
    assert set(found) == {5}


def test_invalid_confidence_is_gap_and_zero_is_valid():
    g = graph()
    edge(g,1,5,confidence=None)
    edge(g,1,6,confidence=float("nan"))
    edge(g,1,9,kind="USES",confidence=0)
    result = expand_graph(g,1,[Hit(1,1)],intent="implementation")
    assert set(indexed(result)) == {9}
    assert len(result.gaps) == 2
    assert not result.truncated


def test_repository_scope_and_cross_repository_edges():
    g = graph()
    g.nodes[5]["repository_id"] = 2
    edge(g,1,5)
    assert not expand_graph(g,1,[Hit(1,1)],intent="implementation").symbols
    with pytest.raises(ValueError):
        expand_graph(g,1,[Hit(1,1,repo_id=2)],intent="callers")
    with pytest.raises(ValueError):
        expand_graph(g,2,[],intent="callers")


def test_seed_and_graph_are_not_mutated():
    g = fixture()
    before = g.copy()
    hit = Hit(1,1)
    expand_graph(g,1,[hit],intent="general")
    assert nx.utils.graphs_equal(g,before)
    assert hit == Hit(1,1)


@pytest.mark.parametrize("options,reason", [
    ({"max_neighbors_per_seed":1},"max_neighbors_per_seed"),
    ({"max_expanded_symbols":1},"max_expanded_symbols"),
    ({"max_expansions":1},"max_expansions"),
])
def test_budget_truncation_is_explicit(options,reason):
    result = expand_graph(fixture(),1,[Hit(1,1)],intent="implementation",**options)
    assert result.truncated and reason in result.truncation_reasons


def test_empty_inputs_and_zero_depth():
    assert not expand_graph(graph(),1,[],intent="callers").seeds
    result = expand_graph(fixture(),1,[Hit(1,1)],intent="callers",max_depth=0)
    assert len(result.seeds) == 1 and not result.symbols


def test_no_endpoint_claim_is_not_a_negative_codebase_claim():
    result = expand_graph(graph(),1,[Hit(1,1)],intent="endpoints")
    assert "does not prove" in result.gaps[0]


@pytest.mark.parametrize("options", [
    {"seed_limit":9},{"seed_limit":True},{"max_depth":3},{"max_depth":-1},
    {"max_neighbors_per_seed":0},{"max_expanded_symbols":0},{"max_expansions":0},
    {"min_confidence":1.1},{"min_confidence":float("nan")},
])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        expand_graph(graph(),1,[Hit(1,1)],intent="callers",**options)


def test_unknown_intent_unsorted_hits_and_conflicting_chunk_identity():
    with pytest.raises(ValueError):
        expand_graph(graph(),1,[],intent="unknown")
    with pytest.raises(ValueError):
        expand_graph(graph(),1,[Hit(1,1,score=.1),Hit(2,2,score=.2)],intent="callers")
    with pytest.raises(ValueError):
        expand_graph(graph(),1,[Hit(1,1),Hit(1,2,score=.5)],intent="callers")


def test_parallel_edges_preserve_selected_edge_evidence():
    g = graph()
    edge(g,1,5,confidence=.5)
    edge(g,1,5,kind="USES",confidence=1)
    result = expand_graph(g,1,[Hit(1,1)],intent="implementation")
    path = indexed(result)[5].paths[0]
    assert path.edge_ids == (2,) and path.edge_kinds == ("USES",)
