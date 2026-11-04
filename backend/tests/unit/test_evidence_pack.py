import json

import pytest
from pydantic import ValidationError

from reposcope.contracts.evidence import Evidence
from reposcope.rag.evidence_pack import (
    ContextSymbol, EvidenceCandidate, EvidencePack, EvidencePath,
    build_evidence_pack, citation_map, render_evidence_pack, serialize_evidence_pack,
)


def candidate(chunk=11,order=0,**changes):
    data = dict(repository_id=1,snapshot_id=2,file_id=3,file_path="app.py",
                symbol_id=chunk,chunk_id=chunk,start_line=10,end_line=11,
                text="def work():\n    return 'λ'\n",name="work",qualname="work",
                kind="function",signature="def work():",origin="seed",order=order,fused_score=.1)
    data.update(changes)
    return EvidenceCandidate(**data)


def build(candidates,**kwargs):
    return build_evidence_pack(candidates,repository_id=1,snapshot_id=2,**kwargs)


def test_reuses_existing_contract_and_preserves_body():
    item = candidate()
    pack = build([item])
    assert isinstance(pack.entries[0].source,Evidence)
    assert pack.entries[0].source.text == item.text
    assert pack.entries[0].source.evidence_id == "E1"


def test_deterministic_ids_and_input_order_independence():
    a,b = candidate(11,1),candidate(12,0)
    first,second = build([a,b]),build([b,a])
    assert serialize_evidence_pack(first) == serialize_evidence_pack(second)
    assert [entry.source.chunk_id for entry in first.entries] == [12,11]
    assert list(citation_map(first)) == ["E1","E2"]


def test_identical_duplicates_collapse_and_conflicts_raise():
    a = candidate()
    assert len(build([a,a]).entries) == 1
    with pytest.raises(ValueError):
        build([a,candidate(name="different")])


@pytest.mark.parametrize("changes", [{"repository_id":2},{"snapshot_id":3}])
def test_mixed_scope_rejected(changes):
    with pytest.raises(ValueError):
        build([candidate(**changes)])


def test_full_json_round_trip():
    pack = build([candidate()],commit_sha="a"*40)
    assert EvidencePack.model_validate_json(serialize_evidence_pack(pack)) == pack


def test_metadata_only_nodes_are_not_citations():
    node = ContextSymbol(symbol_id=99,file_id=3,snapshot_id=2,file_path="app.py",
                         name="GET /users",qualname=None,kind="endpoint",is_seed=False)
    pack = build([],context_symbols=(node,))
    assert citation_map(pack) == {}
    assert "NOT SOURCE CITATIONS" in render_evidence_pack(pack)
    assert "GET /users" in render_evidence_pack(pack)


def test_entry_budget_has_contiguous_ids_and_gap():
    pack = build([candidate(11,0),candidate(12,1)],max_entries=1)
    assert list(citation_map(pack)) == ["E1"]
    assert pack.truncated and "max_entries" in pack.truncation_reasons


def test_source_budget_omits_whole_chunks_not_body_slices():
    pack = build([candidate()],max_source_chars=1)
    assert not pack.entries
    assert "max_source_chars" in pack.truncation_reasons
    assert "[GAP]" in render_evidence_pack(pack)


def test_smaller_later_chunk_can_fit_budget():
    large = candidate(text="def work():\n    return '" + "x"*100 + "'\n")
    small = candidate(12,1)
    pack = build([large,small],max_source_chars=60)
    assert len(pack.entries) == 1
    assert pack.entries[0].source.chunk_id == 12
    assert pack.entries[0].source.evidence_id == "E1"


def test_upstream_truncation_and_gaps_are_preserved():
    pack = build([candidate()],gaps=("Missing chunk",),truncation_reasons=("max_expansions",))
    assert pack.truncated and "Missing chunk" in pack.gaps
    assert "max_expansions" in render_evidence_pack(pack)


def test_empty_pack_is_explicit():
    pack = build([])
    assert not pack.entries and not pack.truncated
    assert any("No citable" in gap for gap in pack.gaps)


def test_code_fence_cannot_close_on_existing_backticks():
    source = "def work():\n    return '```'\n"
    text = render_evidence_pack(build([candidate(text=source)]))
    assert "````python" in text and source in text


def test_expansion_paths_preserve_direction_ids_confidence():
    path = EvidencePath(seed_symbol_id=1,symbol_ids=(1,11),edge_ids=(8,),
                        edge_kinds=("CALLS",),directions=("incoming",),confidence=.8)
    pack = build([candidate(origin="expanded",fused_score=None,paths=(path,))])
    assert pack.entries[0].paths[0] == path
    assert citation_map(pack)["E1"]["paths"][0]["edge_ids"] == [8]


@pytest.mark.parametrize("changes", [
    {"file_path":"../app.py"},{"file_path":"C:/app.py"},{"end_line":12},
    {"text":"  "},{"symbol_id":True},{"fused_score":float("nan")},
    {"signature":" "},{"origin":"expanded"},
])
def test_invalid_candidates(changes):
    with pytest.raises(ValidationError):
        candidate(**changes)


@pytest.mark.parametrize("kwargs", [{"max_entries":0},{"max_source_chars":False}])
def test_invalid_budgets(kwargs):
    with pytest.raises(ValueError):
        build([candidate()],**kwargs)


def test_mutated_nested_evidence_is_revalidated():
    pack = build([candidate()])
    pack.entries[0].source.evidence_id = "E999"
    with pytest.raises(ValidationError):
        serialize_evidence_pack(pack)
