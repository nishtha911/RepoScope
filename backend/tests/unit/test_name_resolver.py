import pytest

from reposcope.parsing.binding_index import build_binding_index
from reposcope.parsing.name_resolver import resolve_simple_names
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import RepoIndexError, build_repo_index
from reposcope.parsing.resolver import collect_references
from reposcope.parsing.scope_index import build_scope_index


def analysis_for(source: str, *, file_path: str = "app.py"):
    parsed = parse_python(
        source.encode("utf-8"),
        file_path=file_path,
    )
    collection = collect_references(
        build_binding_index(
            build_scope_index(build_repo_index([parsed]))
        )
    )
    results = resolve_simple_names(collection)

    return collection, results


def result_for(
    results,
    expression: str,
    *,
    occurrence: int = 0,
    kind: str = "call",
):
    matches = [
        result
        for result in results
        if result.reference.reference_kind == kind
        and result.reference.expression == expression
    ]

    return matches[occurrence]


def target_symbols(collection, result):
    definitions = (
        collection.binding_index.scope_index.repo_index
        .definitions_by_local_key
    )

    return [
        definitions[target.symbol_key]
        for target in result.targets
    ]


def assert_exact(collection, result, qualname: str):
    assert result.status == "EXACT"
    assert result.confidence == 1.0
    assert len(result.targets) == 1
    assert target_symbols(collection, result)[0].qualname == qualname
    assert result.rule_id == "EXACT_NAMED_DEFINITION"


def assert_unresolved(result, rule_id: str | None = None):
    assert result.status == "UNRESOLVED"
    assert result.targets == []
    assert result.confidence is None

    if rule_id is not None:
        assert result.rule_id == rule_id


def test_empty_repository():
    collection = collect_references(
        build_binding_index(
            build_scope_index(build_repo_index([]))
        )
    )

    assert resolve_simple_names(collection) == ()


def test_module_function_call_is_exact():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_class_constructor_call_targets_class_not_implicit_method():
    collection, results = analysis_for(
        "class Service:\n"
        "    def __init__(self):\n"
        "        self.value = 1\n"
        "\n"
        "Service()\n"
    )
    result = result_for(results, "Service()")

    assert_exact(collection, result, "Service")
    assert target_symbols(collection, result)[0].kind == "class"


def test_module_call_before_definition_is_unresolved():
    _, results = analysis_for(
        "helper()\n"
        "\n"
        "def helper():\n"
        "    return 1\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "NAME_NOT_ESTABLISHED",
    )


def test_sequential_redefinition_selects_latest_available_definition():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "helper()\n"
        "\n"
        "def helper():\n"
        "    return 2\n"
        "\n"
        "helper()\n"
    )

    first = result_for(results, "helper()", occurrence=0)
    second = result_for(results, "helper()", occurrence=1)

    assert_exact(collection, first, "helper")
    assert_exact(collection, second, "helper")

    first_symbol = target_symbols(collection, first)[0]
    second_symbol = target_symbols(collection, second)[0]

    assert first_symbol.start_line == 1
    assert second_symbol.start_line == 6
    assert first.targets[0].symbol_key != second.targets[0].symbol_key


def test_recursive_function_name_is_exact():
    collection, results = analysis_for(
        "def helper():\n"
        "    return helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_deferred_function_can_reference_later_module_definition():
    collection, results = analysis_for(
        "def caller():\n"
        "    return helper()\n"
        "\n"
        "def helper():\n"
        "    return 1\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_deferred_lookup_retains_multiple_module_definitions():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    return helper()\n"
        "\n"
        "def helper():\n"
        "    return 2\n"
    )
    result = result_for(results, "helper()")

    assert result.status == "AMBIGUOUS"
    assert result.confidence is None
    assert len(result.targets) == 2
    assert {
        symbol.start_line
        for symbol in target_symbols(collection, result)
    } == {1, 7}


def test_nested_definition_available_before_call_is_exact():
    collection, results = analysis_for(
        "def caller():\n"
        "    def helper():\n"
        "        return 1\n"
        "    return helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "caller.helper",
    )


def test_later_function_local_definition_stops_outer_fallback():
    _, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    helper()\n"
        "    def helper():\n"
        "        return 2\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "LOCAL_BINDING_NOT_AVAILABLE",
    )


@pytest.mark.parametrize(
    "body",
    [
        "    return helper()\n",
        "    helper()\n    helper = unknown\n",
    ],
)
def test_parameter_or_later_assignment_stops_outer_fallback(body):
    parameter = "helper" if body.startswith("    return") else ""

    _, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        f"def caller({parameter}):\n"
        f"{body}"
    )

    assert_unresolved(result_for(results, "helper()"))


def test_unknown_assignment_overwrites_named_definition():
    _, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "helper = unknown\n"
        "helper()\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "SHADOWED_OR_UNKNOWN_BINDING",
    )


def test_new_definition_can_replace_earlier_unknown_assignment():
    collection, results = analysis_for(
        "helper = unknown\n"
        "\n"
        "def helper():\n"
        "    return 1\n"
        "\n"
        "helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_delete_does_not_reuse_previous_definition():
    _, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "del helper\n"
        "helper()\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "SHADOWED_OR_UNKNOWN_BINDING",
    )


def test_global_directive_uses_module_definition():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    global helper\n"
        "    return helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_current_frame_global_definition_supersedes_module_definition():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    global helper\n"
        "    def helper():\n"
        "        return 2\n"
        "    return helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "caller.helper",
    )


def test_nonlocal_directive_uses_enclosing_function_definition():
    collection, results = analysis_for(
        "def outer():\n"
        "    def helper():\n"
        "        return 1\n"
        "    def inner():\n"
        "        nonlocal helper\n"
        "        return helper()\n"
        "    return inner\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "outer.helper",
    )


def test_unknown_nonlocal_write_prevents_exact_definition_target():
    _, results = analysis_for(
        "def outer():\n"
        "    def helper():\n"
        "        return 1\n"
        "    def inner():\n"
        "        nonlocal helper\n"
        "        helper = unknown\n"
        "        return helper()\n"
        "    return inner\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "SHADOWED_OR_UNKNOWN_BINDING",
    )


def test_method_does_not_search_class_namespace_for_bare_name():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    def helper(self):\n"
        "        return 2\n"
        "    def run(self):\n"
        "        return helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_class_body_can_use_enclosing_function_free_name():
    collection, results = analysis_for(
        "def outer():\n"
        "    def helper():\n"
        "        return 1\n"
        "    class Service:\n"
        "        value = helper()\n"
        "    return Service\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "outer.helper",
    )


def test_unavailable_class_local_name_falls_back_to_globals():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def outer():\n"
        "    def helper():\n"
        "        return 2\n"
        "    class Service:\n"
        "        value = helper()\n"
        "        helper = unknown\n"
        "    return Service\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_conditional_single_definition_is_not_certain_after_branch():
    _, results = analysis_for(
        "if flag:\n"
        "    def helper():\n"
        "        return 1\n"
        "\n"
        "helper()\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "CONDITIONAL_BINDING_NOT_ESTABLISHED",
    )


def test_definition_established_in_same_branch_is_exact():
    collection, results = analysis_for(
        "if flag:\n"
        "    def helper():\n"
        "        return 1\n"
        "    helper()\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_opposite_branch_definition_is_not_a_candidate():
    _, results = analysis_for(
        "if flag:\n"
        "    def helper():\n"
        "        return 1\n"
        "else:\n"
        "    helper()\n"
    )

    assert_unresolved(result_for(results, "helper()"))


def test_two_conditional_definitions_are_ambiguous_after_branch():
    _, results = analysis_for(
        "if flag:\n"
        "    def helper():\n"
        "        return 1\n"
        "else:\n"
        "    def helper():\n"
        "        return 2\n"
        "\n"
        "helper()\n"
    )
    result = result_for(results, "helper()")

    assert result.status == "AMBIGUOUS"
    assert len(result.targets) == 2
    assert result.confidence is None


def test_exact_base_target_must_be_class():
    collection, results = analysis_for(
        "class Base:\n"
        "    pass\n"
        "\n"
        "class Child(Base):\n"
        "    pass\n"
    )

    assert_exact(
        collection,
        result_for(results, "Base", kind="base_class"),
        "Base",
    )


def test_function_is_not_accepted_as_exact_base_target():
    _, results = analysis_for(
        "def Base():\n"
        "    return 1\n"
        "\n"
        "class Child(Base):\n"
        "    pass\n"
    )

    assert_unresolved(
        result_for(results, "Base", kind="base_class"),
        "BASE_TARGET_NOT_ESTABLISHED_AS_CLASS",
    )


def test_imports_and_imported_name_calls_are_explicitly_pending():
    _, results = analysis_for(
        "from package import helper\n"
        "helper()\n"
    )

    assert len(results) == 2
    assert all(
        result.rule_id == "IMPORT_LOOKUP_PENDING"
        for result in results
    )
    assert all(result.status == "UNRESOLVED" for result in results)


def test_dotted_attribute_call_is_explicitly_pending():
    _, results = analysis_for("api.helper()\n")

    assert_unresolved(
        result_for(results, "api.helper()"),
        "ATTRIBUTE_LOOKUP_PENDING",
    )


def test_dynamic_callable_expression_is_retained_as_unresolved():
    _, results = analysis_for("factory()()\n")

    assert_unresolved(
        result_for(results, "factory()()"),
        "DYNAMIC_LOOKUP_EXPRESSION",
    )


def test_annotation_reference_is_blocked():
    _, results = analysis_for(
        "def annotation_type():\n"
        "    return int\n"
        "\n"
        "def caller(value: annotation_type()):\n"
        "    return value\n"
    )

    assert_unresolved(
        result_for(results, "annotation_type()"),
        "BLOCKED_REFERENCE",
    )


@pytest.mark.parametrize(
    "uncertainty",
    [
        "from package import *",
        "exec(code)",
        "globals()",
        "module.helper = replacement",
    ],
)
def test_relevant_namespace_uncertainty_prevents_exact(uncertainty):
    _, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        f"{uncertainty}\n"
        "helper()\n"
    )

    assert_unresolved(
        result_for(results, "helper()"),
        "NAMESPACE_UNCERTAINTY",
    )


def test_later_immediate_mutation_does_not_block_earlier_call():
    collection, results = analysis_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "helper()\n"
        "module.helper = replacement\n"
    )

    assert_exact(
        collection,
        result_for(results, "helper()"),
        "helper",
    )


def test_unicode_normalized_name_keeps_original_symbol_identity():
    collection, results = analysis_for(
        "def K():\n"
        "    return 1\n"
        "\n"
        "K()\n"
    )

    assert_exact(
        collection,
        result_for(results, "K()"),
        "K",
    )


def test_every_collected_reference_has_one_result_and_reason():
    collection, results = analysis_for(
        "import package as api\n"
        "class Base:\n"
        "    pass\n"
        "class Child(Base):\n"
        "    def run(self):\n"
        "        return api.helper()\n"
    )

    assert len(results) == len(collection.references)
    assert [
        result.reference.reference_key
        for result in results
    ] == [
        reference.site.reference_key
        for reference in collection.references
    ]

    for result in results:
        assert result.rule_id.strip()
        assert result.reason.strip()
        assert result.status != "INFERRED"

        if result.status == "EXACT":
            assert len(result.targets) == 1
            assert result.confidence == 1.0
        elif result.status == "AMBIGUOUS":
            assert len(result.targets) >= 2
            assert result.confidence is None
        else:
            assert result.targets == []
            assert result.confidence is None


def test_resolution_rejects_stale_source_buffers():
    parsed = parse_python(
        b"def helper():\n    return 1\n\nhelper()\n",
        file_path="app.py",
    )
    collection = collect_references(
        build_binding_index(
            build_scope_index(build_repo_index([parsed]))
        )
    )

    collection.binding_index.scope_index.repo_index.files_by_path[
        "app.py"
    ].source_text = "changed source"

    with pytest.raises(RepoIndexError) as exc:
        resolve_simple_names(collection)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARSE_BUFFER_HASH_MISMATCH",
    }