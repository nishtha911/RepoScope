import json
from codecs import BOM_UTF8

import pytest

from reposcope.contracts.chunking import SOURCE_SEPARATOR
from reposcope.parsing.python_parser import parse_python
from reposcope.retrieval.chunker import (
    ChunkingError,
    build_symbol_chunks,
)


def _parse(source: bytes):
    return parse_python(
        source,
        file_path="package/sample.py",
    )


def test_complete_function_and_header():
    source = (
        b"def add(a: int, b: int) -> int:\n"
        b'    """Add two numbers."""\n'
        b"    return a + b\n"
    )
    parsed = _parse(source)

    chunks = build_symbol_chunks(parsed)

    assert len(chunks) == 1

    chunk = chunks[0]
    symbol = parsed.symbols[0]

    assert chunk.symbol_key == symbol.local_key
    assert chunk.file_path == parsed.file_path
    assert chunk.qualname == "add"
    assert chunk.kind == "function"

    assert chunk.body_text == source[:-1].decode("utf-8")
    assert chunk.start_line == symbol.content_start_line
    assert chunk.end_line == symbol.content_end_line

    assert json.loads(chunk.header_text) == {
        "file_path": "package/sample.py",
        "qualname": "add",
        "kind": "function",
        "signature": "def add(a: int, b: int) -> int:",
        "docstring": "Add two numbers.",
    }

    assert chunk.text == (
        chunk.header_text
        + SOURCE_SEPARATOR
        + chunk.body_text
    )


def test_decorators_indentation_and_class_method_overlap():
    source = (
        b"@decorate\n"
        b"class Service:\n"
        b"    @staticmethod\n"
        b"    def run():\n"
        b"        return 1\n"
    )
    parsed = _parse(source)

    chunks = build_symbol_chunks(parsed)
    by_name = {chunk.qualname: chunk for chunk in chunks}

    assert len(chunks) == 2

    class_chunk = by_name["Service"]
    method_chunk = by_name["Service.run"]

    assert class_chunk.body_text.startswith(
        "@decorate\nclass Service:"
    )

    assert method_chunk.body_text == (
        "    @staticmethod\n"
        "    def run():\n"
        "        return 1"
    )

    assert method_chunk.body_text in class_chunk.body_text
    assert json.loads(class_chunk.header_text)["signature"] is None


def test_outer_and_inner_function_chunks_overlap():
    source = (
        b"def outer():\n"
        b"    def inner():\n"
        b"        return 1\n"
        b"    return inner()\n"
    )

    chunks = build_symbol_chunks(_parse(source))
    by_name = {chunk.qualname: chunk for chunk in chunks}

    assert len(chunks) == 2
    assert set(by_name) == {"outer", "outer.inner"}

    assert by_name["outer"].body_text == source[:-1].decode("utf-8")
    assert by_name["outer.inner"].body_text == (
        "    def inner():\n"
        "        return 1"
    )

    assert (
        by_name["outer.inner"].body_text
        in by_name["outer"].body_text
    )


@pytest.mark.parametrize(
    ("newline", "include_bom"),
    [
        ("\n", False),
        ("\r\n", False),
        ("\r\n", True),
    ],
)
def test_preserves_unicode_newlines_and_bom_policy(
    newline,
    include_bom,
):
    function = (
        "def greet():\n"
        '    """नमस्ते ☕"""\n'
        '    return "café"\n'
    ).replace("\n", newline)

    source_text = (
        "# Unicode before the definition: π ☕"
        + newline
        + function
    )

    source = source_text.encode("utf-8")

    if include_bom:
        source = BOM_UTF8 + source

    parsed = _parse(source)
    chunks = build_symbol_chunks(parsed)

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.body_text == function.removesuffix(newline)
    assert json.loads(chunk.header_text)["docstring"] == "नमस्ते ☕"

    assert chunk.source_sha256 == parsed.source_sha256
    assert chunk.parse_buffer_sha256 == parsed.parse_buffer_sha256

    assert not chunk.body_text.startswith("\ufeff")


def test_oversized_function_is_not_split():
    statements = "\n".join(
        f"    value_{index} = {index}"
        for index in range(1200)
    )

    source_text = (
        "def large():\n"
        + statements
        + "\n    return value_1199"
    )

    chunks = build_symbol_chunks(
        _parse(source_text.encode("utf-8"))
    )

    assert len(chunks) == 1
    assert chunks[0].body_text == source_text
    assert "value_0 = 0" in chunks[0].body_text
    assert chunks[0].body_text.endswith("return value_1199")


@pytest.mark.parametrize(
    "source",
    [
        b"",
        b"# Comment-only file\n",
    ],
)
def test_file_without_definitions_has_no_chunks(source):
    assert build_symbol_chunks(_parse(source)) == []


def test_changed_source_buffer_is_rejected():
    parsed = _parse(b"def run():\n    return 1\n")
    parsed.source_text += "# Changed after parsing\n"

    with pytest.raises(ChunkingError):
        build_symbol_chunks(parsed)


def test_out_of_bounds_content_range_is_rejected():
    parsed = _parse(b"def run():\n    return 1\n")

    parsed.symbols[0].content_end_byte = (
        len(parsed.source_text.encode("utf-8")) + 10
    )

    with pytest.raises(ChunkingError):
        build_symbol_chunks(parsed)


def test_unrelated_original_source_hash_is_rejected():
    parsed = _parse(b"def run():\n    return 1\n")
    parsed.source_sha256 = "0" * 64

    with pytest.raises(ChunkingError):
        build_symbol_chunks(parsed)


def test_dictionary_input_is_rejected():
    with pytest.raises(TypeError):
        build_symbol_chunks({})


@pytest.mark.parametrize(
    ("source", "expected_docstring"),
    [
        (
            b"def run():\n    return 1\n",
            None,
        ),
        (
            b'def run():\n    """"""\n    return 1\n',
            "",
        ),
    ],
)
def test_missing_and_empty_docstrings_remain_distinct(
    source,
    expected_docstring,
):
    chunks = build_symbol_chunks(_parse(source))

    assert len(chunks) == 1
    assert (
        json.loads(chunks[0].header_text)["docstring"]
        == expected_docstring
    )