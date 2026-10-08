import hashlib

import pytest

from reposcope.parsing.python_parser import (
    PythonParserError,
    parse_python,
)


@pytest.mark.parametrize(
    "source",
    [
        b"",
        b"# comment",
        b"# comment\n",
        b"\n\n",
        b"value = 1\n",
    ],
)
def test_files_without_definitions(source):
    parsed = parse_python(
        source,
        file_path="package/example.py",
    )

    assert parsed.schema_version == 1
    assert parsed.file_path == "package/example.py"
    assert parsed.source_text == source.decode("utf-8")
    assert parsed.symbols == []

    expected_hash = hashlib.sha256(source).hexdigest()

    assert parsed.source_sha256 == expected_hash
    assert parsed.parse_buffer_sha256 == expected_hash


@pytest.mark.parametrize(
    "source",
    [
        b"# first\n# second\n",
        b"# first\r\n# second\r\n",
        b"# first\n# second\r\n",
        b"# first\n# second",
        b"# first\r\n# second",
        b"# first\n\n",
    ],
)
def test_newlines_are_not_normalized(source):
    parsed = parse_python(
        source,
        file_path="newlines.py",
    )

    assert parsed.source_text.encode("utf-8") == source
    assert parsed.parse_buffer_sha256 == hashlib.sha256(
        source
    ).hexdigest()


def test_unicode_source_is_preserved():
    text = "# café — नमस्ते\nvalue = 'é'\n"
    source = text.encode("utf-8")

    parsed = parse_python(
        source,
        file_path="unicode.py",
    )

    assert parsed.source_text == text
    assert parsed.source_text.encode("utf-8") == source
    assert parsed.symbols == []


def test_leading_bom_is_removed_only_from_parse_buffer():
    text = "# comment\r\nvalue = 1\r\n"
    parse_buffer = text.encode("utf-8")
    original = b"\xef\xbb\xbf" + parse_buffer

    parsed = parse_python(
        original,
        file_path="bom.py",
    )

    assert parsed.source_text == text
    assert parsed.source_sha256 == hashlib.sha256(
        original
    ).hexdigest()
    assert parsed.parse_buffer_sha256 == hashlib.sha256(
        parse_buffer
    ).hexdigest()

    assert (
        parsed.source_sha256
        != parsed.parse_buffer_sha256
    )


@pytest.mark.parametrize(
    "source",
    [
        b"# coding: utf-8\nvalue = 1\n",
        b"# coding: utf_8\nvalue = 1\n",
        b"#!/usr/bin/env python\n# coding: utf-8\n",
    ],
)
def test_utf8_encoding_declarations_are_supported(source):
    parsed = parse_python(
        source,
        file_path="encoding.py",
    )

    assert parsed.source_text.encode("utf-8") == source


@pytest.mark.parametrize(
    "source",
    [
        b"# coding: latin-1\nvalue = 1\n",
        b"# coding: cp1252\nvalue = 1\n",
    ],
)
def test_non_utf8_encoding_declarations_are_rejected(source):
    with pytest.raises(
        PythonParserError,
        match="unsupported source encoding",
    ):
        parse_python(
            source,
            file_path="unsupported.py",
        )


@pytest.mark.parametrize(
    "source",
    [
        b"# invalid: \xff\n",
        b"# valid first line\nvalue = '\xff'\n",
    ],
)
def test_invalid_utf8_bytes_are_rejected(source):
    with pytest.raises(PythonParserError):
        parse_python(
            source,
            file_path="invalid_bytes.py",
        )


def test_unknown_encoding_declaration_is_rejected():
    with pytest.raises(PythonParserError):
        parse_python(
            b"# coding: definitely-not-an-encoding\n",
            file_path="unknown_encoding.py",
        )


def test_bom_conflicting_with_encoding_cookie_is_rejected():
    source = (
        b"\xef\xbb\xbf"
        b"# coding: latin-1\n"
        b"value = 1\n"
    )

    with pytest.raises(PythonParserError):
        parse_python(
            source,
            file_path="conflicting_encoding.py",
        )


@pytest.mark.parametrize(
    "source",
    [
        b"def broken(",
        b"class Broken(",
        b"value = [1,\n",
    ],
)
def test_syntax_errors_are_rejected(source):
    with pytest.raises(
        PythonParserError,
        match="syntax errors",
    ) as caught:
        parse_python(
            source,
            file_path="broken.py",
        )

    assert caught.value.file_path == "broken.py"
    assert str(caught.value).startswith("broken.py:")


@pytest.mark.parametrize(
    "source,name,kind,is_async",
    [
        (
            b"def f():\n    pass\n",
            "f",
            "function",
            False,
        ),
        (
            b"class C:\n    pass\n",
            "C",
            "class",
            False,
        ),
        (
            b"async def f():\n    pass\n",
            "f",
            "function",
            True,
        ),
        (
            b"if True:\n    def nested():\n        pass\n",
            "nested",
            "function",
            False,
        ),
    ],
)
def test_definitions_are_extracted(
    source,
    name,
    kind,
    is_async,
):
    parsed = parse_python(
        source,
        file_path="definitions.py",
    )

    assert len(parsed.symbols) == 1

    symbol = parsed.symbols[0]

    assert symbol.name == name
    assert symbol.qualname == name
    assert symbol.kind == kind
    assert symbol.is_async is is_async
    assert symbol.parent_key is None
    assert symbol.parameters == []

    if kind == "class":
        assert symbol.cyclomatic_complexity is None
        assert symbol.complexity_policy is None

    else:
        assert symbol.cyclomatic_complexity == 1
        assert symbol.complexity_policy == "cc_python_v1"


@pytest.mark.parametrize(
    "source",
    [
        "value = 1",
        bytearray(b"value = 1"),
        None,
    ],
)
def test_source_must_be_bytes(source):
    with pytest.raises(
        TypeError,
        match="source must be bytes",
    ):
        parse_python(
            source,
            file_path="example.py",
        )


def test_result_contains_serializable_metadata():
    parsed = parse_python(
        b"# comment\n",
        file_path="package/example.py",
    )

    restored = type(parsed).model_validate_json(
        parsed.model_dump_json()
    )

    assert restored == parsed


def test_decorated_async_function_metadata():
    source = b'''@decorate
async def demo(
    a: int,
    /,
    b=1,
    *args: str,
    c: str = "x",
    **kwargs: int,
):
    """Example docstring."""
    return a
'''

    parsed = parse_python(
        source,
        file_path="package/demo.py",
    )

    assert len(parsed.symbols) == 1

    symbol = parsed.symbols[0]

    assert symbol.name == "demo"
    assert symbol.qualname == "demo"
    assert symbol.kind == "function"
    assert symbol.is_async is True
    assert symbol.start_line == 2
    assert symbol.content_start_line == 1
    assert symbol.docstring == "Example docstring."
    assert symbol.cyclomatic_complexity == 1
    assert symbol.complexity_policy == "cc_python_v1"

    assert symbol.signature == (
        "async def demo(\n"
        "    a: int,\n"
        "    /,\n"
        "    b=1,\n"
        "    *args: str,\n"
        '    c: str = "x",\n'
        "    **kwargs: int,\n"
        "):"
    )

    assert [
        (parameter.name, parameter.kind)
        for parameter in symbol.parameters
    ] == [
        ("a", "positional_only"),
        ("b", "positional_or_keyword"),
        ("args", "var_positional"),
        ("c", "keyword_only"),
        ("kwargs", "var_keyword"),
    ]

    buffer = parsed.source_text.encode("utf-8")

    content = buffer[
        symbol.content_start_byte:symbol.content_end_byte
    ].decode("utf-8")

    assert content.startswith(
        "@decorate\nasync def demo("
    )
    assert content.endswith("return a")


def test_nested_definitions_and_parent_relationships():
    source = b'''class Outer:
    class Inner:
        def run(self):
            def helper(value):
                return value
            return helper(1)

def outer():
    def inner():
        pass
    return inner
'''

    parsed = parse_python(
        source,
        file_path="nested.py",
    )

    assert [
        (symbol.qualname, symbol.kind)
        for symbol in parsed.symbols
    ] == [
        ("Outer", "class"),
        ("Outer.Inner", "class"),
        ("Outer.Inner.run", "method"),
        ("Outer.Inner.run.helper", "function"),
        ("outer", "function"),
        ("outer.inner", "function"),
    ]

    by_name = {
        symbol.qualname: symbol
        for symbol in parsed.symbols
    }

    assert by_name["Outer"].parent_key is None

    assert by_name["Outer.Inner"].parent_key == (
        by_name["Outer"].local_key
    )

    assert by_name["Outer.Inner.run"].parent_key == (
        by_name["Outer.Inner"].local_key
    )

    assert by_name["Outer.Inner.run.helper"].parent_key == (
        by_name["Outer.Inner.run"].local_key
    )

    assert by_name["outer"].parent_key is None

    assert by_name["outer.inner"].parent_key == (
        by_name["outer"].local_key
    )

    assert [
        parameter.name
        for parameter in by_name[
            "Outer.Inner.run"
        ].parameters
    ] == ["self"]

    for symbol in parsed.symbols:
        if symbol.kind == "class":
            assert symbol.cyclomatic_complexity is None
            assert symbol.complexity_policy is None

        else:
            assert symbol.cyclomatic_complexity == 1
            assert symbol.complexity_policy == "cc_python_v1"

    buffer = parsed.source_text.encode("utf-8")
    method = by_name["Outer.Inner.run"]

    method_content = buffer[
        method.content_start_byte:method.content_end_byte
    ].decode("utf-8")

    assert method_content.startswith(
        "        def run(self):"
    )


def test_redefinitions_have_distinct_local_keys():
    source = b'''def repeated():
    return 1

def repeated():
    return 2
'''

    parsed = parse_python(
        source,
        file_path="redefinitions.py",
    )

    assert len(parsed.symbols) == 2
    first, second = parsed.symbols

    assert first.qualname == second.qualname == "repeated"
    assert first.local_key != second.local_key
    assert (
        first.definition_start_byte
        < second.definition_start_byte
    )

    assert first.cyclomatic_complexity == 1
    assert second.cyclomatic_complexity == 1
    assert first.complexity_policy == "cc_python_v1"
    assert second.complexity_policy == "cc_python_v1"


def test_parser_attaches_independent_callable_complexity():
    source = b'''class Service:
    async def check(self, value, flag=True):
        if value and flag:
            return 1

        def inner(items):
            for item in items:
                print(item)

        return inner
'''

    parsed = parse_python(
        source,
        file_path="service.py",
    )

    by_name = {
        symbol.qualname: symbol
        for symbol in parsed.symbols
    }

    assert set(by_name) == {
        "Service",
        "Service.check",
        "Service.check.inner",
    }

    class_symbol = by_name["Service"]
    method = by_name["Service.check"]
    inner = by_name["Service.check.inner"]

    assert class_symbol.cyclomatic_complexity is None
    assert class_symbol.complexity_policy is None

    assert method.kind == "method"
    assert method.is_async is True
    assert method.cyclomatic_complexity == 3
    assert method.complexity_policy == "cc_python_v1"

    assert inner.kind == "function"
    assert inner.cyclomatic_complexity == 2
    assert inner.complexity_policy == "cc_python_v1"

    assert method.parent_key == class_symbol.local_key
    assert inner.parent_key == method.local_key