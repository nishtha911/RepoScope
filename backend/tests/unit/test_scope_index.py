import ast
import json

import pytest

from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import RepoIndexError, build_repo_index
from reposcope.parsing.scope_index import (
    ScopeIndex,
    build_scope_index,
    make_scope_key,
)


def index_for(
    source: str,
    *,
    file_path: str = "app.py",
) -> ScopeIndex:
    parsed = parse_python(
        source.encode("utf-8"),
        file_path=file_path,
    )
    return build_scope_index(build_repo_index([parsed]))


def definition_scope(index: ScopeIndex, qualname: str):
    symbol = next(
        symbol
        for symbol in index.repo_index.definitions_by_local_key.values()
        if symbol.qualname == qualname
    )

    key = index.definition_scope_keys_by_local_key[symbol.local_key]
    return index.scopes_by_key[key]


def node_span(source: str, node: ast.AST) -> tuple[int, int]:
    buffer = source.encode("utf-8")
    starts = [0]
    starts.extend(
        position + 1
        for position, value in enumerate(buffer)
        if value == 10
    )

    return (
        starts[node.lineno - 1] + node.col_offset,
        starts[node.end_lineno - 1] + node.end_col_offset,
    )


def call_context(
    index: ScopeIndex,
    name: str,
    *,
    occurrence: int = 0,
    file_path: str = "app.py",
):
    source = index.repo_index.files_by_path[file_path].source_text
    tree = ast.parse(source)

    calls = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )

    call = calls[occurrence]
    start, end = node_span(source, call)

    return index.context_for(
        file_path,
        "Call",
        start,
        end,
    )


def test_empty_repository():
    index = build_scope_index(build_repo_index([]))

    assert not index.scopes_by_key
    assert not index.module_scope_keys_by_path
    assert not index.definition_scope_keys_by_local_key
    assert not index.contexts_by_location


@pytest.mark.parametrize("source", ["", "# comment only\n"])
def test_file_without_definitions_has_module_scope(source):
    index = index_for(source)
    key = index.module_scope_keys_by_path["app.py"]
    scope = index.scopes_by_key[key]

    assert len(index.scopes_by_key) == 1
    assert scope.kind == "module"
    assert scope.parent_scope_key is None
    assert scope.lookup_parent_scope_key is None
    assert scope.source_owner.target_kind == "module"
    assert scope.start_byte == 0
    assert scope.end_byte == len(source.encode("utf-8"))


def test_scope_keys_use_canonical_json():
    key = make_scope_key(
        "café/app.py",
        "function",
        5,
        25,
    )

    assert json.loads(key) == [
        "scope",
        "café/app.py",
        "function",
        5,
        25,
    ]
    assert key == (
        '["scope","café/app.py","function",5,25]'
    )


def test_function_and_nested_function_scopes():
    index = index_for(
        "def outer():\n"
        "    def inner():\n"
        "        return helper()\n"
        "    return inner()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    outer = definition_scope(index, "outer")
    inner = definition_scope(index, "outer.inner")

    assert outer.kind == "function"
    assert outer.parent_scope_key == module_key
    assert outer.lookup_parent_scope_key == module_key

    assert inner.kind == "function"
    assert inner.parent_scope_key == outer.scope_key
    assert inner.lookup_parent_scope_key == outer.scope_key

    assert call_context(index, "helper").scope_key == inner.scope_key
    assert call_context(index, "inner").scope_key == outer.scope_key


def test_method_lexical_parent_differs_from_lookup_parent():
    index = index_for(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    service = definition_scope(index, "Service")
    run = definition_scope(index, "Service.run")

    assert service.kind == "class"
    assert run.kind == "method"
    assert run.parent_scope_key == service.scope_key
    assert run.lookup_parent_scope_key == module_key

    context = call_context(index, "helper")

    assert context.scope_key == run.scope_key
    assert context.source_owner.symbol_key == run.source_owner.symbol_key


def test_method_can_retain_enclosing_function_scope():
    index = index_for(
        "def outer():\n"
        "    class Service:\n"
        "        def run(self):\n"
        "            return helper()\n"
        "    return Service\n"
    )

    outer = definition_scope(index, "outer")
    service = definition_scope(index, "outer.Service")
    run = definition_scope(index, "outer.Service.run")

    assert service.parent_scope_key == outer.scope_key
    assert service.lookup_parent_scope_key == outer.scope_key

    assert run.parent_scope_key == service.scope_key
    assert run.lookup_parent_scope_key == outer.scope_key


def test_nested_class_does_not_capture_outer_class_namespace():
    index = index_for(
        "class Outer:\n"
        "    class Inner:\n"
        "        value = helper()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    outer = definition_scope(index, "Outer")
    inner = definition_scope(index, "Outer.Inner")

    assert inner.parent_scope_key == outer.scope_key
    assert inner.lookup_parent_scope_key == module_key
    assert call_context(index, "helper").scope_key == inner.scope_key


def test_function_defaults_use_surrounding_scope():
    index = index_for(
        "def caller(value=default_factory()):\n"
        "    return body_call()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    caller = definition_scope(index, "caller")

    default = call_context(index, "default_factory")
    body = call_context(index, "body_call")

    assert default.scope_key == module_key
    assert default.source_owner.symbol_key == caller.source_owner.symbol_key
    assert default.resolution_blocker is None

    assert body.scope_key == caller.scope_key


def test_method_default_uses_class_scope_not_method_scope():
    index = index_for(
        "class Service:\n"
        "    def run(self, value=default_factory()):\n"
        "        return body_call()\n"
    )

    service = definition_scope(index, "Service")
    run = definition_scope(index, "Service.run")

    assert call_context(index, "default_factory").scope_key == (
        service.scope_key
    )
    assert call_context(index, "body_call").scope_key == run.scope_key


def test_function_decorator_uses_surrounding_lookup_scope():
    index = index_for(
        "@decorate()\n"
        "def caller():\n"
        "    return body_call()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    caller = definition_scope(index, "caller")
    decorator = call_context(index, "decorate")

    assert decorator.scope_key == module_key
    assert decorator.source_owner.symbol_key == caller.source_owner.symbol_key
    assert call_context(index, "body_call").scope_key == caller.scope_key


def test_class_headers_use_surrounding_scope_with_class_owner():
    index = index_for(
        "@decorate()\n"
        "class Child(base_factory(), metaclass=meta_factory()):\n"
        "    value = body_call()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    child = definition_scope(index, "Child")

    for name in ("decorate", "base_factory", "meta_factory"):
        context = call_context(index, name)
        assert context.scope_key == module_key
        assert context.source_owner.symbol_key == child.source_owner.symbol_key

    assert call_context(index, "body_call").scope_key == child.scope_key


def test_async_function_has_function_scope():
    index = index_for(
        "async def caller():\n"
        "    return await helper()\n"
    )

    caller = definition_scope(index, "caller")

    assert caller.kind == "function"
    assert call_context(index, "helper").scope_key == caller.scope_key


def test_lambda_default_and_body_have_different_contexts():
    index = index_for(
        "callback = lambda value=default_factory(): body_call(value)\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    lambdas = [
        scope
        for scope in index.scopes_by_key.values()
        if scope.kind == "lambda"
    ]

    assert len(lambdas) == 1
    scope = lambdas[0]

    assert scope.parent_scope_key == module_key
    assert scope.lookup_parent_scope_key == module_key
    assert scope.source_owner.target_kind == "module"

    assert call_context(index, "default_factory").scope_key == module_key
    assert call_context(index, "body_call").scope_key == scope.scope_key
    assert not index.definition_scope_keys_by_local_key


def test_lambda_in_class_skips_class_for_body_lookup():
    index = index_for(
        "class Service:\n"
        "    callback = lambda value=default_factory(): body_call(value)\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    service = definition_scope(index, "Service")
    scope = next(
        scope
        for scope in index.scopes_by_key.values()
        if scope.kind == "lambda"
    )

    assert scope.parent_scope_key == service.scope_key
    assert scope.lookup_parent_scope_key == module_key
    assert scope.source_owner.symbol_key == service.source_owner.symbol_key

    assert call_context(index, "default_factory").scope_key == (
        service.scope_key
    )
    assert call_context(index, "body_call").scope_key == scope.scope_key


@pytest.mark.parametrize(
    "expression",
    [
        "[transform(x) for x in produce() if accept(x)]",
        "{transform(x) for x in produce() if accept(x)}",
        "{transform(x): value(x) for x in produce() if accept(x)}",
        "(transform(x) for x in produce() if accept(x))",
    ],
)
def test_comprehension_first_iterable_uses_outer_scope(expression):
    index = index_for(f"result = {expression}\n")
    module_key = index.module_scope_keys_by_path["app.py"]

    scopes = [
        scope
        for scope in index.scopes_by_key.values()
        if scope.kind == "comprehension"
    ]

    assert len(scopes) == 1
    scope = scopes[0]

    assert scope.parent_scope_key == module_key
    assert scope.lookup_parent_scope_key == module_key
    assert call_context(index, "produce").scope_key == module_key
    assert call_context(index, "transform").scope_key == scope.scope_key
    assert call_context(index, "accept").scope_key == scope.scope_key

    if "value(x)" in expression:
        assert call_context(index, "value").scope_key == scope.scope_key

    assert not index.definition_scope_keys_by_local_key


def test_later_comprehension_iterable_uses_comprehension_scope():
    index = index_for(
        "result = [combine(x, y) "
        "for x in first() "
        "for y in second(x) "
        "if accept(y)]\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    scope = next(
        scope
        for scope in index.scopes_by_key.values()
        if scope.kind == "comprehension"
    )

    assert call_context(index, "first").scope_key == module_key

    for name in ("combine", "second", "accept"):
        assert call_context(index, name).scope_key == scope.scope_key


def test_comprehension_inside_class_skips_class_lookup():
    index = index_for(
        "class Service:\n"
        "    values = [transform(x) for x in produce()]\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    service = definition_scope(index, "Service")
    scope = next(
        scope
        for scope in index.scopes_by_key.values()
        if scope.kind == "comprehension"
    )

    assert scope.parent_scope_key == service.scope_key
    assert scope.lookup_parent_scope_key == module_key

    assert call_context(index, "produce").scope_key == service.scope_key
    assert call_context(index, "transform").scope_key == scope.scope_key


def test_annotations_are_explicitly_blocked():
    index = index_for(
        "def caller(value: parameter_type()) -> return_type():\n"
        "    local: local_type() = actual_value()\n"
        "    return body_call()\n"
    )

    module_key = index.module_scope_keys_by_path["app.py"]
    caller = definition_scope(index, "caller")

    for name in ("parameter_type", "return_type"):
        context = call_context(index, name)
        assert context.scope_key == module_key
        assert context.resolution_blocker == (
            "ANNOTATION_SEMANTICS_NOT_MODELED"
        )

    local_annotation = call_context(index, "local_type")

    assert local_annotation.scope_key == caller.scope_key
    assert local_annotation.resolution_blocker == (
        "ANNOTATION_SEMANTICS_NOT_MODELED"
    )

    for name in ("actual_value", "body_call"):
        context = call_context(index, name)
        assert context.scope_key == caller.scope_key
        assert context.resolution_blocker is None


def test_unicode_before_call_uses_byte_offset_not_character_offset():
    source = "label = 'café'; helper()\n"
    index = index_for(source)
    buffer = source.encode("utf-8")

    start = buffer.index(b"helper()")
    end = start + len(b"helper()")

    assert start != source.index("helper()")

    context = index.context_for(
        "app.py",
        "Call",
        start,
        end,
    )

    assert context.scope_key == index.module_scope_keys_by_path["app.py"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [False, True])
def test_unicode_crlf_and_bom_scope_positions(newline, bom):
    text = (
        f"def café():{newline}"
        f"    return 1{newline}"
        f"{newline}"
        f"def caller():{newline}"
        f"    return café(){newline}"
    )
    source = text.encode("utf-8")

    if bom:
        source = b"\xef\xbb\xbf" + source

    parsed = parse_python(source, file_path="unicode.py")
    index = build_scope_index(build_repo_index([parsed]))
    caller = definition_scope(index, "caller")
    buffer = text.encode("utf-8")

    expression = "café()".encode("utf-8")
    start = buffer.rindex(expression)
    end = start + len(expression)

    context = index.context_for(
        "unicode.py",
        "Call",
        start,
        end,
    )

    assert context.scope_key == caller.scope_key
    assert buffer[start:end] == expression
    assert index.repo_index.files_by_path["unicode.py"].source_text == text


def test_unicode_identifier_normalization_matches_parser_definition():
    index = index_for(
        "def K():\n"
        "    return 1\n"
    )

    assert len(index.definition_scope_keys_by_local_key) == 1


def test_unknown_node_context_has_explicit_error():
    index = index_for("helper()\n")

    with pytest.raises(RepoIndexError) as exc:
        index.context_for("app.py", "Call", 100, 108)

    assert exc.value.code == "UNKNOWN_NODE_CONTEXT"
    assert exc.value.file_path == "app.py"


@pytest.mark.parametrize(
    "attribute",
    [
        "scopes_by_key",
        "module_scope_keys_by_path",
        "definition_scope_keys_by_local_key",
        "contexts_by_location",
    ],
)
def test_scope_mapping_entries_are_read_only(attribute):
    index = index_for(
        "def caller():\n"
        "    return helper()\n"
    )
    mapping = getattr(index, attribute)
    key = next(iter(mapping))

    with pytest.raises(TypeError):
        mapping[key] = mapping[key]

    with pytest.raises(TypeError):
        del mapping[key]


def test_scope_index_revalidates_repository_buffers():
    repo = build_repo_index([
        parse_python(
            b"def caller():\n    return helper()\n",
            file_path="app.py",
        )
    ])

    repo.files_by_path["app.py"].source_text = (
        "def caller():\n    return changed()\n"
    )

    with pytest.raises(RepoIndexError) as exc:
        build_scope_index(repo)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARSE_BUFFER_HASH_MISMATCH",
    }


def test_multiple_files_have_distinct_module_scopes():
    files = [
        parse_python(b"helper()\n", file_path="a.py"),
        parse_python(b"helper()\n", file_path="b.py"),
    ]

    index = build_scope_index(build_repo_index(files))

    assert set(index.module_scope_keys_by_path) == {"a.py", "b.py"}
    assert len(set(index.module_scope_keys_by_path.values())) == 2

    for file_path in ("a.py", "b.py"):
        context = call_context(
            index,
            "helper",
            file_path=file_path,
        )
        assert context.scope_key == index.module_scope_keys_by_path[
            file_path
        ]


def test_file_input_order_does_not_change_scope_index():
    files = [
        parse_python(
            b"def caller():\n    return helper()\n",
            file_path="z.py",
        ),
        parse_python(
            b"class Service:\n    pass\n",
            file_path="a.py",
        ),
    ]

    forward = build_scope_index(build_repo_index(files))
    reverse = build_scope_index(build_repo_index(list(reversed(files))))

    for attribute in (
        "scopes_by_key",
        "module_scope_keys_by_path",
        "definition_scope_keys_by_local_key",
        "contexts_by_location",
    ):
        assert list(getattr(forward, attribute)) == list(
            getattr(reverse, attribute)
        )
        assert getattr(forward, attribute) == getattr(reverse, attribute)