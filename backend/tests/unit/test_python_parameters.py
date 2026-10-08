import pytest
import tree_sitter_python
from tree_sitter import Language, Parser

from reposcope.parsing.python_parameters import (
    extract_parameters,
)


def _extract(source: bytes):
    parser = Parser(
        Language(tree_sitter_python.language())
    )
    root = parser.parse(source).root_node

    assert not root.has_error

    definition = root.named_children[0]
    parameters_node = definition.child_by_field_name(
        "parameters"
    )
    assert parameters_node is not None

    return extract_parameters(parameters_node, source)


def _rows(parameters):
    return [
        (
            parameter.name,
            parameter.kind,
            parameter.annotation,
            parameter.default_text,
        )
        for parameter in parameters
    ]


def test_empty_parameters():
    parameters = _extract(
        b"def f():\n    pass\n"
    )

    assert parameters == []


def test_all_parameter_kinds():
    source = b'''async def demo(
    a: int,
    /,
    b=1,
    *args: str,
    c: str = "x",
    **kwargs: int,
):
    return a
'''

    assert _rows(_extract(source)) == [
        ("a", "positional_only", "int", None),
        ("b", "positional_or_keyword", None, "1"),
        ("args", "var_positional", "str", None),
        ("c", "keyword_only", "str", '"x"'),
        ("kwargs", "var_keyword", "int", None),
    ]


def test_bare_star_creates_keyword_only_parameters():
    source = (
        b"def f(a, *, b, c=3):\n"
        b"    pass\n"
    )

    assert _rows(_extract(source)) == [
        ("a", "positional_or_keyword", None, None),
        ("b", "keyword_only", None, None),
        ("c", "keyword_only", None, "3"),
    ]


def test_positional_separator_is_not_a_parameter():
    source = (
        b"def f(a, b=2, /, c=3):\n"
        b"    pass\n"
    )

    assert _rows(_extract(source)) == [
        ("a", "positional_only", None, None),
        ("b", "positional_only", None, "2"),
        ("c", "positional_or_keyword", None, "3"),
    ]


def test_untyped_variadic_parameters():
    source = (
        b"def f(*args, flag=True, **kwargs):\n"
        b"    pass\n"
    )

    assert _rows(_extract(source)) == [
        ("args", "var_positional", None, None),
        ("flag", "keyword_only", None, "True"),
        ("kwargs", "var_keyword", None, None),
    ]


@pytest.mark.parametrize(
    "name",
    ["self", "cls"],
)
def test_self_and_cls_are_retained(name):
    source = (
        f"def f({name}, value: int):\n"
        "    pass\n"
    ).encode("utf-8")

    parameters = _extract(source)

    assert [parameter.name for parameter in parameters] == [
        name,
        "value",
    ]
    assert parameters[0].kind == "positional_or_keyword"


def test_complex_annotations_are_source_text():
    source = (
        b"def f(value: dict[str, list[int | None]]):\n"
        b"    pass\n"
    )

    parameter = _extract(source)[0]

    assert parameter.annotation == (
        "dict[str, list[int | None]]"
    )


@pytest.mark.parametrize(
    "expression",
    [
        "None",
        "False",
        "'a b'",
        "[1, 2]",
        "{'a': 1}",
        "factory()",
        "1 / 0",
    ],
)
def test_defaults_are_preserved_without_evaluation(
    expression,
):
    source = (
        f"def f(value={expression}):\n"
        "    pass\n"
    ).encode("utf-8")

    parameter = _extract(source)[0]

    assert parameter.default_text == expression
    assert parameter.annotation is None


def test_multiline_default_is_preserved():
    source = b'''def f(
    value=(
        1 + 2
    ),
):
    pass
'''

    parameter = _extract(source)[0]

    assert parameter.default_text == (
        "(\n"
        "        1 + 2\n"
        "    )"
    )


def test_comments_do_not_become_parameters():
    source = b'''def f(
    # Before the first parameter.
    a: int,  # After the first parameter.
    b=2,
):
    pass
'''

    assert _rows(_extract(source)) == [
        ("a", "positional_or_keyword", "int", None),
        ("b", "positional_or_keyword", None, "2"),
    ]


def test_unicode_parameter_name_and_default():
    source = (
        "def f(café: str = 'नमस्ते'):\n"
        "    pass\n"
    ).encode("utf-8")

    assert _rows(_extract(source)) == [
        (
            "café",
            "positional_or_keyword",
            "str",
            "'नमस्ते'",
        )
    ]


def test_declaration_order_is_preserved():
    source = (
        b"def f(z, a, m=1, *, y, b=2):\n"
        b"    pass\n"
    )

    parameters = _extract(source)

    assert [parameter.name for parameter in parameters] == [
        "z",
        "a",
        "m",
        "y",
        "b",
    ]


def test_wrong_node_type_is_rejected():
    source = b"def f():\n    pass\n"

    parser = Parser(
        Language(tree_sitter_python.language())
    )
    root = parser.parse(source).root_node

    with pytest.raises(
        ValueError,
        match="requires a parameters node",
    ):
        extract_parameters(root, source)