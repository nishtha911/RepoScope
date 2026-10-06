import pytest
from pydantic import ValidationError

from repolens.contracts.edge import Edge


def edge_data():
    return {
        "source_symbol_id": 11,
        "target_symbol_id": 10,
        "kind": "CALLS",
    }


def test_valid_edge():
    edge = Edge(**edge_data())

    assert edge.id is None
    assert edge.confidence is None
    assert edge.source_symbol_id == 11
    assert edge.target_symbol_id == 10
    assert edge.model_dump()["kind"] == "CALLS"


@pytest.mark.parametrize(
    "changes",
    [
        {"source_symbol_id": 0},
        {"target_symbol_id": 0},
        {"kind": "   "},
        {"confidence": -0.1},
        {"confidence": 1.1},
    ],
)
def test_invalid_edge(changes):
    data = edge_data()
    data.update(changes)

    with pytest.raises(ValidationError):
        Edge(**data)


@pytest.mark.parametrize("confidence", [0.0, 0.8, 1.0])
def test_valid_confidence(confidence):
    edge = Edge(**edge_data(), confidence=confidence)

    assert edge.confidence == confidence


def test_recursive_call_is_allowed():
    edge = Edge(
        source_symbol_id=10,
        target_symbol_id=10,
        kind="CALLS",
    )

    assert edge.source_symbol_id == edge.target_symbol_id


def test_unknown_field_is_rejected():
    data = edge_data()
    data["unexpected_field"] = "something"

    with pytest.raises(ValidationError):
        Edge(**data)