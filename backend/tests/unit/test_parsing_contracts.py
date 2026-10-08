import copy
import hashlib
import json

import pytest
from pydantic import ValidationError

from reposcope.contracts.parsing import (
    ParsedFile,
    ParsedParameter,
    make_local_key,
)


def _symbol(
    buffer,
    kind,
    name,
    qualname,
    start,
    end,
    content_start=None,
    parent=None,
):
    if content_start is None:
        content_start = start

    return {
        "local_key": make_local_key(
            "package/users.py",
            kind,
            qualname,
            start,
        ),
        "parent_key": parent,
        "name": name,
        "qualname": qualname,
        "kind": kind,
        "start_line": buffer.count(b"\n", 0, start) + 1,
        "end_line": buffer.count(b"\n", 0, end - 1) + 1,
        "definition_start_byte": start,
        "definition_end_byte": end,
        "content_start_line": (
            buffer.count(b"\n", 0, content_start) + 1
        ),
        "content_end_line": (
            buffer.count(b"\n", 0, end - 1) + 1
        ),
        "content_start_byte": content_start,
        "content_end_byte": end,
        "signature": (
            None if kind == "class" else "def f(self):"
        ),
        "docstring": None,
        "parameters": [],
        "is_async": False,
        "cyclomatic_complexity": None,
        "complexity_policy": None,
    }


@pytest.fixture
def payload():
    text = (
        "@dec\r\n"
        "class C:\r\n"
        "    def f(self):\r\n"
        "        return 'é'\r\n"
    )
    buffer = text.encode("utf-8")

    class_symbol = _symbol(
        buffer,
        "class",
        "C",
        "C",
        buffer.index(b"class C"),
        len(buffer),
        content_start=0,
    )

    method_symbol = _symbol(
        buffer,
        "method",
        "f",
        "C.f",
        buffer.index(b"def f"),
        len(buffer),
        parent=class_symbol["local_key"],
    )

    method_symbol["parameters"] = [
        {
            "name": "self",
            "kind": "positional_or_keyword",
            "annotation": None,
            "default_text": None,
        }
    ]

    digest = hashlib.sha256(buffer).hexdigest()

    return {
        "file_path": "package/users.py",
        "source_sha256": digest,
        "source_text": text,
        "parse_buffer_sha256": digest,
        "symbols": [class_symbol, method_symbol],
    }


def test_valid_decorated_class_method_and_roundtrip(payload):
    parsed = ParsedFile.model_validate(payload)

    assert parsed.schema_version == 1
    assert [symbol.kind for symbol in parsed.symbols] == [
        "class",
        "method",
    ]

    assert parsed.symbols[0].start_line == 2
    assert parsed.symbols[0].content_start_line == 1
    assert parsed.symbols[0].end_line == 4

    assert parsed.symbols[1].parameters[0].name == "self"
    assert parsed.source_text == payload["source_text"]

    restored = ParsedFile.model_validate_json(
        parsed.model_dump_json()
    )
    assert restored == parsed


@pytest.mark.parametrize(
    "kind",
    [
        "positional_only",
        "positional_or_keyword",
        "var_positional",
        "keyword_only",
        "var_keyword",
    ],
)
def test_parameter_kinds_and_raw_text(kind):
    parameter = ParsedParameter(
        name="value",
        kind=kind,
        annotation="  list[str]  ",
        default_text="  factory()  ",
    )

    assert parameter.annotation == "  list[str]  "
    assert parameter.default_text == "  factory()  "


@pytest.mark.parametrize(
    "field",
    ["annotation", "default_text"],
)
def test_nullable_parameter_fields_are_required(field):
    data = {
        "name": "x",
        "kind": "positional_or_keyword",
        "annotation": None,
        "default_text": None,
    }
    del data[field]

    with pytest.raises(ValidationError):
        ParsedParameter.model_validate(data)


@pytest.mark.parametrize(
    "kind",
    ["module", "parameter", "variable", "endpoint"],
)
def test_nondefinition_records_rejected(payload, kind):
    payload["symbols"][0]["kind"] = kind

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


@pytest.mark.parametrize(
    "level",
    ["file", "symbol", "parameter"],
)
def test_unknown_fields_rejected(payload, level):
    targets = {
        "file": payload,
        "symbol": payload["symbols"][1],
        "parameter": payload["symbols"][1]["parameters"][0],
    }
    targets[level]["invented_field"] = True

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/x.py",
        "../x.py",
        "a/../x.py",
        "a//x.py",
        "./x.py",
        "C:/x.py",
        "a\\x.py",
        " ",
    ],
)
def test_invalid_paths_rejected(payload, path):
    payload["file_path"] = path

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["source_sha256", "parse_buffer_sha256"],
)
def test_malformed_hashes_rejected(payload, field):
    payload[field] = "not-a-hash"

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_buffer_hash_mismatch_rejected(payload):
    payload["parse_buffer_sha256"] = "0" * 64

    with pytest.raises(
        ValidationError,
        match="does not match",
    ):
        ParsedFile.model_validate(payload)


def test_original_hash_is_not_assumed_equal_to_parse_hash(
    payload,
):
    original = (
        b"\xef\xbb\xbf"
        + payload["source_text"].encode("utf-8")
    )
    payload["source_sha256"] = hashlib.sha256(
        original
    ).hexdigest()

    parsed = ParsedFile.model_validate(payload)

    assert (
        parsed.source_sha256
        != parsed.parse_buffer_sha256
    )


@pytest.mark.parametrize(
    "field",
    [
        "parent_key",
        "docstring",
        "parameters",
        "is_async",
        "cyclomatic_complexity",
        "complexity_policy",
    ],
)
def test_symbol_fields_are_required(payload, field):
    del payload["symbols"][1][field]

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("end_line", 1),
        ("definition_end_byte", 0),
        ("content_start_byte", 10),
        ("content_end_byte", 9999),
        ("start_line", 99),
        ("end_line", 99),
    ],
)
def test_invalid_ranges_rejected(payload, field, value):
    payload["symbols"][1][field] = value

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_utf8_midcharacter_boundary_rejected(payload):
    buffer = payload["source_text"].encode("utf-8")

    invalid_end = (
        buffer.index("é".encode("utf-8")) + 1
    )
    payload["symbols"][1][
        "definition_end_byte"
    ] = invalid_end

    with pytest.raises(
        ValidationError,
        match="UTF-8",
    ):
        ParsedFile.model_validate(payload)


def test_duplicate_keys_rejected(payload):
    duplicate = copy.deepcopy(payload["symbols"][1])
    payload["symbols"].append(duplicate)

    with pytest.raises(
        ValidationError,
        match="unique",
    ):
        ParsedFile.model_validate(payload)


def test_invalid_local_identity_rejected(payload):
    payload["symbols"][1]["local_key"] = "invented-id"

    with pytest.raises(
        ValidationError,
        match="identity",
    ):
        ParsedFile.model_validate(payload)


def test_missing_parent_rejected(payload):
    payload["symbols"][1]["parent_key"] = "missing"

    with pytest.raises(
        ValidationError,
        match="parent_key",
    ):
        ParsedFile.model_validate(payload)


def test_parent_cycle_rejected(payload):
    payload["symbols"][0]["parent_key"] = (
        payload["symbols"][1]["local_key"]
    )

    with pytest.raises(
        ValidationError,
        match="cycle",
    ):
        ParsedFile.model_validate(payload)


def test_unordered_symbols_rejected(payload):
    payload["symbols"].reverse()

    with pytest.raises(
        ValidationError,
        match="ordering",
    ):
        ParsedFile.model_validate(payload)


@pytest.mark.parametrize(
    "value,policy",
    [
        (2, None),
        (None, "cc_python_v1"),
        (0, "cc_python_v1"),
    ],
)
def test_invalid_complexity_pair_rejected(
    payload,
    value,
    policy,
):
    payload["symbols"][1].update(
        cyclomatic_complexity=value,
        complexity_policy=policy,
    )

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_callable_complexity_metadata_supported_without_calculation(
    payload,
):
    payload["symbols"][1].update(
        cyclomatic_complexity=2,
        complexity_policy="test_policy",
    )

    parsed = ParsedFile.model_validate(payload)

    assert parsed.symbols[1].cyclomatic_complexity == 2


@pytest.mark.parametrize(
    "change",
    [
        {"signature": "class C:"},
        {"is_async": True},
        {
            "cyclomatic_complexity": 1,
            "complexity_policy": "test_policy",
        },
    ],
)
def test_class_metadata_rules(payload, change):
    payload["symbols"][0].update(change)

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_callable_requires_signature(payload):
    payload["symbols"][1]["signature"] = None

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_source_metadata_not_stripped(payload):
    payload["symbols"][1].update(
        signature="  def f(self):  ",
        docstring="  doc  ",
    )

    parsed = ParsedFile.model_validate(payload)

    assert parsed.symbols[1].signature == "  def f(self):  "
    assert parsed.symbols[1].docstring == "  doc  "


@pytest.mark.parametrize(
    "text",
    ["", "# comment\n", "# comment"],
)
def test_files_without_definitions(text):
    digest = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    parsed = ParsedFile(
        file_path="empty.py",
        source_sha256=digest,
        source_text=text,
        parse_buffer_sha256=digest,
        symbols=[],
    )

    assert parsed.symbols == []


@pytest.mark.parametrize(
    "ending",
    ["", "\n", "\r\n"],
)
def test_exclusive_end_line_with_or_without_final_newline(
    ending,
):
    text = "def f():\n    pass" + ending
    buffer = text.encode("utf-8")

    symbol = _symbol(
        buffer,
        "function",
        "f",
        "f",
        0,
        len(buffer),
    )
    symbol["signature"] = "def f():"

    digest = hashlib.sha256(buffer).hexdigest()

    parsed = ParsedFile(
        file_path="package/users.py",
        source_sha256=digest,
        source_text=text,
        parse_buffer_sha256=digest,
        symbols=[symbol],
    )

    assert parsed.symbols[0].end_line == 2


def test_schema_version_rejected(payload):
    payload["schema_version"] = 2

    with pytest.raises(ValidationError):
        ParsedFile.model_validate(payload)


def test_local_key_json_is_unambiguous():
    key = make_local_key(
        "a|b.py",
        "function",
        "outer.inner",
        12,
    )

    assert json.loads(key) == [
        "a|b.py",
        "function",
        "outer.inner",
        12,
    ]