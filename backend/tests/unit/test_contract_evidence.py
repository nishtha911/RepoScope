import pytest
from pydantic import ValidationError

from reposcope.contracts.evidence import Evidence


def evidence_data():
    return {
        "evidence_id": "E1",
        "snapshot_id": 1,
        "file_id": 2,
        "file_path": "payments.py",
        "start_line": 20,
        "end_line": 21,
        "text": (
            "def verify_payment(signature):\n"
            "    return signature == 'valid'\n"
        ),
    }


def test_valid_evidence():
    evidence = Evidence(**evidence_data())

    assert evidence.evidence_id == "E1"
    assert evidence.symbol_id is None
    assert evidence.chunk_id is None
    assert evidence.model_dump()["file_path"] == "payments.py"


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_id": "E0"},
        {"snapshot_id": 0},
        {"file_id": 0},
        {"file_path": "   "},
        {"symbol_id": 0},
        {"chunk_id": 0},
        {"start_line": 0},
        {"end_line": 19},
        {"text": ""},
        {"text": "   \n\t"},
    ],
)
def test_invalid_evidence(changes):
    data = evidence_data()
    data.update(changes)

    with pytest.raises(ValidationError):
        Evidence(**data)


def test_source_text_is_preserved():
    text = "    return True\n\n"
    data = evidence_data()
    data["text"] = text

    evidence = Evidence(**data)

    assert evidence.text == text


def test_unknown_field_is_rejected():
    data = evidence_data()
    data["unexpected_field"] = "something"

    with pytest.raises(ValidationError):
        Evidence(**data)