import pytest

from reposcope.parsing.binding_index import (
    BindingIndex,
    build_binding_index,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import RepoIndexError, build_repo_index
from reposcope.parsing.resolver import (
    ReferenceCollection,
    collect_references,
)
from reposcope.parsing.scope_index import build_scope_index


def bindings_for(
    source: str | bytes,
    *,
    file_path: str = "app.py",
) -> BindingIndex:
    source_bytes = (
        source.encode("utf-8")
        if isinstance(source, str)
        else source
    )
    parsed = parse_python(source_bytes, file_path=file_path)

    return build_binding_index(
        build_scope_index(build_repo_index([parsed]))
    )


def collection_for(
    source: str | bytes,
    *,
    file_path: str = "app.py",
) -> ReferenceCollection:
    return collect_references(
        bindings_for(source, file_path=file_path)
    )


def references_of(
    collection: ReferenceCollection,
    kind: str,
):
    return [
        reference
        for reference in collection.references
        if reference.site.reference_kind == kind
    ]


def owner_qualname(collection: ReferenceCollection, reference):
    target = reference.site.source_owner

    if target.target_kind == "module":
        return None

    return (
        collection.binding_index.scope_index.repo_index
        .definitions_by_local_key[target.symbol_key]
        .qualname
    )


def test_empty_repository():
    bindings = build_binding_index(
        build_scope_index(build_repo_index([]))
    )
    collection = collect_references(bindings)

    assert collection.references == ()
    assert not collection.binding_index.scope_index.repo_index.files_by_path


@pytest.mark.parametrize(
    "source",
    [
        "",
        "# comment only\n",
        "def helper():\n    return 1\n",
        "class Service:\n    pass\n",
    ],
)
def test_source_without_explicit_references(source):
    collection = collection_for(source)

    assert collection.references == ()


def test_module_call_has_module_owner_and_simple_lookup():
    collection = collection_for("helper()\n")
    reference, = collection.references

    assert reference.site.reference_kind == "call"
    assert reference.site.expression == "helper()"
    assert reference.site.source_owner.target_kind == "module"

    assert reference.lookup.head_name == "helper"
    assert reference.lookup.attributes == ()
    assert reference.lookup.location[1] == "Name"

    assert reference.import_info is None
    assert reference.control_path == ()
    assert reference.resolution_blocker is None


def test_function_call_has_function_lookup_scope_and_owner():
    collection = collection_for(
        "def caller():\n"
        "    return helper()\n"
    )
    reference, = collection.references
    scopes = collection.binding_index.scope_index

    assert owner_qualname(collection, reference) == "caller"
    assert scopes.scopes_by_key[
        reference.site.scope_key
    ].kind == "function"
    assert reference.site.start_line == 2
    assert reference.site.end_line == 2


def test_method_call_retains_method_owner():
    collection = collection_for(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n"
    )
    reference, = collection.references
    scopes = collection.binding_index.scope_index

    assert owner_qualname(collection, reference) == "Service.run"
    assert scopes.scopes_by_key[
        reference.site.scope_key
    ].kind == "method"


@pytest.mark.parametrize(
    "expression,head,attributes",
    [
        ("helper()", "helper", ()),
        ("api.helper()", "api", ("helper",)),
        (
            "package.service.helper()",
            "package",
            ("service", "helper"),
        ),
        ("self.run()", "self", ("run",)),
    ],
)
def test_dotted_call_lookup_metadata(expression, head, attributes):
    collection = collection_for(expression + "\n")
    reference, = collection.references

    assert reference.site.expression == expression
    assert reference.lookup.head_name == head
    assert reference.lookup.attributes == attributes


def test_nested_calls_are_separate_references():
    collection = collection_for("outer(inner())\n")
    calls = references_of(collection, "call")

    assert len(calls) == 2
    assert {reference.site.expression for reference in calls} == {
        "outer(inner())",
        "inner()",
    }
    assert len({
        reference.site.reference_key
        for reference in calls
    }) == 2


def test_higher_order_call_is_retained_without_simple_name_guess():
    collection = collection_for("factory()()\n")
    calls = references_of(collection, "call")

    assert len(calls) == 2

    outer = next(
        reference
        for reference in calls
        if reference.site.expression == "factory()()"
    )
    inner = next(
        reference
        for reference in calls
        if reference.site.expression == "factory()"
    )

    assert outer.lookup.head_name is None
    assert outer.lookup.attributes == ()
    assert outer.lookup.location[1] == "Call"

    assert inner.lookup.head_name == "factory"


def test_dynamic_attribute_receiver_is_not_flattened_to_a_name():
    collection = collection_for("factory().run()\n")
    calls = references_of(collection, "call")

    outer = next(
        reference
        for reference in calls
        if reference.site.expression == "factory().run()"
    )

    assert outer.lookup.location[1] == "Attribute"
    assert outer.lookup.head_name is None
    assert outer.lookup.attributes == ()


def test_multi_item_imports_have_individual_sites():
    collection = collection_for(
        "import first, second as local\n"
        "from package import third, fourth as another\n"
    )
    imports = references_of(collection, "import")

    assert len(imports) == 4
    assert [reference.site.expression for reference in imports] == [
        "first",
        "second as local",
        "third",
        "fourth as another",
    ]
    assert all(reference.lookup is None for reference in imports)
    assert all(
        reference.site.source_owner.target_kind == "module"
        for reference in imports
    )

    local = imports[1]

    assert local.import_info.form == "import"
    assert local.import_info.module == "second"
    assert local.import_info.alias == "local"
    assert local.import_info.bound_module == "second"


def test_relative_import_retains_level_module_and_imported_name():
    collection = collection_for(
        "from ..service import helper as local\n",
        file_path="pkg/sub/app.py",
    )
    reference, = collection.references

    assert reference.site.reference_kind == "import"
    assert reference.site.expression == "helper as local"
    assert reference.import_info.form == "from"
    assert reference.import_info.module == "service"
    assert reference.import_info.level == 2
    assert reference.import_info.imported_name == "helper"
    assert reference.import_info.alias == "local"


def test_wildcard_import_is_retained_as_its_own_reference():
    collection = collection_for("from package import *\n")
    reference, = collection.references

    assert reference.site.reference_kind == "import"
    assert reference.site.expression == "*"
    assert reference.import_info.imported_name == "*"
    assert reference.lookup is None


def test_function_import_has_function_owner_and_scope():
    collection = collection_for(
        "def caller():\n"
        "    import package as api\n"
    )
    reference, = collection.references
    scopes = collection.binding_index.scope_index

    assert owner_qualname(collection, reference) == "caller"
    assert scopes.scopes_by_key[
        reference.site.scope_key
    ].kind == "function"


def test_conditional_import_uses_binding_event_control_path():
    collection = collection_for(
        "if flag:\n"
        "    import package as api\n"
    )
    reference, = collection.references
    bindings = collection.binding_index
    module = bindings.scope_index.module_scope_keys_by_path["app.py"]
    event, = bindings.events_for(module, "api")

    assert reference.control_path
    assert reference.control_path == event.control_path


def test_class_bases_use_subclass_owner_and_surrounding_scope():
    collection = collection_for(
        "class Child(Base, package.Other):\n"
        "    pass\n"
    )
    bases = references_of(collection, "base_class")
    scopes = collection.binding_index.scope_index
    module = scopes.module_scope_keys_by_path["app.py"]

    assert len(bases) == 2
    assert [reference.site.expression for reference in bases] == [
        "Base",
        "package.Other",
    ]

    for reference in bases:
        assert owner_qualname(collection, reference) == "Child"
        assert reference.site.scope_key == module

    assert bases[0].lookup.head_name == "Base"
    assert bases[0].lookup.attributes == ()
    assert bases[1].lookup.head_name == "package"
    assert bases[1].lookup.attributes == ("Other",)


def test_base_factory_call_has_call_and_base_reference():
    collection = collection_for(
        "class Child(factory()):\n"
        "    pass\n"
    )

    assert len(collection.references) == 2
    assert {
        reference.site.reference_kind
        for reference in collection.references
    } == {"call", "base_class"}
    assert all(
        reference.site.expression == "factory()"
        for reference in collection.references
    )
    assert len({
        reference.site.reference_key
        for reference in collection.references
    }) == 2

    call, = references_of(collection, "call")
    base, = references_of(collection, "base_class")

    assert call.lookup.head_name == "factory"
    assert base.lookup.head_name is None

    assert owner_qualname(collection, call) == "Child"
    assert owner_qualname(collection, base) == "Child"


def test_decorator_call_validates_with_decorated_owner():
    collection = collection_for(
        "@decorate()\n"
        "def caller():\n"
        "    return 1\n"
    )
    reference, = collection.references
    scopes = collection.binding_index.scope_index
    parsed = scopes.repo_index.files_by_path["app.py"]

    assert owner_qualname(collection, reference) == "caller"
    assert reference.site.scope_key == (
        scopes.module_scope_keys_by_path["app.py"]
    )
    assert reference.site.validate_against_file(parsed) is reference.site


def test_default_and_body_calls_have_distinct_lookup_scopes():
    collection = collection_for(
        "def caller(value=default_factory()):\n"
        "    return body_call()\n"
    )
    scopes = collection.binding_index.scope_index

    default = next(
        reference
        for reference in collection.references
        if reference.lookup.head_name == "default_factory"
    )
    body = next(
        reference
        for reference in collection.references
        if reference.lookup.head_name == "body_call"
    )

    assert default.site.scope_key == (
        scopes.module_scope_keys_by_path["app.py"]
    )
    assert scopes.scopes_by_key[body.site.scope_key].kind == "function"

    assert owner_qualname(collection, default) == "caller"
    assert owner_qualname(collection, body) == "caller"


def test_annotation_calls_are_retained_with_resolution_blockers():
    collection = collection_for(
        "def caller(value: parameter_type()) -> return_type():\n"
        "    local: local_type() = actual_value()\n"
        "    return local\n"
    )

    calls = {
        reference.lookup.head_name: reference
        for reference in references_of(collection, "call")
    }

    for name in ("parameter_type", "return_type", "local_type"):
        assert calls[name].resolution_blocker == (
            "ANNOTATION_SEMANTICS_NOT_MODELED"
        )

    assert calls["actual_value"].resolution_blocker is None


def test_comprehension_calls_keep_outer_and_inner_contexts():
    collection = collection_for(
        "result = [transform(item) "
        "for item in produce() "
        "if accept(item)]\n"
    )
    scopes = collection.binding_index.scope_index

    calls = {
        reference.lookup.head_name: reference
        for reference in references_of(collection, "call")
    }

    assert calls["produce"].site.scope_key == (
        scopes.module_scope_keys_by_path["app.py"]
    )

    inner_key = calls["transform"].site.scope_key

    assert scopes.scopes_by_key[inner_key].kind == "comprehension"
    assert calls["accept"].site.scope_key == inner_key
    assert calls["transform"].control_path
    assert calls["accept"].control_path


def test_multiline_call_preserves_exact_source_text():
    source = (
        "helper(\n"
        '    "café",\n'
        ")\n"
    )
    collection = collection_for(source)
    reference, = collection.references

    assert reference.site.expression == source[:-1]
    assert reference.site.start_line == 1
    assert reference.site.end_line == 3
    assert reference.site.end_byte == len(source.encode("utf-8")) - 1


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [False, True])
def test_unicode_bom_and_crlf_reference_positions(newline, bom):
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

    collection = collection_for(source, file_path="unicode.py")
    reference, = collection.references
    buffer = text.encode("utf-8")

    assert reference.site.expression == "café()"
    assert reference.lookup.head_name == "café"
    assert reference.site.start_line == 5
    assert reference.site.end_line == 5
    assert buffer[
        reference.site.start_byte:reference.site.end_byte
    ] == "café()".encode("utf-8")

    parsed = (
        collection.binding_index.scope_index.repo_index
        .files_by_path["unicode.py"]
    )
    assert reference.site.validate_against_file(parsed) is reference.site


def test_every_site_validates_against_its_owned_file():
    collection = collection_for(
        "import package as api\n"
        "@decorate()\n"
        "class Child(Base):\n"
        "    def run(self):\n"
        "        return api.helper()\n"
    )
    repo = collection.binding_index.scope_index.repo_index

    for reference in collection.references:
        parsed = repo.files_by_path[reference.site.file_path]

        assert reference.site.validate_against_file(parsed) is (
            reference.site
        )
        repo.validate_target(reference.site.source_owner)


def test_collection_is_sorted_and_reference_keys_are_unique():
    collection = collection_for(
        "import package as api\n"
        "class Child(factory()):\n"
        "    def run(self):\n"
        "        return outer(inner())\n"
    )

    positions = [
        (
            reference.site.file_path,
            reference.site.start_byte,
            reference.site.end_byte,
            reference.site.reference_kind,
        )
        for reference in collection.references
    ]
    keys = [
        reference.site.reference_key
        for reference in collection.references
    ]

    assert positions == sorted(positions)
    assert len(keys) == len(set(keys))


def test_collection_owns_revalidated_binding_records():
    original = bindings_for(
        "def caller():\n"
        "    return helper()\n"
    )
    collection = collect_references(original)

    assert collection.binding_index is not original

    original.scope_index.repo_index.files_by_path[
        "app.py"
    ].source_text = "changed after collection"

    owned = (
        collection.binding_index.scope_index.repo_index
        .files_by_path["app.py"]
    )
    reference, = collection.references

    assert reference.site.validate_against_file(owned) is reference.site


def test_collection_rejects_stale_source_buffers():
    original = bindings_for("helper()\n")
    original.scope_index.repo_index.files_by_path[
        "app.py"
    ].source_text = "changed()\n"

    with pytest.raises(RepoIndexError) as exc:
        collect_references(original)

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "PARSE_BUFFER_HASH_MISMATCH",
    }


def test_file_order_does_not_change_reference_collection():
    files = [
        parse_python(
            b"helper()\n",
            file_path="z.py",
        ),
        parse_python(
            b"from package import helper\n",
            file_path="a.py",
        ),
    ]

    forward = collect_references(
        build_binding_index(
            build_scope_index(build_repo_index(files))
        )
    )
    reverse = collect_references(
        build_binding_index(
            build_scope_index(build_repo_index(list(reversed(files))))
        )
    )

    assert forward.references == reverse.references