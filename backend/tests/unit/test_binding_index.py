import json

import pytest

from reposcope.parsing.binding_index import (
    BindingIndex,
    build_binding_index,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import RepoIndexError, build_repo_index
from reposcope.parsing.scope_index import build_scope_index


def index_for(
    source: str,
    *,
    file_path: str = "app.py",
) -> BindingIndex:
    parsed = parse_python(
        source.encode("utf-8"),
        file_path=file_path,
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    return build_binding_index(scopes)


def module_key(
    index: BindingIndex,
    file_path: str = "app.py",
) -> str:
    return index.scope_index.module_scope_keys_by_path[file_path]


def definition_scope_key(
    index: BindingIndex,
    qualname: str,
    *,
    file_path: str = "app.py",
) -> str:
    scopes = index.scope_index

    for local_key, scope_key in (
        scopes.definition_scope_keys_by_local_key.items()
    ):
        scope = scopes.scopes_by_key[scope_key]
        symbol = scopes.repo_index.definitions_by_local_key[local_key]

        if scope.file_path == file_path and symbol.qualname == qualname:
            return scope_key

    raise AssertionError(f"definition scope not found: {qualname}")


def branch_names(event) -> list[str]:
    return [
        json.loads(label)[-1]
        for label in event.control_path
    ]


def test_empty_repository():
    scopes = build_scope_index(build_repo_index([]))
    index = build_binding_index(scopes)

    assert index.coverage == "static_bindings"
    assert not index.local_names_by_scope
    assert not index.events_by_scope
    assert not index.events_by_binding_scope_and_name
    assert not index.control_paths_by_location


def test_declarations_imports_and_parameters_are_preserved():
    index = index_for(
        "import package as api\n"
        "def caller(value):\n"
        "    return value\n"
    )
    module = module_key(index)
    caller = definition_scope_key(index, "caller")

    imported, = index.events_for(module, "api")
    definition, = index.events_for(module, "caller")
    parameter, = index.events_for(caller, "value")

    assert imported.kind == "import"
    assert imported.import_info.module == "package"
    assert definition.kind == "definition"
    assert definition.definition_target is not None
    assert parameter.kind == "parameter"
    assert parameter.parameter_kind == "positional_or_keyword"
    assert parameter.binding_scope_key == caller

    indexed_definition = index.scope_index.repo_index.validate_target(
        definition.definition_target
    )
    assert indexed_definition.name == "caller"


def test_assignment_records_value_and_post_rhs_activation():
    index = index_for("receiver = Constructor()\n")
    module = module_key(index)
    event, = index.events_for(module, "receiver")

    assert event.kind == "assignment"
    assert event.scope_key == module
    assert event.binding_scope_key == module
    assert event.namespace == "global"
    assert event.control_path == ()

    file_path, node_kind, start, end = event.value_location
    buffer = index.scope_index.repo_index.files_by_path[
        file_path
    ].source_text.encode("utf-8")

    assert node_kind == "Call"
    assert buffer[start:end] == b"Constructor()"
    assert event.activation_byte >= end


def test_chained_assignment_preserves_both_names():
    index = index_for("first = second = Constructor()\n")
    module = module_key(index)

    first, = index.events_for(module, "first")
    second, = index.events_for(module, "second")

    assert first.kind == second.kind == "assignment"
    assert first.value_location == second.value_location
    assert first.activation_byte == second.activation_byte
    assert first.ordinal != second.ordinal


def test_destructuring_does_not_assign_whole_rhs_to_each_name():
    index = index_for(
        "first, (second, *rest) = values\n"
    )
    module = module_key(index)

    for name in ("first", "second", "rest"):
        event, = index.events_for(module, name)
        assert event.kind == "assignment"
        assert event.value_location is None


def test_annotation_without_value_is_not_runtime_assignment():
    index = index_for(
        "declared: Type\n"
        "initialized: Type = Constructor()\n"
    )
    module = module_key(index)

    declared, = index.events_for(module, "declared")
    initialized, = index.events_for(module, "initialized")

    assert declared.kind == "annotation"
    assert declared.value_location is None
    assert initialized.kind == "assignment"
    assert initialized.value_location is not None


def test_augmented_assignment_does_not_claim_rhs_is_new_value():
    index = index_for(
        "value = 1\n"
        "value += other\n"
    )
    events = index.events_for(module_key(index), "value")

    assert len(events) == 2
    assert all(event.kind == "assignment" for event in events)
    assert events[1].value_location is None


def test_later_local_assignment_prevents_outer_name_fallback():
    index = index_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    helper()\n"
        "    helper = unknown\n"
    )

    module = module_key(index)
    caller = definition_scope_key(index, "caller")

    assert "helper" in index.local_names_by_scope[caller]
    assert index.events_for(module, "helper")[0].kind == "definition"
    assert index.events_for(caller, "helper")[0].kind == "assignment"


def test_parameter_is_in_function_local_names():
    index = index_for(
        "def caller(helper):\n"
        "    return helper()\n"
    )
    caller = definition_scope_key(index, "caller")

    assert "helper" in index.local_names_by_scope[caller]
    assert index.events_for(caller, "helper")[0].kind == "parameter"


def test_global_write_routes_to_module_but_keeps_execution_scope():
    index = index_for(
        "def caller():\n"
        "    global receiver\n"
        "    receiver = Constructor()\n"
    )

    module = module_key(index)
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(module, "receiver")

    assert event.scope_key == caller
    assert event.binding_scope_key == module
    assert event.namespace == "global"
    assert "receiver" not in index.local_names_by_scope[caller]


def test_nonlocal_write_routes_to_enclosing_function():
    index = index_for(
        "def outer():\n"
        "    receiver = First()\n"
        "    def inner():\n"
        "        nonlocal receiver\n"
        "        receiver = Second()\n"
        "    return inner\n"
    )

    outer = definition_scope_key(index, "outer")
    inner = definition_scope_key(index, "outer.inner")
    events = index.events_for(outer, "receiver")

    assert len(events) == 2
    assert {event.scope_key for event in events} == {outer, inner}
    assert all(event.binding_scope_key == outer for event in events)

    inner_event = next(
        event
        for event in events
        if event.scope_key == inner
    )
    assert inner_event.namespace == "nonlocal"
    assert "receiver" not in index.local_names_by_scope[inner]


def test_nonlocal_routes_to_nearest_function_with_local_binding():
    index = index_for(
        "def outer():\n"
        "    value = 1\n"
        "    def middle():\n"
        "        value = 2\n"
        "        def inner():\n"
        "            nonlocal value\n"
        "            value = 3\n"
        "        return inner\n"
        "    return middle\n"
    )

    outer = definition_scope_key(index, "outer")
    middle = definition_scope_key(index, "outer.middle")
    inner = definition_scope_key(index, "outer.middle.inner")

    assert len(index.events_for(outer, "value")) == 1

    middle_events = index.events_for(middle, "value")
    assert len(middle_events) == 2
    assert any(
        event.scope_key == inner
        and event.binding_scope_key == middle
        for event in middle_events
    )


def test_if_branches_have_distinct_control_paths():
    index = index_for(
        "if flag:\n"
        "    receiver = First()\n"
        "else:\n"
        "    receiver = Second()\n"
    )

    events = index.events_for(module_key(index), "receiver")

    assert len(events) == 2
    assert branch_names(events[0]) == ["body"]
    assert branch_names(events[1]) == ["else"]
    assert events[0].control_path != events[1].control_path


def test_conditional_definition_keeps_path_but_function_body_resets_it():
    index = index_for(
        "if flag:\n"
        "    def caller(value):\n"
        "        local = Constructor()\n"
        "        return local\n"
    )

    module = module_key(index)
    caller = definition_scope_key(index, "caller")

    definition, = index.events_for(module, "caller")
    parameter, = index.events_for(caller, "value")
    local, = index.events_for(caller, "local")

    assert branch_names(definition) == ["body"]
    assert parameter.control_path == ()
    assert local.control_path == ()


@pytest.mark.parametrize(
    "statement",
    [
        "flag and (value := Constructor())",
        "flag or (value := Constructor())",
    ],
)
def test_short_circuit_walrus_has_conditional_path(statement):
    index = index_for(statement + "\n")
    event, = index.events_for(module_key(index), "value")

    assert event.kind == "assignment"
    assert branch_names(event) == ["short-circuit:1"]


def test_conditional_expression_writes_have_distinct_paths():
    index = index_for(
        "(value := First()) if flag else (value := Second())\n"
    )
    events = index.events_for(module_key(index), "value")

    assert len(events) == 2
    assert {tuple(branch_names(event)) for event in events} == {
        ("body",),
        ("else",),
    }


def test_for_and_while_writes_have_control_paths():
    index = index_for(
        "for item in values:\n"
        "    receiver = Constructor()\n"
        "while flag:\n"
        "    other = Constructor()\n"
    )
    module = module_key(index)

    item, = index.events_for(module, "item")
    receiver, = index.events_for(module, "receiver")
    other, = index.events_for(module, "other")

    assert item.kind == "loop"
    assert item.control_path
    assert receiver.control_path
    assert other.control_path


def test_with_targets_are_recorded_without_constructor_inference():
    index = index_for(
        "with acquire() as resource:\n"
        "    value = resource\n"
    )
    module = module_key(index)

    resource, = index.events_for(module, "resource")

    assert resource.kind == "with"
    assert resource.value_location is None
    assert resource.control_path


def test_exception_target_has_binding_and_cleanup_delete():
    index = index_for(
        "def caller():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception as error:\n"
        "        use(error)\n"
    )

    caller = definition_scope_key(index, "caller")
    events = index.events_for(caller, "error")

    assert [event.kind for event in events] == [
        "exception",
        "delete",
    ]
    assert events[0].activation_byte < events[1].activation_byte
    assert events[0].control_path == events[1].control_path
    assert events[0].control_path
    assert "error" in index.local_names_by_scope[caller]


def test_explicit_delete_preserves_name_shadowing_evidence():
    index = index_for(
        "def caller():\n"
        "    del helper\n"
    )
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "helper")

    assert event.kind == "delete"
    assert "helper" in index.local_names_by_scope[caller]


def test_pattern_capture_names_are_collected():
    index = index_for(
        "def caller(value):\n"
        "    match value:\n"
        '        case {"key": captured, **rest}:\n'
        "            selected = captured\n"
        "        case [head, *tail]:\n"
        "            selected = head\n"
    )
    caller = definition_scope_key(index, "caller")

    for name in ("captured", "rest", "head", "tail"):
        event, = index.events_for(caller, name)
        assert event.kind == "pattern"
        assert event.control_path
        assert name in index.local_names_by_scope[caller]


def test_comprehension_target_stays_in_comprehension_scope():
    index = index_for(
        "result = [transform(item) for item in produce()]\n"
    )
    module = module_key(index)
    comprehension = next(
        scope
        for scope in index.scope_index.scopes_by_key.values()
        if scope.kind == "comprehension"
    )

    item, = index.events_for(comprehension.scope_key, "item")

    assert item.kind == "loop"
    assert item.binding_scope_key == comprehension.scope_key
    assert item.control_path
    assert index.events_for(module, "item") == ()
    assert "item" not in index.local_names_by_scope[module]


def test_comprehension_walrus_binds_in_enclosing_function():
    index = index_for(
        "def caller(values):\n"
        "    result = [(captured := item) for item in values]\n"
        "    return captured\n"
    )
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "captured")
    execution_scope = index.scope_index.scopes_by_key[event.scope_key]

    assert execution_scope.kind == "comprehension"
    assert event.binding_scope_key == caller
    assert event.namespace == "local"
    assert event.control_path
    assert "captured" in index.local_names_by_scope[caller]


def test_nested_comprehension_walrus_skips_both_comprehension_scopes():
    index = index_for(
        "def caller(values):\n"
        "    result = [[(captured := item) for item in row] "
        "for row in values]\n"
        "    return captured\n"
    )
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "captured")

    assert event.binding_scope_key == caller
    assert index.scope_index.scopes_by_key[
        event.scope_key
    ].kind == "comprehension"


def test_default_expression_walrus_binds_outside_function():
    index = index_for(
        "def caller(value=(captured := Constructor())):\n"
        "    return value\n"
    )
    module = module_key(index)
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(module, "captured")

    assert event.scope_key == module
    assert event.binding_scope_key == module
    assert "captured" not in index.local_names_by_scope[caller]


@pytest.mark.parametrize(
    "source",
    [
        "obj.member = replacement\n",
        "obj[index] = replacement\n",
        "del obj.member\n",
        "del obj[index]\n",
    ],
)
def test_attribute_and_item_writes_are_uncertainty_markers(source):
    index = index_for(source)
    module = module_key(index)
    mutations = [
        event
        for event in index.events_by_scope[module]
        if event.kind == "namespace_mutation"
    ]

    assert len(mutations) == 1
    assert mutations[0].name is None
    assert mutations[0].binding_scope_key is None


@pytest.mark.parametrize(
    "source",
    [
        "exec(code)\n",
        "eval(code)\n",
        "globals()\n",
        "locals()\n",
        "vars(obj)\n",
    ],
)
def test_possible_dynamic_namespace_calls_are_marked(source):
    index = index_for(source)
    module = module_key(index)
    markers = [
        event
        for event in index.events_by_scope[module]
        if event.kind == "dynamic_namespace"
    ]

    assert len(markers) == 1
    assert markers[0].name is None
    assert markers[0].binding_scope_key is None


@pytest.mark.parametrize(
    "source",
    [
        'setattr(obj, "member", replacement)\n',
        'delattr(obj, "member")\n',
    ],
)
def test_possible_builtin_attribute_mutations_are_marked(source):
    index = index_for(source)
    module = module_key(index)

    assert any(
        event.kind == "namespace_mutation"
        for event in index.events_by_scope[module]
    )


def test_wildcard_import_marker_is_preserved():
    index = index_for("from package import *\n")
    module = module_key(index)
    event, = index.events_by_scope[module]

    assert event.kind == "wildcard_import"
    assert event.name is None
    assert event.binding_scope_key is None
    assert event.import_info.imported_name == "*"


def test_annotations_retain_resolution_blockers_for_nested_writes():
    index = index_for(
        "def caller(value: annotation_type()):\n"
        "    local: local_type() = Constructor()\n"
        "    return local\n"
    )
    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "local")

    assert event.kind == "assignment"
    assert event.resolution_blocker is None

    blockers = [
        context.resolution_blocker
        for context in index.scope_index.contexts_by_location.values()
    ]
    assert "ANNOTATION_SEMANTICS_NOT_MODELED" in blockers


def test_control_path_is_available_for_reference_source_node():
    source = (
        "if flag:\n"
        "    receiver = Constructor()\n"
    )
    index = index_for(source)
    event, = index.events_for(module_key(index), "receiver")

    assert index.control_paths_by_location[
        event.value_location
    ] == event.control_path


def test_no_repository_code_is_executed():
    index = index_for(
        "raise RuntimeError('must not execute')\n"
        "receiver = Constructor()\n"
    )

    assert index.events_for(
        module_key(index),
        "receiver",
    )[0].kind == "assignment"


@pytest.mark.parametrize(
    "attribute",
    [
        "directives_by_scope",
        "local_names_by_scope",
        "events_by_scope",
        "events_by_binding_scope_and_name",
        "control_paths_by_location",
    ],
)
def test_mapping_entries_are_read_only(attribute):
    index = index_for(
        "def caller(value):\n"
        "    local = value\n"
    )
    mapping = getattr(index, attribute)
    key = next(iter(mapping))

    with pytest.raises(TypeError):
        mapping[key] = mapping[key]

    with pytest.raises(TypeError):
        del mapping[key]


def test_binding_index_revalidates_source_buffers():
    parsed = parse_python(
        b"value = 1\n",
        file_path="app.py",
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    scopes.repo_index.files_by_path["app.py"].source_text = (
        "value = 2\n"
    )

    with pytest.raises(RepoIndexError) as exc:
        build_binding_index(scopes)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARSE_BUFFER_HASH_MISMATCH",
    }


def test_file_order_does_not_change_binding_records():
    files = [
        parse_python(
            b"def caller(value):\n    local = Constructor()\n",
            file_path="z.py",
        ),
        parse_python(
            b"import package as api\n",
            file_path="a.py",
        ),
    ]

    forward = build_binding_index(
        build_scope_index(build_repo_index(files))
    )
    reverse = build_binding_index(
        build_scope_index(build_repo_index(list(reversed(files))))
    )

    for attribute in (
        "directives_by_scope",
        "local_names_by_scope",
        "events_by_scope",
        "events_by_binding_scope_and_name",
        "control_paths_by_location",
    ):
        assert list(getattr(forward, attribute)) == list(
            getattr(reverse, attribute)
        )
        assert getattr(forward, attribute) == getattr(reverse, attribute)