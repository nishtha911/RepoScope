import math
import networkx as nx
import pytest
from reposcope.impact.blast_radius import blast_radius
from reposcope.graph.traversal_types import TraversalBudgetExceeded


def graph(count=8):
    g = nx.MultiDiGraph(repository_id=1, snapshot_id=10)
    for sid in range(1, count + 1):
        g.add_node(sid, repository_id=1, snapshot_id=10, file_id=sid,
                   file_path=f"f{sid}.py", name=f"s{sid}", kind="function")
    return g


def add(g, a, b, kind="CALLS", confidence=1.0, eid=None):
    eid = eid or g.number_of_edges() + 1
    g.add_edge(a, b, key=eid, edge_id=eid, kind=kind, confidence=confidence)


def run(g, seeds=(1,), **kw):
    return blast_radius(g, 1, 10, seeds, **kw)


def hits(r):
    return {h.symbol_id: h for h in r.hits}


def test_chain_decay():
    g = graph()
    for i in range(2, 7):
        add(g, i, i-1)
    r = run(g)
    assert list(hits(r)) == [1, 2, 3, 4, 5]
    assert [h.weight for h in r.hits] == pytest.approx([1, 1, .8, .64, .512])
    assert hits(r)[5].symbol_path == (1, 2, 3, 4, 5)
    assert r.depth_limited


def test_multisource_deduplicates_and_preserves_seed():
    g = graph()
    add(g, 3, 1)
    add(g, 3, 2, confidence=.5)
    add(g, 4, 3)
    r = run(g, [2, 1, 1])
    assert r.seed_symbol_ids == (1, 2)
    assert list(hits(r)) == [1, 2, 3, 4]
    assert hits(r)[3].seed_symbol_id == 1
    assert hits(r)[4].min_depth == 2


def test_outgoing_is_not_reverse_impact():
    g = graph()
    add(g, 1, 2)
    assert list(hits(run(g))) == [1]


@pytest.mark.parametrize("kind", ["CALLS", "INHERITS", "USES"])
def test_all_propagation_kinds(kind):
    g = graph()
    add(g, 2, 1, kind)
    assert hits(run(g))[2].relationship_path == (kind,)


@pytest.mark.parametrize("kind", ["IMPORTS", "TESTED_BY", "EXPOSES"])
def test_other_edges_do_not_propagate(kind):
    g = graph()
    add(g, 2, 1, kind)
    assert list(hits(run(g))) == [1]


def test_endpoint_chain_no_sibling_or_module_fanout():
    g = graph()
    g.nodes[3]["kind"] = "endpoint"
    g.nodes[4]["kind"] = "module"
    g.nodes[5]["kind"] = "endpoint"
    add(g, 2, 1)
    add(g, 3, 2)
    add(g, 4, 3, "EXPOSES")
    add(g, 4, 5, "EXPOSES")
    add(g, 5, 6)
    r = run(g)
    assert r.affected_endpoint_ids == (3,)
    assert list(hits(r)) == [1, 2, 3]


def test_model_change_reaches_users_and_endpoint():
    g = graph()
    g.nodes[1].update(kind="class", is_database_model=True)
    g.nodes[3]["kind"] = "endpoint"
    add(g, 2, 1, "USES")
    add(g, 3, 2)
    r = run(g)
    assert r.affected_database_model_ids == (1,)
    assert r.affected_endpoint_ids == (3,)


def test_plain_class_is_not_invented_model():
    g = graph()
    g.nodes[1]["kind"] = "class"
    assert run(g).affected_database_model_ids == ()


def test_shortest_and_strongest_paths_differ():
    g = graph()
    add(g, 2, 1, confidence=.1)
    add(g, 3, 1)
    add(g, 2, 3)
    h = hits(run(g))[2]
    assert h.min_depth == 1 and h.depth == 2
    assert h.weight == pytest.approx(.8)


def test_weaker_shorter_path_still_expanded():
    g = graph()
    add(g, 2, 1, confidence=.1)
    add(g, 3, 1)
    add(g, 2, 3)
    add(g, 4, 2)
    add(g, 5, 4)
    add(g, 6, 5)
    assert hits(run(g))[6].depth == 4


def test_cycle_and_self_loop():
    g = graph()
    add(g, 2, 1)
    add(g, 1, 2)
    add(g, 2, 2)
    assert list(hits(run(g))) == [1, 2]


@pytest.mark.parametrize("confidence", [None, math.nan, math.inf, -1, 2, True, "1"])
def test_bad_confidence_is_explicit_gap(confidence):
    g = graph()
    add(g, 2, 1, confidence=confidence)
    r = run(g)
    assert list(hits(r)) == [1]
    assert r.skipped_confidence_edge_ids == (1,)


def test_zero_confidence_is_valid():
    g = graph()
    add(g, 2, 1, confidence=0)
    assert hits(run(g))[2].weight == 0


def test_parallel_edges_best_wins():
    g = graph()
    add(g, 2, 1, confidence=.2)
    add(g, 2, 1, "USES", confidence=.9)
    assert hits(run(g))[2].edge_path == (2,)


def test_deterministic_ties_and_input_order():
    g = graph()
    add(g, 3, 1, eid=10)
    add(g, 2, 1, eid=20)
    add(g, 4, 3, eid=30)
    add(g, 4, 2, eid=40)
    assert hits(run(g))[4].symbol_path == (1, 2, 4)
    other = graph()
    for a,b,k,d in reversed(list(g.edges(keys=True, data=True))):
        other.add_edge(a,b,key=k,**d)
    assert run(g, [2, 1]) == run(other, [1, 2])


def test_file_counts_are_unique():
    g = graph()
    g.nodes[2].update(file_id=1, file_path="f1.py")
    add(g, 2, 1)
    assert run(g).affected_file_ids == (1,)


def test_empty_seed_set():
    assert run(graph(), []).hits == ()


@pytest.mark.parametrize("seed", [999, 0, True, "1"])
def test_invalid_seed(seed):
    with pytest.raises(ValueError):
        run(graph(), [seed])


@pytest.mark.parametrize("field,value", [("repository_id", 2), ("snapshot_id", 20)])
def test_foreign_node_rejected(field,value):
    g = graph()
    g.nodes[8][field] = value
    with pytest.raises(ValueError):
        run(g)


def test_wrong_graph_snapshot_rejected():
    g = graph()
    g.graph["snapshot_id"] = 11
    with pytest.raises(ValueError):
        run(g)


@pytest.mark.parametrize("depth", [0, 9, True, "4"])
def test_depth_validation(depth):
    with pytest.raises(ValueError):
        run(graph(), max_depth=depth)


@pytest.mark.parametrize("decay", [-1, 2, None, math.nan, True])
def test_decay_validation(decay):
    with pytest.raises(ValueError):
        run(graph(), decay=decay)


@pytest.mark.parametrize("options", [{"max_results": 1}, {"max_expansions": 1}])
def test_budget_exhaustion_is_not_partial_success(options):
    g = graph()
    add(g, 2, 1)
    add(g, 3, 1)
    with pytest.raises(TraversalBudgetExceeded):
        run(g, **options)


def test_seed_is_endpoint():
    g = graph()
    g.nodes[1]["kind"] = "endpoint"
    assert run(g).affected_endpoint_ids == (1,)


def test_exposes_metadata_preserved_without_sibling_fanout():
    g = graph()
    g.nodes[2]["kind"] = "endpoint"
    g.nodes[3]["kind"] = "module"
    add(g, 2, 1)
    add(g, 3, 2, "EXPOSES")
    r = run(g)
    assert r.endpoint_exposures[0].module_symbol_id == 3
    assert r.endpoint_exposures[0].endpoint_symbol_id == 2
    assert 3 not in hits(r)


def test_diff_bindings_validate_side_identity():
    from types import SimpleNamespace as NS
    from reposcope.impact.blast_radius import resolve_diff_seeds
    g = graph()
    g.graph["commit_sha"] = "abc"
    g.nodes[1].update(qualname="s1",start_line=1,end_line=2)
    version = NS(local_key="local",path="f1.py",qualname="s1",kind="function",start_line=1,end_line=2)
    report = NS(base_revision="abc",head_revision="def",gaps=(),changes=[NS(base_symbol=version,head_symbol=None)])
    assert resolve_diff_seeds(report,g,"base",{"local":1}).seed_symbol_ids == (1,)
    assert resolve_diff_seeds(report,g,"base",{}).gaps
    with pytest.raises(ValueError):
        resolve_diff_seeds(report,g,"head",{})
    with pytest.raises(ValueError):
        resolve_diff_seeds(report,g,"base",{"local":2})
