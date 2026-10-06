import pytest
from pydantic import ValidationError

from reposcope.contracts.chunk import Chunk


def chunk_data():
    return {
        "snapshot_id": 1,
        "file_id": 2,
        "symbol_id": 10,
        "start_line": 20,
        "end_line": 21,
        "text": (
            "def verify_payment(signature):\n"
            "    return signature == 'valid'\n"
        ),
    }


def test_valid_chunk():
    chunk = Chunk(**chunk_data())

    assert chunk.id is None
    assert chunk.symbol_id == 10
    assert chunk.model_dump()["snapshot_id"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_id": 0},
        {"file_id": 0},
        {"symbol_id": 0},
        {"start_line": 0},
        {"end_line": 0},
        {"end_line": 19},
        {"text": ""},
        {"text": "   \n\t"},
    ],
)
def test_invalid_chunk(changes):
    data = chunk_data()
    data.update(changes)

    with pytest.raises(ValidationError):
        Chunk(**data)


def test_text_whitespace_is_preserved():
    text = "    return True\n\n"
    data = chunk_data()
    data["text"] = text

    chunk = Chunk(**data)

    assert chunk.text == text


def test_snapshot_id_is_required():
    data = chunk_data()
    del data["snapshot_id"]

    with pytest.raises(ValidationError):
        Chunk(**data)


def test_unknown_field_is_rejected():
    data = chunk_data()
    data["unexpected_field"] = "something"

    with pytest.raises(ValidationError):
        Chunk(**data)