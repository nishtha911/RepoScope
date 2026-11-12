import networkx as nx
import pytest
from reposcope.impact.test_gap import analyze_test_gaps


def graph():
    g=nx.MultiDiGraph(repository_id=1,snapshot_id=10)
    for sid,kind in [(1,'function'),(2,'method'),(3,'function'),(4,'class')]:
        g.add_node(sid,repository_id=1,snapshot_id=10,kind=kind)
    return g


def run(g,ids=(1,),complete=True,roles=None):
    return analyze_test_gaps(g,1,10,ids,test_links_complete=complete,
        symbol_roles={1:'production',2:'production',3:'test'} if roles is None else roles)


def add(g,a=1,b=3,kind='TESTED_BY',confidence=1.0):
    g.add_edge(a,b,key=1,edge_id=1,kind=kind,confidence=confidence)


def test_absence_in_complete_index():
    r=run(graph())
    assert r.untested_modified_symbol_ids==(1,) and r.gap_ratio==1
    assert 'static' in r.items[0].reason


def test_linked_has_evidence():
    g=graph();add(g)
    r=run(g)
    assert r.items[0].status=='LINKED' and r.gap_ratio==0
    assert r.items[0].test_symbol_ids==(3,) and r.items[0].edge_ids==(1,)


def test_incomplete_absence_is_unknown():
    r=run(graph(),complete=False)
    assert r.gap_ratio is None and r.unknown_symbol_ids==(1,)
    assert not r.untested_modified_symbol_ids


def test_link_presence_does_not_require_complete_index():
    g=graph();add(g)
    assert run(g,complete=False).items[0].status=='LINKED'


@pytest.mark.parametrize('confidence',[None,0,-1,2,float('nan'),True])
def test_bad_or_zero_association_blocks_absence(confidence):
    g=graph();add(g,confidence=confidence)
    assert run(g).items[0].status=='UNKNOWN'


def test_unknown_target_role_is_not_coverage_or_absence():
    g=graph();add(g,b=2)
    assert run(g).items[0].status=='UNKNOWN'


def test_reverse_edge_is_not_test_link():
    g=graph();add(g,a=3,b=1)
    assert run(g).gap_ratio==1


def test_test_functions_and_classes_excluded():
    r=run(graph(),ids=(3,4))
    assert all(x.status=='NOT_APPLICABLE' for x in r.items) and r.gap_ratio==0


def test_unknown_production_role():
    assert run(graph(),roles={}).items[0].status=='UNKNOWN'


def test_duplicates_and_order():
    assert run(graph(),ids=(2,1,1))==run(graph(),ids=(1,2))


def test_partial_associations_ratio():
    g=graph();add(g)
    assert run(g,ids=(1,2)).gap_ratio==.5


@pytest.mark.parametrize('ids',[(999,),(True,),(0,),('1',)])
def test_invalid_seed(ids):
    with pytest.raises(ValueError):run(graph(),ids)


def test_foreign_node_rejected():
    g=graph();g.nodes[3]['snapshot_id']=11
    with pytest.raises(ValueError):run(g)


def test_foreign_role_rejected():
    with pytest.raises(ValueError):run(graph(),roles={999:'test'})
