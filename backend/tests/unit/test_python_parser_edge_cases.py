import hashlib

import pytest

from reposcope.parsing.python_parser import (
    PythonParserError,
    parse_python,
)


@pytest.mark.parametrize(
    "ending",
    ["", "\n", "\r\n"],
)
@pytest.mark.parametrize(
    "with_bom",
    [False, True],
)
def test_unicode_definition_ranges_and_source_preservation(
    ending,
    with_bom,
):
    newline = "\r\n" if ending == "\r\n" else "\n"

    text = newline.join(
        [
            "def café(value: str = 'é'):",
            '    """नमस्ते"""',
            "    return value",
        ]
    ) + ending

    parse_buffer = text.encode("utf-8")
    original = (
        b"\xef\xbb\xbf" + parse_buffer
        if with_bom
        else parse_buffer
    )

    parsed = parse_python(
        original,
        file_path="unicode.py",
    )

    assert parsed.source_text == text
    assert parsed.source_sha256 == hashlib.sha256(
        original
    ).hexdigest()
    assert parsed.parse_buffer_sha256 == hashlib.sha256(
        parse_buffer
    ).hexdigest()

    assert len(parsed.symbols) == 1
    symbol = parsed.symbols[0]

    assert symbol.name == "café"
    assert symbol.qualname == "café"
    assert symbol.start_line == 1
    assert symbol.end_line == 3
    assert symbol.content_start_line == 1
    assert symbol.content_end_line == 3
    assert symbol.definition_start_byte == 0

    assert symbol.signature == "def café(value: str = 'é'):"
    assert symbol.docstring == "नमस्ते"

    parameter = symbol.parameters[0]
    assert parameter.name == "value"
    assert parameter.annotation == "str"
    assert parameter.default_text == "'é'"

    content = parse_buffer[
        symbol.content_start_byte:symbol.content_end_byte
    ].decode("utf-8")

    expected_content = newline.join(
        [
            "def café(value: str = 'é'):",
            '    """नमस्ते"""',
            "    return value",
        ]
    )

    assert content == expected_content
    assert symbol.cyclomatic_complexity == 1
    assert symbol.complexity_policy == "cc_python_v1"


@pytest.mark.parametrize(
    "first_statement,expected",
    [
        (
            '"plain docstring"',
            "plain docstring",
        ),
        (
            '""',
            "",
        ),
        (
            '"  keep spaces  "',
            "  keep spaces  ",
        ),
        (
            '"escaped\\nnewline"',
            "escaped\nnewline",
        ),
        (
            'r"literal\\ntext"',
            r"literal\ntext",
        ),
        (
            '"first" "second"',
            "firstsecond",
        ),
        (
            '("parenthesized")',
            "parenthesized",
        ),
        (
            'b"bytes are not a docstring"',
            None,
        ),
        (
            'f"formatted {1}"',
            None,
        ),
        (
            '"computed" + "string"',
            None,
        ),
        (
            "(1 / 0)",
            None,
        ),
    ],
)
def test_docstring_literal_and_nonliteral_cases(
    first_statement,
    expected,
):
    source = (
        "def f():\n"
        f"    {first_statement}\n"
        "    return None\n"
    ).encode("utf-8")

    parsed = parse_python(
        source,
        file_path="docstrings.py",
    )

    assert parsed.symbols[0].docstring == expected


def test_leading_comment_does_not_hide_docstring():
    source = b'''def f():
    # Comment before the docstring.
    """Actual docstring."""
    return 1
'''

    parsed = parse_python(
        source,
        file_path="comment_docstring.py",
    )

    assert parsed.symbols[0].docstring == "Actual docstring."


def test_later_string_statement_is_not_a_docstring():
    source = b'''def f():
    value = 1
    """Not a docstring."""
    return value
'''

    parsed = parse_python(
        source,
        file_path="later_string.py",
    )

    assert parsed.symbols[0].docstring is None


def test_multiline_docstring_is_not_cleaned():
    source = b'''class Service:
    """First line.
    Indented second line.
    """
'''

    parsed = parse_python(
        source,
        file_path="multiline_docstring.py",
    )

    assert parsed.symbols[0].docstring == (
        "First line.\n"
        "    Indented second line.\n"
        "    "
    )


def test_decorated_class_and_method_categories():
    source = b'''@decorate
class Service:
    """Service documentation."""

    @staticmethod
    def static(value):
        return value

    @classmethod
    def create(cls):
        return cls()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
'''

    parsed = parse_python(
        source,
        file_path="service.py",
    )

    assert [
        (symbol.qualname, symbol.kind)
        for symbol in parsed.symbols
    ] == [
        ("Service", "class"),
        ("Service.static", "method"),
        ("Service.create", "method"),
        ("Service.value", "method"),
        ("Service.value", "method"),
    ]

    class_symbol = parsed.symbols[0]
    methods = parsed.symbols[1:]

    assert class_symbol.start_line == 2
    assert class_symbol.content_start_line == 1
    assert class_symbol.signature is None
    assert class_symbol.parameters == []
    assert class_symbol.docstring == "Service documentation."
    assert class_symbol.cyclomatic_complexity is None
    assert class_symbol.complexity_policy is None

    assert [
        [parameter.name for parameter in method.parameters]
        for method in methods
    ] == [
        ["value"],
        ["cls"],
        ["self"],
        ["self", "new_value"],
    ]

    buffer = parsed.source_text.encode("utf-8")

    expected_decorators = [
        "    @staticmethod",
        "    @classmethod",
        "    @property",
        "    @value.setter",
    ]

    for method, decorator in zip(
        methods,
        expected_decorators,
    ):
        assert method.parent_key == class_symbol.local_key
        assert method.is_async is False
        assert method.start_line == method.content_start_line + 1
        assert method.cyclomatic_complexity == 1
        assert method.complexity_policy == "cc_python_v1"

        content = buffer[
            method.content_start_byte:method.content_end_byte
        ].decode("utf-8")

        assert content.startswith(decorator + "\n")

        definition = buffer[
            method.definition_start_byte:method.definition_end_byte
        ].decode("utf-8")

        assert definition.startswith("def ")

    getter, setter = methods[2:]

    assert getter.qualname == setter.qualname
    assert getter.local_key != setter.local_key


def test_multiple_decorators_and_header_colons():
    source = b'''@first
@second(42)
def f(value: str = "a:b") -> dict[str, str]:
    return {"value": value}
'''

    parsed = parse_python(
        source,
        file_path="decorators.py",
    )

    symbol = parsed.symbols[0]

    assert symbol.start_line == 3
    assert symbol.content_start_line == 1

    assert symbol.signature == (
        'def f(value: str = "a:b") -> dict[str, str]:'
    )

    assert symbol.parameters[0].annotation == "str"
    assert symbol.parameters[0].default_text == '"a:b"'

    buffer = parsed.source_text.encode("utf-8")
    content = buffer[
        symbol.content_start_byte:symbol.content_end_byte
    ].decode("utf-8")

    assert content.startswith("@first\n@second(42)\ndef f(")


def test_repeated_parsing_produces_identical_metadata():
    source = b'''class Service:
    def run(self, value=1):
        if value:
            return value
        return None
'''

    first = parse_python(
        source,
        file_path="stable.py",
    )
    second = parse_python(
        source,
        file_path="stable.py",
    )

    assert first.model_dump() == second.model_dump()

    keys = [
        symbol.local_key
        for symbol in first.symbols
    ]

    assert len(keys) == len(set(keys))


def test_syntax_error_rejects_the_whole_file():
    source = b'''def valid():
    return 1

def broken(
'''

    with pytest.raises(
        PythonParserError,
        match="syntax errors",
    ):
        parse_python(
            source,
            file_path="partially_broken.py",
        )


def test_decorators_defaults_and_body_are_not_executed():
    source = b'''@must_not_run()
def f(value=must_not_run()):
    return must_not_run()
'''

    parsed = parse_python(
        source,
        file_path="not_executed.py",
    )

    symbol = parsed.symbols[0]

    assert symbol.name == "f"
    assert symbol.signature == "def f(value=must_not_run()):"
    assert symbol.parameters[0].default_text == "must_not_run()"
    assert symbol.cyclomatic_complexity == 1