"""Pure citation validation tests; no model, provider, DB, or network work."""
from copy import deepcopy

import pytest

from reposcope.rag.evidence_pack import EvidenceCandidate, build_evidence_pack
from reposcope.rag.validator import ANSWER_SCHEMA, CitationValidationError, validate_answer

SOURCE = "def get_hmm():\n    \"\"\"Get a thought.\"\"\"\n    return 'hmmm...'\n"


@pytest.fixture
def pack():
    candidate = EvidenceCandidate(repository_id=33, snapshot_id=9, file_id=11,
        file_path="sample/core.py", symbol_id=75, chunk_id=101,
        start_line=5, end_line=7, text=SOURCE, name="get_hmm", qualname="get_hmm",
        kind="function", signature="def get_hmm():", origin="seed", order=0)
    return build_evidence_pack([candidate], repository_id=33, snapshot_id=9,
        commit_sha="d469f2f5e0a472be2c7d95ff90ed46e975810dc8")


@pytest.fixture
def draft():
    return {"claims": [{"text": "get_hmm returns the string 'hmmm...'.", "citations": [
        {"evidence_id": "E1", "quote": "return 'hmmm...'"}]}],
        "gaps": [], "insufficient_evidence": False}


def test_valid_claim_is_rendered_with_pack_owned_source(draft, pack):
    result = validate_answer(draft, pack)
    assert result.answer == "get_hmm returns the string 'hmmm...'. [E1]"
    assert len(result.evidence) == 1 and result.evidence[0].symbol_id == 75
    assert result.evidence[0].snapshot_id == 9
    assert result.evidence[0].start_line == 5 and result.evidence[0].end_line == 7
    assert result.evidence[0].file_path == "sample/core.py"
    assert result.evidence[0].text == SOURCE
    assert not result.insufficient_evidence


def test_unknown_citation_is_rejected(draft, pack):
    draft["claims"][0]["citations"][0]["evidence_id"] = "E99"
    with pytest.raises(CitationValidationError, match="not in"):
        validate_answer(draft, pack)


@pytest.mark.parametrize("quote", ["return 'invented'", "RETURN 'hmmm...'", "Get a thought without punctuation"])
def test_wrong_quote_is_rejected(draft, pack, quote):
    draft["claims"][0]["citations"][0]["quote"] = quote
    with pytest.raises(CitationValidationError, match="does not match"):
        validate_answer(draft, pack)


@pytest.mark.parametrize("quote", ["", "return", "        ", "--------"])
def test_trivial_quote_is_rejected(draft, pack, quote):
    draft["claims"][0]["citations"][0]["quote"] = quote
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_uncited_claim_is_rejected(draft, pack):
    draft["claims"][0]["citations"] = []
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


@pytest.mark.parametrize("text", ["", " ", "Some claim [E1]", "Some claim [E999]"])
def test_blank_or_inline_citation_text_is_rejected(draft, pack, text):
    draft["claims"][0]["text"] = text
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_fabricated_source_metadata_is_rejected(draft, pack):
    draft["claims"][0]["citations"][0]["file_path"] = "invented.py"
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_unchecked_answer_field_is_rejected(draft, pack):
    draft["answer"] = "unchecked model paragraph"
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_duplicate_citation_is_rejected(draft, pack):
    draft["claims"][0]["citations"].append(deepcopy(draft["claims"][0]["citations"][0]))
    with pytest.raises(CitationValidationError, match="Duplicate"):
        validate_answer(draft, pack)


def test_empty_affirmative_answer_is_rejected(draft, pack):
    draft["claims"] = []
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_empty_pack_requires_insufficiency(draft):
    empty = build_evidence_pack([], repository_id=33, snapshot_id=9)
    with pytest.raises(CitationValidationError):
        validate_answer(draft, empty)
    result = validate_answer({"claims": [], "gaps": [], "insufficient_evidence": True}, empty)
    assert result.insufficient_evidence and not result.evidence
    assert "insufficient" in result.answer and result.gaps


def test_insufficiency_cannot_hide_factual_claims(draft, pack):
    draft["insufficient_evidence"] = True
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_insufficiency_without_gap_gets_server_owned_explanation(pack):
    result = validate_answer({"claims": [], "gaps": [], "insufficient_evidence": True}, pack)
    assert result.gaps and result.evidence == ()


@pytest.mark.parametrize("gap", ["", " ", "x" * 1001, "Unsupported [E9]"])
def test_invalid_gaps_are_rejected(draft, pack, gap):
    draft["gaps"] = [gap]
    with pytest.raises(CitationValidationError):
        validate_answer(draft, pack)


def test_cached_draft_must_match_current_pack(draft, pack):
    assert validate_answer(draft, pack).evidence
    changed = pack.model_copy(update={"entries": ()})
    with pytest.raises(CitationValidationError):
        validate_answer(draft, changed)


def test_input_records_are_not_mutated(draft, pack):
    before_draft = deepcopy(draft)
    before_pack = pack.model_dump()
    validate_answer(draft, pack)
    assert draft == before_draft and pack.model_dump() == before_pack


def test_exact_quote_is_not_a_semantic_truth_guarantee(draft, pack):
    # This limitation is intentional and explicit: matching source text is not
    # an entailment test. A separate groundedness evaluation must catch this.
    draft["claims"][0]["text"] = "get_hmm returns False."
    assert validate_answer(draft, pack).answer.startswith("get_hmm returns False.")


def test_schema_is_closed_and_requires_all_top_level_fields():
    assert ANSWER_SCHEMA["additionalProperties"] is False
    assert set(ANSWER_SCHEMA["required"]) == {"claims", "gaps", "insufficient_evidence"}
