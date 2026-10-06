import pytest
from pydantic import ValidationError

from repolens.contracts.symbol import Symbol


def symbol_data():
    return {
        "file_id": 1,
        "name": "verify_payment",
        "kind": "function",
        "start_line": 20,
        "end_line": 38,
    }


def test_valid_symbol():
    symbol = Symbol(**symbol_data())

    assert symbol.id is None
    assert symbol.name == "verify_payment"
    assert symbol.model_dump()["file_id"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"file_id": 0},
        {"name": "   "},
        {"start_line": 0},
        {"end_line": 19},
    ],
)
def test_invalid_symbol(changes):
    data = symbol_data()
    data.update(changes)

    with pytest.raises(ValidationError):
        Symbol(**data)


def test_unknown_field_is_rejected():
    data = symbol_data()
    data["unexpected_field"] = "something"

    with pytest.raises(ValidationError):
        Symbol(**data)