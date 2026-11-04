from dataclasses import dataclass
import json
from types import SimpleNamespace as NS

import pytest

from reposcope.rag import pipeline
from reposcope.rag.evidence_pack import citation_map
from reposcope.rag.prompts import build_spotlighted_messages


@dataclass(frozen=True)
class Path:
    seed_symbol_id: int = 1
    symbol_ids: tuple = (1,2)
    edge_ids: tuple = (10,)
    edge_kinds: tuple = ("CALLS",)
    directions: tuple = ("outgoing",)
    confidence: float = .9


def metadata(symbol):
    return dict(symbol_id=symbol,name=f"f{symbol}",qualname=f"f{symbol}",kind="function",
                start_line=10,end_line=11,file_id=3,file_path="app.py",repository_id=1,snapshot_id=2)


def raw(symbol):
    return json.dumps(dict(file_path="app.py",qualname=f"f{symbol}",kind="function",signature=f"def f{symbol}():",docstring=None)) + pipeline.SOURCE_SEPARATOR + f"def f{symbol}():\n    return {symbol}\n"


@pytest.fixture
def setup(monkeypatch):
    rows = {i:metadata(i) for i in (1,2)}
    chunks = {i:dict(chunk_id=i,symbol_id=i,repo_id=1,text=raw(i)) for i in (1,2)}
    expansion = NS(repository_id=1,seeds=(NS(symbol_id=1,chunk_id=1,fused_score=.1),),
        symbols=(NS(symbol_id=2,name="f2",kind="function",file_path="app.py",paths=(Path(),)),),
        gaps=(),truncated=False,truncation_reasons=())
    result = NS(expansion=expansion,context_chunks=tuple(
        NS(chunk_id=i,symbol_id=i,repo_id=1,text=raw(i),is_seed=i==1) for i in (1,2)))
    monkeypatch.setattr(pipeline,"_snapshot",lambda *args:dict(status="ready",commit_sha="a"*40))
    monkeypatch.setattr(pipeline,"_symbols",lambda session,ids:[rows[i] for i in sorted(ids) if i in rows])
    monkeypatch.setattr(pipeline,"_chunks",lambda session,ids:[chunks[i] for i in sorted(ids) if i in chunks])
    return result,rows,chunks


def test_adapter_to_prompt_end_to_end_without_providers(setup):
    result,_,_ = setup
    pack = pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)
    assert list(citation_map(pack)) == ["E1","E2"]
    assert pack.entries[0].source.text == "def f1():\n    return 1\n"
    assert pack.entries[1].paths[0].edge_ids == (10,)
    assert pack.entries[1].source.start_line == 10
    assert "[E2]" in build_spotlighted_messages("Explain",pack)[0]["content"]


def test_decorated_body_gets_correct_content_start():
    row = metadata(1)
    body = "@decorate\ndef f1():\n    return 1\n"
    aligned = pipeline._source_parts(body,row)
    assert aligned[2:4] == (9,11)
    assert aligned[0] == body


def test_indented_method_body_is_preserved():
    row = metadata(1)
    row["kind"] = "method"
    body = "    def f1():\n        return 1\n"
    assert pipeline._source_parts(body,row)[0] == body


def test_null_snapshot_becomes_gap_not_invented_identity(setup):
    result,rows,_ = setup
    rows[1]["snapshot_id"] = None
    pack = pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)
    assert not pack.entries
    assert any("no verified snapshot" in gap for gap in pack.gaps)


@pytest.mark.parametrize("change", [{"repository_id":2},{"snapshot_id":3}])
def test_foreign_scope_rejected(setup,change):
    result,rows,_ = setup
    rows[2].update(change)
    with pytest.raises(ValueError):
        pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)


def test_stale_chunk_rejected(setup):
    result,_,chunks = setup
    chunks[1]["text"] = "changed"
    with pytest.raises(ValueError,match="rerun retrieval"):
        pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)


def test_missing_chunk_is_gap(setup):
    result,_,chunks = setup
    del chunks[2]
    pack = pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)
    assert len(pack.entries) == 1
    assert len(pack.context_symbols) == 2
    assert any("no longer stored" in gap for gap in pack.gaps)


def test_unalignable_source_becomes_gap(setup):
    result,rows,_ = setup
    rows[1]["end_line"] = 100
    pack = pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)
    assert any("unverifiable" in gap for gap in pack.gaps)
    assert [entry.source.symbol_id for entry in pack.entries] == [2]


def test_unready_snapshot_rejected(setup,monkeypatch):
    result,_,_ = setup
    monkeypatch.setattr(pipeline,"_snapshot",lambda *args:dict(status="pending",commit_sha="a"*40))
    with pytest.raises(ValueError,match="ready snapshot"):
        pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)


def test_context_repo_mismatch_rejected(setup):
    result,_,_ = setup
    result.context_chunks[0].repo_id = 2
    with pytest.raises(ValueError):
        pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)


def test_upstream_budget_survives_adapter(setup):
    result,_,_ = setup
    result.expansion.truncated = True
    result.expansion.truncation_reasons = ("max_expansions",)
    pack = pipeline.assemble_evidence_pack(object(),result,snapshot_id=2)
    assert pack.truncated and "max_expansions" in pack.truncation_reasons
