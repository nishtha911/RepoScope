from textwrap import indent

import pytest
import tree_sitter_python
from tree_sitter import Language, Parser

from reposcope.parsing.python_complexity import (
    COMPLEXITY_POLICY,
    ComplexityError,
    calculate_complexity,
)


def _function_node(source: bytes):
    parser = Parser(
        Language(tree_sitter_python.language())
    )
    tree = parser.parse(source)
    root = tree.root_node

    assert not root.has_error

    stack = [root]

    while stack:
        node = stack.pop()

        if node.type == "function_definition":
            return node

        stack.extend(reversed(node.children))

    raise AssertionError("Test source contains no function definition")


def _calculate(source: bytes) -> int:
    return calculate_complexity(
        _function_node(source),
        source,
    )


def _source(body: str, *, is_async: bool = False) -> bytes:
    prefix = "async " if is_async else ""

    text = (
        f"{prefix}def f(value=None, items=(), "
        "a=False, b=False, c=False):\n"
        + indent(body, "    ")
        + "\n"
    )

    return text.encode("utf-8")


def test_policy_identifier():
    assert COMPLEXITY_POLICY == "cc_python_v1"


@pytest.mark.parametrize(
    "label,body,expected",
    [
        (
            "baseline",
            "return 1",
            1,
        ),
        (
            "if",
            "if value:\n"
            "    return 1\n"
            "return 0",
            2,
        ),
        (
            "elif",
            "if a:\n"
            "    return 1\n"
            "elif b:\n"
            "    return 2\n"
            "else:\n"
            "    return 3",
            3,
        ),
        (
            "conditional-expression",
            "return 1 if value else 0",
            2,
        ),
        (
            "for",
            "for item in items:\n"
            "    pass",
            2,
        ),
        (
            "while",
            "while value:\n"
            "    break",
            2,
        ),
        (
            "two-exception-handlers",
            "try:\n"
            "    operation()\n"
            "except ValueError:\n"
            "    pass\n"
            "except TypeError:\n"
            "    pass",
            3,
        ),
        (
            "except-star",
            "try:\n"
            "    operation()\n"
            "except* ValueError:\n"
            "    pass",
            2,
        ),
        (
            "and",
            "return a and b",
            2,
        ),
        (
            "or",
            "return a or b",
            2,
        ),
        (
            "three-and-values",
            "return a and b and c",
            3,
        ),
        (
            "mixed-booleans-in-if",
            "if a and b or c:\n"
            "    return 1",
            4,
        ),
        (
            "list-comprehension",
            "return [x for x in items]",
            2,
        ),
        (
            "filtered-comprehension",
            "return [x for x in items if x]",
            3,
        ),
        (
            "boolean-filter",
            "return [x for x in items if x and a]",
            4,
        ),
        (
            "two-comprehension-generators",
            "return [(x, y) for x in items for y in items]",
            3,
        ),
        (
            "set-comprehension",
            "return {x for x in items if x}",
            3,
        ),
        (
            "dict-comprehension",
            "return {x: x for x in items if x}",
            3,
        ),
        (
            "generator-expression",
            "return (x for x in items)",
            2,
        ),
        (
            "assert",
            "assert value",
            2,
        ),
        (
            "assert-with-and",
            "assert a and b",
            3,
        ),
        (
            "with",
            "with manager():\n"
            "    pass",
            1,
        ),
        (
            "try-else-finally",
            "try:\n"
            "    operation()\n"
            "except ValueError:\n"
            "    pass\n"
            "else:\n"
            "    operation()\n"
            "finally:\n"
            "    cleanup()",
            2,
        ),
        (
            "loop-control-and-else",
            "for item in items:\n"
            "    continue\n"
            "else:\n"
            "    return None",
            2,
        ),
        (
            "literal-match-case",
            "match value:\n"
            "    case 1:\n"
            "        return 1\n"
            "    case _:\n"
            "        return 0",
            2,
        ),
        (
            "wildcard-default",
            "match value:\n"
            "    case _:\n"
            "        return 0",
            1,
        ),
        (
            "capture-default",
            "match value:\n"
            "    case captured:\n"
            "        return captured",
            1,
        ),
        (
            "aliased-wildcard-default",
            "match value:\n"
            "    case _ as captured:\n"
            "        return captured",
            1,
        ),
        (
            "guarded-catch-all",
            "match value:\n"
            "    case _ if a:\n"
            "        return 1\n"
            "    case _:\n"
            "        return 0",
            3,
        ),
        (
            "boolean-case-guard",
            "match value:\n"
            "    case 1 if a and b:\n"
            "        return 1\n"
            "    case _:\n"
            "        return 0",
            4,
        ),
        (
            "or-pattern-is-one-case",
            "match value:\n"
            "    case 1 | 2:\n"
            "        return 1\n"
            "    case _:\n"
            "        return 0",
            2,
        ),
    ],
)
def test_policy_contributions(label, body, expected):
    actual = _calculate(_source(body))

    assert actual == expected, (
        label,
        actual,
        expected,
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        (
            "async for item in items:\n"
            "    pass",
            2,
        ),
        (
            "async with manager():\n"
            "    pass",
            1,
        ),
        (
            "return [x async for x in items if x]",
            3,
        ),
    ],
)
def test_async_constructs(body, expected):
    source = _source(body, is_async=True)

    assert _calculate(source) == expected


@pytest.mark.parametrize(
    "body",
    [
        (
            "def inner(x):\n"
            "    if x:\n"
            "        return 1\n"
            "return inner"
        ),
        (
            "async def inner(x):\n"
            "    if x:\n"
            "        return 1\n"
            "return inner"
        ),
        (
            "class Inner:\n"
            "    if a:\n"
            "        value = 1\n"
            "    def method(self):\n"
            "        if b:\n"
            "            return 1\n"
            "return Inner"
        ),
        (
            "return lambda x: 1 if x else 0"
        ),
        (
            "return lambda x=(1 if a else 2): "
            "1 if x else 0"
        ),
        (
            "@decorate(a if b else c)\n"
            "def inner(x=a or b):\n"
            "    if x:\n"
            "        return 1\n"
            "return inner"
        ),
    ],
)
def test_nested_scope_subtrees_are_excluded(body):
    assert _calculate(_source(body)) == 1


def test_callable_header_defaults_and_decorators_are_excluded():
    source = b'''@decorate(a if b else c)
def f(value=a or b, other=(1 if c else 2)):
    return value
'''

    assert _calculate(source) == 1


def test_docstring_text_does_not_count_as_code():
    source = b'''def f():
    """if and or for while assert"""
    return 1
'''

    assert _calculate(source) == 1


def test_indented_method_definition():
    source = b'''class Service:
    def f(self, value):
        if value:
            return 1
        return 0
'''

    assert _calculate(source) == 2


def test_wrong_node_type_is_rejected():
    source = b"def f():\n    pass\n"

    parser = Parser(
        Language(tree_sitter_python.language())
    )
    root = parser.parse(source).root_node

    with pytest.raises(
        ComplexityError,
        match="requires a function_definition node",
    ):
        calculate_complexity(root, source)


def test_out_of_bounds_source_buffer_is_rejected():
    source = b"def f():\n    pass\n"
    definition = _function_node(source)

    with pytest.raises(
        ComplexityError,
        match="outside the source buffer",
    ):
        calculate_complexity(definition, source[:1])