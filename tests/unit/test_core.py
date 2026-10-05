from backend.app.core.graph import reachable_nodes
from backend.app.core.parser import parse_python
from backend.app.retrieval.chunker import chunk_python
from backend.app.retrieval.hybrid import reciprocal_rank_fusion
from backend.app.retrieval.validator import validate_citations


def test_parser_extracts_top_level_symbols():
    result = parse_python("def run():\n    return 1\n\nclass Job:\n    pass\n", "worker")
    assert [symbol.qualified_name for symbol in result] == ["worker.run", "worker.Job"]


def test_chunker_preserves_symbol_source():
    chunks = chunk_python("def run():\n    return 1\n")
    assert len(chunks) == 1
    assert chunks[0].text == "def run():\n    return 1"


def test_rrf_combines_rankings():
    result = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    assert result[0][1] == result[1][1]


def test_graph_traversal_respects_depth():
    assert reachable_nodes([("a", "b"), ("b", "c")], "a", max_depth=1) == {
        "a": 0,
        "b": 1,
    }


def test_citation_validator_rejects_unknown_evidence():
    assert not validate_citations("Claim [E2]", {"E1"})