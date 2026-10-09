import json
from hashlib import sha256

import pytest
from pydantic import ValidationError

from reposcope.contracts.chunking import (
    ChunkDraft,
    SOURCE_SEPARATOR,
)


@pytest.fixture
def chunk_data():
    """Explicit test data, not output from the real chunker."""
    body = (
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b"
    )

    header = json.dumps(
        {
            "file_path": "sample.py",
            "qualname": "add",
            "kind": "function",
            "signature": "def add(a: int, b: int) -> int:",
            "docstring": "Add two numbers.",
        },
        ensure_ascii=False,
        indent=2,
    )

    digest = sha256(body.encode("utf-8")).hexdigest()

    return {
        "symbol_key": '["sample.py","function","add",0]',
        "file_path": "sample.py",
        "source_sha256": digest,
        "parse_buffer_sha256": digest,
        "qualname": "add",
        "kind": "function",
        "start_line": 1,
        "end_line": 3,
        "header_text": header,
        "body_text": body,
        "text": header + SOURCE_SEPARATOR + body,
    }


def test_valid_chunk_draft(chunk_data):
    chunk = ChunkDraft(**chunk_data)

    assert chunk.schema_version == 1
    assert chunk.qualname == "add"
    assert chunk.kind == "function"
    assert chunk.body_text == chunk_data["body_text"]

    payload = chunk.model_dump()

    assert "snapshot_id" not in payload
    assert "file_id" not in payload
    assert "symbol_id" not in payload


def test_source_whitespace_is_preserved(chunk_data):
    body = (
        "    def run(self):\r\n"
        "\r\n"
        "        return 1  "
    )

    chunk_data["body_text"] = body
    chunk_data["text"] = (
        chunk_data["header_text"]
        + SOURCE_SEPARATOR
        + body
    )

    chunk = ChunkDraft(**chunk_data)

    assert chunk.body_text == body
    assert chunk.body_text.startswith("    ")
    assert "\r\n" in chunk.body_text
    assert chunk.body_text.endswith("  ")


def test_blank_body_is_rejected(chunk_data):
    chunk_data["body_text"] = " \n\t"
    chunk_data["text"] = (
        chunk_data["header_text"]
        + SOURCE_SEPARATOR
        + chunk_data["body_text"]
    )

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)


def test_reversed_line_range_is_rejected(chunk_data):
    chunk_data["start_line"] = 5
    chunk_data["end_line"] = 2

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)


@pytest.mark.parametrize(
    "field",
    ["source_sha256", "parse_buffer_sha256"],
)
def test_invalid_hash_format_is_rejected(chunk_data, field):
    chunk_data[field] = "not-a-sha256"

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)


def test_unknown_fields_are_rejected(chunk_data):
    chunk_data["unexpected_field"] = "value"

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)


def test_inconsistent_assembled_text_is_rejected(chunk_data):
    chunk_data["text"] = "Unrelated text"

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)


def test_ineligible_kind_is_rejected(chunk_data):
    chunk_data["kind"] = "parameter"

    with pytest.raises(ValidationError):
        ChunkDraft(**chunk_data)