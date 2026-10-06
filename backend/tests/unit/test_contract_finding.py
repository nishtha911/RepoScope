import pytest
from pydantic import ValidationError

from repolens.contracts.finding import Finding


def finding_data():
    return {
        "snapshot_id": 1,
        "symbol_id": 10,
        "file_id": 2,
        "category": "missing_linked_tests",
        "title": "Payment verification has no linked tests",
        "description": (
            "No linked tests were found for verify_payment "
            "in the indexed graph."
        ),
    }


def test_valid_finding():
    finding = Finding(**finding_data())

    assert finding.id is None
    assert finding.score is None
    assert finding.confidence is None
    assert finding.model_dump()["symbol_id"] == 10


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 0},
        {"snapshot_id": 0},
        {"symbol_id": 0},
        {"file_id": 0},
        {"category": "   "},
        {"title": "   "},
        {"description": "   "},
        {"score": -0.1},
        {"confidence": 1.1},
    ],
)
def test_invalid_finding(changes):
    data = finding_data()
    data.update(changes)

    with pytest.raises(ValidationError):
        Finding(**data)


@pytest.mark.parametrize("confidence", [0.0, 0.8, 1.0])
def test_valid_confidence(confidence):
    finding = Finding(**finding_data(), confidence=confidence)

    assert finding.confidence == confidence


def test_unknown_field_is_rejected():
    data = finding_data()
    data["unexpected_field"] = "something"

    with pytest.raises(ValidationError):
        Finding(**data)