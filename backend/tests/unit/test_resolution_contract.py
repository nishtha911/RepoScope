import json

import pytest
from pydantic import ValidationError

from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import (
    ModuleInfo,
    ReferenceSite,
    ResolutionResult,
    ResolverTarget,
    make_module_key,
    make_reference_key,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.scope_index import build_scope_index


SOURCE = (
    "def helper():\n"
    "    return 1\n"
    "\n"
    "def other():\n"
    "    return 2\n"
    "\n"
    "def caller():\n"
    "    return helper()\n"
)


@pytest.fixture
def parsed_file() -> ParsedFile:
    return parse_python(
        SOURCE.encode("utf-8"),
        file_path="pkg/service.py",
    )


def target_for(
    parsed_file: ParsedFile,
    qualname: str | None = None,
) -> ResolverTarget:
    symbol_key = None

    if qualname is not None:
        symbol = next(
            symbol
            for symbol in parsed_file.symbols
            if symbol.qualname == qualname
        )
        symbol_key = symbol.local_key

    return ResolverTarget(
        target_kind="module" if qualname is None else "symbol",
        module_key=make_module_key(".", parsed_file.file_path),
        file_path=parsed_file.file_path,
        symbol_key=symbol_key,
    )


def site_for(
    parsed_file: ParsedFile,
    expression: str = "helper()",
    *,
    reference_kind: str = "call",
    owner: str | None = "caller",
) -> ReferenceSite:
    buffer = parsed_file.source_text.encode("utf-8")
    expression_bytes = expression.encode("utf-8")
    start_byte = buffer.rindex(expression_bytes)
    end_byte = start_byte + len(expression_bytes)

    # Fixture-only scope identifier; Pass 1 supplies actual scope keys.
    scope_key = f"fixture-scope:{owner or 'module'}"

    return ReferenceSite(
        reference_key=make_reference_key(
            parsed_file.file_path,
            reference_kind,
            start_byte,
            end_byte,
            scope_key,
        ),
        reference_kind=reference_kind,
        file_path=parsed_file.file_path,
        source_sha256=parsed_file.source_sha256,
        parse_buffer_sha256=parsed_file.parse_buffer_sha256,
        scope_key=scope_key,
        source_owner=target_for(parsed_file, owner),
        expression=expression,
        start_line=buffer.count(b"\n", 0, start_byte) + 1,
        end_line=buffer.count(b"\n", 0, end_byte - 1) + 1,
        start_byte=start_byte,
        end_byte=end_byte,
    )


def result_for(
    parsed_file: ParsedFile,
    *,
    status: str = "EXACT",
    names: tuple[str, ...] = ("helper",),
    confidence: float | None = 1.0,
) -> ResolutionResult:
    return ResolutionResult(
        reference=site_for(parsed_file),
        status=status,
        targets=[
            target_for(parsed_file, name)
            for name in names
        ],
        rule_id="fixture_rule",
        reason="Contract test fixture; no resolver has run.",
        confidence=confidence,
    )


@pytest.mark.parametrize(
    "root,path,name",
    [
        (".", "service.py", "service"),
        (".", "pkg/service.py", "pkg.service"),
        (".", "pkg/__init__.py", "pkg"),
        ("backend", "backend/pkg/service.py", "pkg.service"),
        (".", "__init__.py", None),
        ("src", "src/__init__.py", None),
        (".", "foo-bar.py", None),
        (".", "class.py", None),
        (".", "café/service.py", "café.service"),
    ],
)
def test_module_identity(root, path, name):
    module = ModuleInfo(
        module_key=make_module_key(root, path),
        file_path=path,
        source_root=root,
        module_name=name,
    )

    assert module.module_name == name
    assert module.module_key == json.dumps(
        ["module", root, path],
        ensure_ascii=False,
        separators=(",", ":"),
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/tmp/app.py",
        "C:/repo/app.py",
        "../app.py",
        "pkg\\app.py",
        "pkg//app.py",
        "pkg/./app.py",
        "pkg/../app.py",
        "pkg/app.py/",
        "app.txt",
    ],
)
def test_invalid_module_paths_are_rejected(path):
    with pytest.raises(ValidationError):
        ModuleInfo(
            module_key=make_module_key(".", path),
            file_path=path,
            source_root=".",
            module_name=None,
        )


@pytest.mark.parametrize(
    "root,path,name",
    [
        ("src", "app.py", "app"),
        (".", "pkg/service.py", "service"),
        (".", "__init__.py", "__init__"),
        (".", "service.py", None),
        ("../src", "src/app.py", "app"),
    ],
)
def test_invalid_module_context_is_rejected(root, path, name):
    with pytest.raises(ValidationError):
        ModuleInfo(
            module_key=make_module_key(root, path),
            file_path=path,
            source_root=root,
            module_name=name,
        )


def test_noncanonical_module_key_is_rejected():
    with pytest.raises(ValidationError):
        ModuleInfo(
            module_key=json.dumps(["module", ".", "app.py"]),
            file_path="app.py",
            source_root=".",
            module_name="app",
        )


def test_target_kinds_and_symbol_keys(parsed_file):
    module_target = target_for(parsed_file)
    symbol_target = target_for(parsed_file, "helper")

    assert module_target.target_kind == "module"
    assert module_target.symbol_key is None
    assert symbol_target.target_kind == "symbol"
    assert symbol_target.symbol_key is not None

    bad_module = module_target.model_dump()
    bad_module["symbol_key"] = symbol_target.symbol_key

    bad_symbol = symbol_target.model_dump()
    bad_symbol["symbol_key"] = None

    for payload in (bad_module, bad_symbol):
        with pytest.raises(ValidationError):
            ResolverTarget.model_validate(payload)


def test_target_file_must_match_both_keys(parsed_file):
    payload = target_for(parsed_file, "helper").model_dump()
    payload["file_path"] = "other.py"

    with pytest.raises(ValidationError):
        ResolverTarget.model_validate(payload)

    payload["module_key"] = make_module_key(".", "other.py")

    with pytest.raises(ValidationError):
        ResolverTarget.model_validate(payload)


def test_reference_matches_real_source(parsed_file):
    site = site_for(parsed_file)

    assert site.start_line == 8
    assert site.end_line == 8
    assert site.expression == "helper()"
    assert site.validate_against_file(parsed_file) is site


@pytest.mark.parametrize(
    "field,value",
    [
        ("reference_key", "wrong-key"),
        ("scope_key", " "),
        ("expression", " "),
        ("start_byte", -1),
        ("end_byte", 0),
        ("end_line", 7),
        ("source_sha256", "not-a-hash"),
    ],
)
def test_invalid_reference_fields_are_rejected(
    parsed_file,
    field,
    value,
):
    payload = site_for(parsed_file).model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        ReferenceSite.model_validate(payload)


def test_reference_expression_must_match_actual_slice(parsed_file):
    payload = site_for(parsed_file).model_dump()

    # Same UTF-8 length and line span, but different source text.
    payload["expression"] = "otherx()"
    site = ReferenceSite.model_validate(payload)

    with pytest.raises(ValueError, match="source slice"):
        site.validate_against_file(parsed_file)


@pytest.mark.parametrize(
    "field",
    ["source_sha256", "parse_buffer_sha256"],
)
def test_reference_rejects_hash_mismatch(parsed_file, field):
    payload = site_for(parsed_file).model_dump()
    payload[field] = "0" * 64
    site = ReferenceSite.model_validate(payload)

    with pytest.raises(ValueError, match="hashes"):
        site.validate_against_file(parsed_file)


def test_reference_rejects_different_file(parsed_file):
    other_file = parse_python(
        SOURCE.encode("utf-8"),
        file_path="other.py",
    )

    with pytest.raises(ValueError, match="file"):
        site_for(parsed_file).validate_against_file(other_file)


def test_reference_must_lie_inside_symbol_owner(parsed_file):
    site = site_for(parsed_file, owner="helper")

    with pytest.raises(ValueError, match="inside"):
        site.validate_against_file(parsed_file)


def test_module_owner_is_allowed(parsed_file):
    site = site_for(parsed_file, owner=None)

    assert site.source_owner.target_kind == "module"
    assert site.validate_against_file(parsed_file) is site


def test_base_class_owner_is_the_subclass():
    parsed = parse_python(
        (
            b"class Base:\n"
            b"    pass\n"
            b"\n"
            b"class Child(Base):\n"
            b"    pass\n"
        ),
        file_path="classes.py",
    )

    site = site_for(
        parsed,
        expression="Base",
        reference_kind="base_class",
        owner="Child",
    )

    assert site.start_line == 4
    assert site.validate_against_file(parsed) is site


@pytest.mark.parametrize("owner", [None, "caller"])
def test_base_class_rejects_nonclass_owner(parsed_file, owner):
    with pytest.raises(ValidationError):
        site_for(
            parsed_file,
            reference_kind="base_class",
            owner=owner,
        )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [False, True])
@pytest.mark.parametrize("multiline", [False, True])
def test_unicode_bom_crlf_and_multiline_references(
    newline,
    bom,
    multiline,
):
    if multiline:
        expression = (
            f"helper({newline}"
            f'        "café",{newline}'
            "    )"
        )
    else:
        expression = 'helper("café")'

    text = (
        f"def helper(value):{newline}"
        f"    return value{newline}"
        f"{newline}"
        f"def caller():{newline}"
        f"    return {expression}{newline}"
    )

    source = text.encode("utf-8")

    if bom:
        source = b"\xef\xbb\xbf" + source

    parsed = parse_python(source, file_path="unicode.py")
    site = site_for(parsed, expression=expression)

    assert site.expression == expression
    assert site.end_byte - site.start_byte == len(
        expression.encode("utf-8")
    )
    assert site.start_line == 5
    assert site.end_line == (7 if multiline else 5)
    assert site.validate_against_file(parsed) is site

    if bom:
        assert parsed.source_sha256 != parsed.parse_buffer_sha256
    else:
        assert parsed.source_sha256 == parsed.parse_buffer_sha256


@pytest.mark.parametrize(
    "status,names,confidence",
    [
        ("EXACT", ("helper",), 1.0),
        ("INFERRED", ("helper",), 0.5),
        ("AMBIGUOUS", ("helper", "other"), None),
        ("UNRESOLVED", (), None),
    ],
)
def test_valid_resolution_statuses(
    parsed_file,
    status,
    names,
    confidence,
):
    result = result_for(
        parsed_file,
        status=status,
        names=names,
        confidence=confidence,
    )

    assert result.status == status
    assert result.confidence == confidence
    assert result.schema_version == 1
    assert result.resolution_policy == "python_resolver_v1"

    restored = ResolutionResult.model_validate_json(
        result.model_dump_json()
    )
    assert restored == result


@pytest.mark.parametrize(
    "status,names,confidence",
    [
        ("EXACT", (), 1.0),
        ("EXACT", ("helper", "other"), 1.0),
        ("INFERRED", (), 0.5),
        ("INFERRED", ("helper", "other"), 0.5),
        ("AMBIGUOUS", (), None),
        ("AMBIGUOUS", ("helper",), None),
        ("UNRESOLVED", ("helper",), None),
        ("EXACT", ("helper",), None),
        ("EXACT", ("helper",), 0.5),
        ("INFERRED", ("helper",), 1.0),
        ("AMBIGUOUS", ("helper", "other"), 0.5),
        ("UNRESOLVED", (), 0.0),
        ("EXACT", ("helper",), float("nan")),
        ("EXACT", ("helper",), float("inf")),
        ("EXACT", ("helper",), -0.1),
        ("EXACT", ("helper",), 1.1),
        ("exact", ("helper",), 1.0),
    ],
)
def test_invalid_resolution_combinations(
    parsed_file,
    status,
    names,
    confidence,
):
    with pytest.raises(ValidationError):
        result_for(
            parsed_file,
            status=status,
            names=names,
            confidence=confidence,
        )


def test_duplicate_candidates_are_rejected(parsed_file):
    with pytest.raises(ValidationError, match="unique"):
        result_for(
            parsed_file,
            status="AMBIGUOUS",
            names=("helper", "helper"),
            confidence=None,
        )


@pytest.mark.parametrize("field", ["rule_id", "reason"])
def test_resolution_requires_nonblank_evidence(parsed_file, field):
    payload = result_for(parsed_file).model_dump()
    payload[field] = " "

    with pytest.raises(ValidationError):
        ResolutionResult.model_validate(payload)


def test_extra_fields_are_rejected_on_every_model(parsed_file):
    module = ModuleInfo(
        module_key=make_module_key(".", parsed_file.file_path),
        file_path=parsed_file.file_path,
        source_root=".",
        module_name="pkg.service",
    )

    models = [
        module,
        target_for(parsed_file, "helper"),
        site_for(parsed_file),
        result_for(parsed_file),
    ]

    for model in models:
        payload = model.model_dump()
        payload["unexpected_field"] = True

        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(model).model_validate(payload)


def test_nullable_fields_are_required():
    required_fields = [
        (ModuleInfo, "module_name"),
        (ResolverTarget, "symbol_key"),
        (ResolutionResult, "confidence"),
    ]

    for model, field in required_fields:
        assert model.model_fields[field].is_required()


@pytest.mark.parametrize(
    "source,owner_qualname,lookup_scope_kind",
    [
        (
            "@decorate()\n"
            "def caller():\n"
            "    return 1\n",
            "caller",
            "module",
        ),
        (
            "@decorate()\n"
            "class Child:\n"
            "    pass\n",
            "Child",
            "module",
        ),
        (
            "class Service:\n"
            "    @decorate()\n"
            "    def run(self):\n"
            "        return 1\n",
            "Service.run",
            "class",
        ),
        (
            "@decorate()\n"
            "async def caller():\n"
            "    return 1\n",
            "caller",
            "module",
        ),
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [False, True])
def test_decorator_call_validates_with_real_scope_context(
    source,
    owner_qualname,
    lookup_scope_kind,
    newline,
    bom,
):
    text = source.replace("\n", newline)
    original_bytes = text.encode("utf-8")

    if bom:
        original_bytes = b"\xef\xbb\xbf" + original_bytes

    parsed = parse_python(
        original_bytes,
        file_path="decorators.py",
    )
    scopes = build_scope_index(build_repo_index([parsed]))
    owned = scopes.repo_index.files_by_path["decorators.py"]
    buffer = owned.source_text.encode("utf-8")

    expression = "decorate()"
    expression_bytes = expression.encode("utf-8")
    start_byte = buffer.index(expression_bytes)
    end_byte = start_byte + len(expression_bytes)

    context = scopes.context_for(
        owned.file_path,
        "Call",
        start_byte,
        end_byte,
    )
    owner = scopes.repo_index.definitions_by_local_key[
        context.source_owner.symbol_key
    ]

    assert owner.qualname == owner_qualname
    assert scopes.scopes_by_key[
        context.scope_key
    ].kind == lookup_scope_kind

    # Decorators precede the definition but belong to its content range.
    assert start_byte < owner.definition_start_byte
    assert owner.content_start_byte <= start_byte
    assert end_byte <= owner.content_end_byte

    site = ReferenceSite(
        reference_key=make_reference_key(
            owned.file_path,
            "call",
            start_byte,
            end_byte,
            context.scope_key,
        ),
        reference_kind="call",
        file_path=owned.file_path,
        source_sha256=owned.source_sha256,
        parse_buffer_sha256=owned.parse_buffer_sha256,
        scope_key=context.scope_key,
        source_owner=context.source_owner,
        expression=expression,
        start_line=buffer.count(b"\n", 0, start_byte) + 1,
        end_line=buffer.count(b"\n", 0, end_byte - 1) + 1,
        start_byte=start_byte,
        end_byte=end_byte,
    )

    assert site.validate_against_file(owned) is site


@pytest.mark.parametrize("position", ["before", "after"])
def test_call_outside_owner_content_still_fails(position):
    definition = (
        "@decorate()\n"
        "def caller():\n"
        "    return 1\n"
    )

    source = (
        "outside()\n\n" + definition
        if position == "before"
        else definition + "\noutside()\n"
    )

    parsed = parse_python(
        source.encode("utf-8"),
        file_path="outside_owner.py",
    )
    site = site_for(
        parsed,
        expression="outside()",
        owner="caller",
    )

    with pytest.raises(ValueError, match="inside its source owner"):
        site.validate_against_file(parsed)


def test_base_class_reference_does_not_accept_decorator_range():
    parsed = parse_python(
        (
            b"@decorate()\n"
            b"class Child:\n"
            b"    pass\n"
        ),
        file_path="classes.py",
    )

    # Deliberately mislabeled input: decorator text is not a class base.
    site = site_for(
        parsed,
        expression="decorate()",
        reference_kind="base_class",
        owner="Child",
    )

    with pytest.raises(ValueError, match="inside its source owner"):
        site.validate_against_file(parsed)


def test_multiline_decorator_nested_call_validates():
    parsed = parse_python(
        (
            b"@wrap(\n"
            b"    decorate()\n"
            b")\n"
            b"def caller():\n"
            b"    return 1\n"
        ),
        file_path="multiline_decorator.py",
    )
    site = site_for(
        parsed,
        expression="decorate()",
        owner="caller",
    )

    assert site.start_line == 2
    assert site.validate_against_file(parsed) is site