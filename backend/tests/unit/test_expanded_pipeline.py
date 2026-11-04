from types import SimpleNamespace

import networkx as nx
import pytest

from reposcope.retrieval import expanded_pipeline as pipeline


def hit(symbol=1,chunk=1,score=1):
    return SimpleNamespace(symbol_id=symbol,chunk_id=chunk,repo_id=1,score=score,text=f"code {symbol}")


def graph():
    g = nx.MultiDiGraph(repository_id=1)
    for node in (1,2,3):
        g.add_node(node,repository_id=1,name=f"n{node}",qualname=f"n{node}",kind="function",file_path="app.py")
    g.add_edge(1,2,key=1,edge_id=1,kind="CALLS",confidence=1)
    return g


def test_preserves_hybrid_hits_and_hydrates_context(monkeypatch):
    original = [hit(),hit(3,3,.5)]
    monkeypatch.setattr(pipeline,"_hybrid_search",lambda *args,**kwargs: original)
    monkeypatch.setattr(pipeline,"_load_graph",lambda *args: graph())
    monkeypatch.setattr(pipeline,"_fetch_chunks",lambda *args: [dict(chunk_id=2,symbol_id=2,repo_id=1,text="callee")])
    result = pipeline.search_chunks_hybrid_expanded(object(),1,"query",intent="implementation")
    assert result.hybrid_hits == tuple(original)
    assert [s.symbol_id for s in result.expansion.seeds] == [1,3]
    assert [(c.symbol_id,c.is_seed) for c in result.context_chunks] == [(1,True),(3,True),(2,False)]
    assert not result.expansion.gaps


def test_no_chunk_is_explicit_metadata_only_gap(monkeypatch):
    monkeypatch.setattr(pipeline,"_hybrid_search",lambda *args,**kwargs: [hit()])
    monkeypatch.setattr(pipeline,"_load_graph",lambda *args: graph())
    monkeypatch.setattr(pipeline,"_fetch_chunks",lambda *args: [])
    result = pipeline.search_chunks_hybrid_expanded(object(),1,"query",intent="implementation")
    assert "metadata only" in result.expansion.gaps[0]
    assert len(result.context_chunks) == 1


def test_empty_query_does_no_database_work(monkeypatch):
    def fail(*args,**kwargs):
        raise AssertionError("Should not query")
    monkeypatch.setattr(pipeline,"_hybrid_search",fail)
    monkeypatch.setattr(pipeline,"_load_graph",fail)
    monkeypatch.setattr(pipeline,"_fetch_chunks",fail)
    result = pipeline.search_chunks_hybrid_expanded(object(),1,"  ",intent="callers")
    assert result.hybrid_hits == result.context_chunks == ()


def test_empty_hybrid_results_do_not_load_graph(monkeypatch):
    monkeypatch.setattr(pipeline,"_hybrid_search",lambda *args,**kwargs: [])
    def fail(*args):
        raise AssertionError("Should not load graph")
    monkeypatch.setattr(pipeline,"_load_graph",fail)
    assert not pipeline.search_chunks_hybrid_expanded(object(),1,"q",intent="callers").expansion.seeds


def test_retriever_failure_propagates(monkeypatch):
    def fail(*args,**kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(pipeline,"_hybrid_search",fail)
    with pytest.raises(RuntimeError,match="provider unavailable"):
        pipeline.search_chunks_hybrid_expanded(object(),1,"q",intent="callers")


def test_loader_failure_propagates(monkeypatch):
    monkeypatch.setattr(pipeline,"_hybrid_search",lambda *args,**kwargs: [hit()])
    def fail(*args):
        raise RuntimeError("graph load budget")
    monkeypatch.setattr(pipeline,"_load_graph",fail)
    with pytest.raises(RuntimeError,match="graph load budget"):
        pipeline.search_chunks_hybrid_expanded(object(),1,"q",intent="callers")


def test_hydration_rejects_other_repository(monkeypatch):
    monkeypatch.setattr(pipeline,"_hybrid_search",lambda *args,**kwargs: [hit()])
    monkeypatch.setattr(pipeline,"_load_graph",lambda *args: graph())
    monkeypatch.setattr(pipeline,"_fetch_chunks",lambda *args: [dict(chunk_id=2,symbol_id=2,repo_id=2,text="foreign")])
    with pytest.raises(ValueError):
        pipeline.search_chunks_hybrid_expanded(object(),1,"q",intent="implementation")


@pytest.mark.parametrize("options", [
    {"limit":101},{"limit":True},{"candidate_limit":1},{"seed_limit":9},{"max_depth":3},{"k":0},
])
def test_invalid_options_rejected_before_search(options):
    with pytest.raises(ValueError):
        pipeline.search_chunks_hybrid_expanded(object(),1,"q",intent="callers",**options)
