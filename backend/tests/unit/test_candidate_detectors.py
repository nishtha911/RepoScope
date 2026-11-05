import pytest
from pydantic import ValidationError
from reposcope.contracts.symbol import Symbol
from reposcope.contracts.edge import Edge
from reposcope.contracts.finding import Finding
from reposcope.recommendations.detectors import (
    CandidateSymbol, CandidateDataset, DetectorConfig, detect_candidates,
)


def row(i, kind="function", **kw):
    return CandidateSymbol(symbol=Symbol(id=i, file_id=1, name=f"s{i}", kind=kind,
        start_line=i, end_line=i), filepath="app.py", is_test=False, **kw)


def edge(a, b, kind="CALLS", confidence=1.0):
    return Edge(source_symbol_id=a, target_symbol_id=b, kind=kind, confidence=confidence)


def data(symbols, edges=(), complete=True):
    return CandidateDataset(repo_id=1, snapshot_id=2, symbols=tuple(symbols),
        edges=tuple(edges), test_links_complete=complete)


def categories(report):
    return [f.category for f in report.findings]


def hot(complete=True, extra=()):
    return data([row(i) for i in range(1, 7)],
        [edge(i, 1) for i in range(2, 7)] + list(extra), complete)


def test_high_fan_in_reuses_contract_and_leaves_score_unset():
    r = detect_candidates(hot())
    assert categories(r) == ["UNTESTED_HOTSPOT"]
    assert Finding.model_validate(r.findings[0].model_dump()).snapshot_id == 2
    assert r.findings[0].score is None and r.findings[0].confidence is None
    assert r.evidence[0].related_symbol_ids == (2, 3, 4, 5, 6)


def test_incomplete_index_is_gap_not_finding():
    r = detect_candidates(hot(False))
    assert not r.findings
    assert "TEST_LINKS_INCOMPLETE" in [g.code for g in r.gaps]


@pytest.mark.parametrize("confidence", [None, 0.0, 0.2, 1.0])
def test_any_test_association_blocks_absence(confidence):
    assert not detect_candidates(hot(extra=[edge(1, 2, "TESTED_BY", confidence)])).findings


def test_reversed_test_link_does_not_block():
    assert "UNTESTED_HOTSPOT" in categories(detect_candidates(hot(extra=[edge(2, 1, "TESTED_BY")])))


def test_duplicate_callers_and_recursion_not_counted():
    d = data([row(1), row(2)], [edge(2, 1)] * 8 + [edge(1, 1)])
    assert not detect_candidates(d).findings


@pytest.mark.parametrize("confidence", [None, 0.0, 0.49])
def test_low_or_unknown_confidence_calls_excluded(confidence):
    d = data([row(1), row(2)], [edge(2, 1, confidence=confidence)])
    assert not detect_candidates(d, DetectorConfig(min_fan_in=1)).findings


@pytest.mark.parametrize("value,expected", [(9, False), (10, True), (11, True)])
def test_complexity_threshold(value, expected):
    r = detect_candidates(data([row(1, cyclomatic_complexity=value, complexity_policy="python_v1")]))
    assert ("COMPLEXITY_HOTSPOT" in categories(r)) == expected


def test_missing_complexity_is_gap():
    assert detect_candidates(data([row(1)])).gaps[0].code == "COMPLEXITY_UNKNOWN"


@pytest.mark.parametrize("doc,expected", [(None, True), ("", True), ("  ", True), ("Documented", False)])
def test_doc_policy(doc, expected):
    d = data([row(1, "endpoint"), row(2, docstring=doc, documentation_known=True)], [edge(1, 2)])
    assert ("API_DOC_GAP" in categories(detect_candidates(d))) == expected


def test_unknown_docs_not_missing():
    r = detect_candidates(data([row(1, "endpoint"), row(2)], [edge(1, 2)]))
    assert not r.findings
    assert "DOCUMENTATION_UNKNOWN" in [g.code for g in r.gaps]


@pytest.mark.parametrize("links", [[], [edge(1, 2), edge(1, 3)]])
def test_missing_or_ambiguous_handler(links):
    r = detect_candidates(data([row(1, "endpoint"), row(2), row(3)], links))
    assert "ENDPOINT_HANDLER_UNKNOWN" in [g.code for g in r.gaps]


def test_order_independent():
    d = hot()
    backward = data(list(reversed(d.symbols)), list(reversed(d.edges)))
    assert detect_candidates(d) == detect_candidates(backward)


def test_foreign_edge_rejected():
    with pytest.raises(ValidationError):
        data([row(1)], [edge(1, 99)])


def test_duplicate_symbols_rejected():
    with pytest.raises(ValidationError):
        data([row(1), row(1)])


def test_unpaired_complexity_rejected():
    with pytest.raises(ValidationError):
        row(1, cyclomatic_complexity=10)


def test_doc_known_flag_required():
    with pytest.raises(ValidationError):
        row(1, docstring="hello")


@pytest.mark.parametrize("value", [0, -1, True])
def test_threshold_validation(value):
    with pytest.raises(ValidationError):
        DetectorConfig(min_fan_in=value)


def test_test_callable_excluded():
    r = row(1, cyclomatic_complexity=20, complexity_policy="v1").model_copy(update={"is_test": True})
    assert not detect_candidates(data([r])).findings


def test_unknown_test_role_excluded():
    r = row(1).model_copy(update={"is_test": None})
    report = detect_candidates(data([r]))
    assert not report.findings and report.gaps[0].code == "TEST_ROLE_UNKNOWN"
