import pytest

from reposcope.parsing.declaration_index import (
    DeclarationIndex,
    build_declaration_index,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import RepoIndexError, build_repo_index
from reposcope.parsing.scope_index import build_scope_index


def index_for(
    source: str,
    *,
    file_path: str = "app.py",
) -> DeclarationIndex:
    parsed = parse_python(
        source.encode("utf-8"),
        file_path=file_path,
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    return build_declaration_index(scopes)


def module_key(
    index: DeclarationIndex,
    file_path: str = "app.py",
) -> str:
    return index.scope_index.module_scope_keys_by_path[file_path]


def definition_scope_key(
    index: DeclarationIndex,
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


def test_empty_repository():
    scopes = build_scope_index(build_repo_index([]))
    index = build_declaration_index(scopes)

    assert index.is_complete is False
    assert not index.directives_by_scope
    assert not index.events_by_scope
    assert not index.events_by_scope_and_name


def test_partial_index_does_not_claim_assignment_coverage():
    index = index_for("value = 1\n")
    scope_key = module_key(index)

    assert index.is_complete is False
    assert index.events_for(scope_key, "value") == ()


def test_named_definitions_bind_in_surrounding_scope():
    index = index_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n"
    )

    module = module_key(index)
    service = definition_scope_key(index, "Service")
    run = definition_scope_key(index, "Service.run")

    helper_event, = index.events_for(module, "helper")
    class_event, = index.events_for(module, "Service")
    method_event, = index.events_for(service, "run")
    self_event, = index.events_for(run, "self")

    assert helper_event.kind == "definition"
    assert helper_event.namespace == "global"
    assert class_event.kind == "definition"
    assert method_event.kind == "definition"
    assert method_event.namespace == "local"
    assert self_event.kind == "parameter"

    for event in (helper_event, class_event, method_event):
        assert event.definition_target is not None
        definition = index.scope_index.repo_index.validate_target(
            event.definition_target
        )
        assert definition.name == event.name


def test_nested_function_declaration_binds_in_outer_function():
    index = index_for(
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n"
    )

    outer = definition_scope_key(index, "outer")
    inner = definition_scope_key(index, "outer.inner")
    event, = index.events_for(outer, "inner")

    assert event.kind == "definition"
    assert event.namespace == "local"
    assert event.definition_target.symbol_key == (
        index.scope_index.scopes_by_key[inner].source_owner.symbol_key
    )


def test_duplicate_declarations_are_not_overwritten():
    index = index_for(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def helper():\n"
        "    return 2\n"
    )

    events = index.events_for(module_key(index), "helper")

    assert len(events) == 2
    assert all(event.kind == "definition" for event in events)
    assert events[0].start_byte < events[1].start_byte
    assert len({
        event.definition_target.symbol_key
        for event in events
    }) == 2


def test_conditional_declarations_are_retained_without_resolution():
    index = index_for(
        "if flag:\n"
        "    def helper():\n"
        "        return 1\n"
        "else:\n"
        "    def helper():\n"
        "        return 2\n"
    )

    events = index.events_for(module_key(index), "helper")

    assert len(events) == 2
    assert index.is_complete is False


@pytest.mark.parametrize(
    "source,bound_name,module,bound_module,alias",
    [
        ("import package\n", "package", "package", "package", None),
        (
            "import package.service\n",
            "package",
            "package.service",
            "package",
            None,
        ),
        (
            "import package.service as api\n",
            "api",
            "package.service",
            "package.service",
            "api",
        ),
        (
            "import package as api\n",
            "api",
            "package",
            "package",
            "api",
        ),
    ],
)
def test_plain_import_binding(
    source,
    bound_name,
    module,
    bound_module,
    alias,
):
    index = index_for(source)
    event, = index.events_for(module_key(index), bound_name)

    assert event.kind == "import"
    assert event.namespace == "global"
    assert event.definition_target is None
    assert event.import_info.form == "import"
    assert event.import_info.module == module
    assert event.import_info.bound_module == bound_module
    assert event.import_info.alias == alias
    assert event.import_info.level == 0
    assert event.import_info.imported_name is None


@pytest.mark.parametrize(
    "source,bound_name,module,level,imported_name,alias",
    [
        (
            "from package import helper\n",
            "helper",
            "package",
            0,
            "helper",
            None,
        ),
        (
            "from package import helper as local\n",
            "local",
            "package",
            0,
            "helper",
            "local",
        ),
        (
            "from .service import helper\n",
            "helper",
            "service",
            1,
            "helper",
            None,
        ),
        (
            "from ..service import helper as local\n",
            "local",
            "service",
            2,
            "helper",
            "local",
        ),
        (
            "from . import service\n",
            "service",
            None,
            1,
            "service",
            None,
        ),
    ],
)
def test_from_import_binding(
    source,
    bound_name,
    module,
    level,
    imported_name,
    alias,
):
    index = index_for(source)
    event, = index.events_for(module_key(index), bound_name)

    assert event.kind == "import"
    assert event.import_info.form == "from"
    assert event.import_info.module == module
    assert event.import_info.level == level
    assert event.import_info.imported_name == imported_name
    assert event.import_info.alias == alias
    assert event.import_info.bound_module is None


def test_multi_item_imports_have_separate_records():
    index = index_for(
        "import first, second as local\n"
        "from package import third, fourth as another\n"
    )
    module = module_key(index)

    assert len(index.events_by_scope[module]) == 4

    for name in ("first", "local", "third", "another"):
        event, = index.events_for(module, name)
        assert event.kind == "import"

    buffer = index.scope_index.repo_index.files_by_path[
        "app.py"
    ].source_text.encode("utf-8")

    local, = index.events_for(module, "local")

    assert buffer[local.start_byte:local.end_byte] == (
        b"second as local"
    )


def test_repeated_import_alias_keeps_both_events():
    index = index_for(
        "import first as api\n"
        "import second as api\n"
    )

    events = index.events_for(module_key(index), "api")

    assert len(events) == 2
    assert [event.import_info.module for event in events] == [
        "first",
        "second",
    ]


def test_function_import_is_local_to_function():
    index = index_for(
        "def caller():\n"
        "    import package as api\n"
        "    return api\n"
    )

    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "api")

    assert event.namespace == "local"
    assert index.events_for(module_key(index), "api") == ()


def test_wildcard_import_is_marker_not_guessed_names():
    index = index_for("from package import *\n")
    module = module_key(index)
    event, = index.events_by_scope[module]

    assert event.kind == "wildcard_import"
    assert event.name is None
    assert event.import_info.imported_name == "*"
    assert index.events_for(module, "helper") == ()
    assert not index.events_by_scope_and_name


@pytest.mark.parametrize(
    "header,expected",
    [
        (
            "def caller(a, /, b=1, *args, c, d=2, **kwargs):",
            [
                ("a", "positional_only"),
                ("b", "positional_or_keyword"),
                ("args", "var_positional"),
                ("c", "keyword_only"),
                ("d", "keyword_only"),
                ("kwargs", "var_keyword"),
            ],
        ),
        (
            "def caller(a, *, b):",
            [
                ("a", "positional_or_keyword"),
                ("b", "keyword_only"),
            ],
        ),
        (
            "async def caller(value):",
            [
                ("value", "positional_or_keyword"),
            ],
        ),
    ],
)
def test_named_function_parameter_kinds(header, expected):
    index = index_for(f"{header}\n    return 1\n")
    caller = definition_scope_key(index, "caller")

    events = [
        event
        for event in index.events_by_scope[caller]
        if event.kind == "parameter"
    ]

    assert [
        (event.name, event.parameter_kind)
        for event in events
    ] == expected
    assert all(event.namespace == "local" for event in events)
    assert all(event.definition_target is None for event in events)


def test_lambda_parameters_do_not_create_definition_targets():
    index = index_for(
        "callback = lambda a, /, b=1, *args, c=2, **kwargs: a\n"
    )

    scope = next(
        scope
        for scope in index.scope_index.scopes_by_key.values()
        if scope.kind == "lambda"
    )
    events = index.events_by_scope[scope.scope_key]

    assert [
        (event.name, event.parameter_kind)
        for event in events
    ] == [
        ("a", "positional_only"),
        ("b", "positional_or_keyword"),
        ("args", "var_positional"),
        ("c", "keyword_only"),
        ("kwargs", "var_keyword"),
    ]
    assert all(event.kind == "parameter" for event in events)
    assert all(event.definition_target is None for event in events)


def test_self_and_cls_parameters_are_preserved():
    index = index_for(
        "class Service:\n"
        "    def run(self, value):\n"
        "        return value\n"
        "\n"
        "    @classmethod\n"
        "    def build(cls):\n"
        "        return cls()\n"
    )

    run = definition_scope_key(index, "Service.run")
    build = definition_scope_key(index, "Service.build")

    assert index.events_for(run, "self")[0].kind == "parameter"
    assert index.events_for(build, "cls")[0].kind == "parameter"


def test_global_directive_classifies_function_import():
    index = index_for(
        "def caller():\n"
        "    global api\n"
        "    import package as api\n"
    )

    caller = definition_scope_key(index, "caller")
    directive = index.directives_by_scope[caller]
    event, = index.events_for(caller, "api")

    assert directive.global_names == frozenset({"api"})
    assert directive.nonlocal_names == frozenset()
    assert event.namespace == "global"

    # Records retain their execution scope; write routing comes later.
    assert event.scope_key == caller


def test_nonlocal_directive_classifies_import_without_routing_it():
    index = index_for(
        "def outer():\n"
        "    api = None\n"
        "    def inner():\n"
        "        nonlocal api\n"
        "        import package as api\n"
        "    return inner\n"
    )

    outer = definition_scope_key(index, "outer")
    inner = definition_scope_key(index, "outer.inner")
    directive = index.directives_by_scope[inner]
    event, = index.events_for(inner, "api")

    assert directive.nonlocal_names == frozenset({"api"})
    assert directive.global_names == frozenset()
    assert event.namespace == "nonlocal"
    assert event.scope_key == inner

    # Assignment collection is intentionally absent at this stage.
    assert index.events_for(outer, "api") == ()
    assert index.is_complete is False


def test_global_directive_classifies_nested_definition():
    index = index_for(
        "def caller():\n"
        "    global helper\n"
        "    def helper():\n"
        "        return 1\n"
    )

    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "helper")

    assert event.kind == "definition"
    assert event.namespace == "global"
    assert event.definition_target is not None


@pytest.mark.parametrize(
    "source",
    [
        "nonlocal missing\n",
        "def caller():\n    nonlocal missing\n",
        "def caller(value):\n    global value\n",
        "def caller():\n    print(value)\n    global value\n",
    ],
)
def test_invalid_scope_directives_are_rejected(source):
    parsed = parse_python(source.encode("utf-8"), file_path="app.py")
    scopes = build_scope_index(build_repo_index([parsed]))

    with pytest.raises(RepoIndexError) as exc:
        build_declaration_index(scopes)

    assert exc.value.code == "INVALID_SCOPE_DECLARATION"
    assert exc.value.file_path == "app.py"


def test_repository_code_and_defaults_are_not_executed():
    index = index_for(
        "import definitely_missing_reposcope_test_package\n"
        "raise RuntimeError('repository code must not run')\n"
        "def caller(value=must_not_run()):\n"
        "    return value\n"
    )

    module = module_key(index)
    caller = definition_scope_key(index, "caller")

    assert index.events_for(
        module,
        "definitely_missing_reposcope_test_package",
    )[0].kind == "import"
    assert index.events_for(caller, "value")[0].kind == "parameter"


def test_unicode_parameter_names_match_parser_metadata():
    index = index_for(
        "def caller(café):\n"
        "    return café\n"
    )

    caller = definition_scope_key(index, "caller")
    event, = index.events_for(caller, "café")

    assert event.kind == "parameter"
    assert event.parameter_kind == "positional_or_keyword"

    buffer = index.scope_index.repo_index.files_by_path[
        "app.py"
    ].source_text.encode("utf-8")

    assert buffer[event.start_byte:event.end_byte] == (
        "café".encode("utf-8")
    )


def test_changed_parameter_metadata_is_rejected():
    parsed = parse_python(
        b"def caller(value):\n    return value\n",
        file_path="app.py",
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    owned_file = scopes.repo_index.files_by_path["app.py"]
    owned_file.symbols[0].parameters[0].name = "different"

    with pytest.raises(RepoIndexError) as exc:
        build_declaration_index(scopes)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARAMETER_METADATA_MISMATCH",
    }


@pytest.mark.parametrize(
    "attribute",
    [
        "directives_by_scope",
        "events_by_scope",
        "events_by_scope_and_name",
    ],
)
def test_mapping_entries_are_read_only(attribute):
    index = index_for(
        "def caller(value):\n"
        "    import package as api\n"
    )
    mapping = getattr(index, attribute)
    key = next(iter(mapping))

    with pytest.raises(TypeError):
        mapping[key] = mapping[key]

    with pytest.raises(TypeError):
        del mapping[key]


def test_declaration_index_revalidates_source_buffers():
    parsed = parse_python(
        b"def caller():\n    return 1\n",
        file_path="app.py",
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    scopes.repo_index.files_by_path["app.py"].source_text = (
        "def caller():\n    return 2\n"
    )

    with pytest.raises(RepoIndexError) as exc:
        build_declaration_index(scopes)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARSE_BUFFER_HASH_MISMATCH",
    }


def test_file_order_does_not_change_declaration_records():
    files = [
        parse_python(
            b"def caller(value):\n    import package as api\n",
            file_path="z.py",
        ),
        parse_python(
            b"from package import helper\n",
            file_path="a.py",
        ),
    ]

    forward = build_declaration_index(
        build_scope_index(build_repo_index(files))
    )
    reverse = build_declaration_index(
        build_scope_index(build_repo_index(list(reversed(files))))
    )

    for attribute in (
        "directives_by_scope",
        "events_by_scope",
        "events_by_scope_and_name",
    ):
        assert list(getattr(forward, attribute)) == list(
            getattr(reverse, attribute)
        )
        assert getattr(forward, attribute) == getattr(reverse, attribute)