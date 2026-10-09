import pytest

from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import (
    ResolverTarget,
    make_module_key,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.repo_index import (
    RepoIndexError,
    build_repo_index,
)


SOURCE = (
    "def helper():\n"
    "    return 1\n"
    "\n"
    "class Service:\n"
    "    def run(self):\n"
    "        return helper()\n"
)


def parsed(
    file_path: str = "pkg/service.py",
    source: bytes | None = None,
) -> ParsedFile:
    return parse_python(
        SOURCE.encode("utf-8") if source is None else source,
        file_path=file_path,
    )


def symbol_target(
    parsed_file: ParsedFile,
    qualname: str,
    *,
    source_root: str = ".",
) -> ResolverTarget:
    symbol = next(
        symbol
        for symbol in parsed_file.symbols
        if symbol.qualname == qualname
    )

    return ResolverTarget(
        target_kind="symbol",
        module_key=make_module_key(
            source_root,
            parsed_file.file_path,
        ),
        file_path=parsed_file.file_path,
        symbol_key=symbol.local_key,
    )


def test_empty_repository_index():
    index = build_repo_index([])

    assert index.source_roots == (".",)
    assert not index.files_by_path
    assert not index.modules_by_path
    assert not index.modules_by_key
    assert not index.modules_by_name
    assert not index.definitions_by_local_key
    assert index.module_candidates("missing") == ()


def test_index_contains_modules_and_real_definitions():
    original = parsed()
    index = build_repo_index([original])

    module = index.module_for_file(original.file_path)

    assert module.file_path == "pkg/service.py"
    assert module.source_root == "."
    assert module.module_name == "pkg.service"
    assert module.module_key == make_module_key(
        ".",
        "pkg/service.py",
    )
    assert index.modules_by_key[module.module_key] is module
    assert index.module_candidates("pkg.service") == (module,)

    expected_keys = {
        symbol.local_key
        for symbol in original.symbols
    }

    assert set(index.definitions_by_local_key) == expected_keys

    for symbol in original.symbols:
        indexed = index.definitions_by_local_key[symbol.local_key]
        assert indexed.model_dump() == symbol.model_dump()


@pytest.mark.parametrize(
    "root,path,name",
    [
        (".", "app.py", "app"),
        (".", "pkg/__init__.py", "pkg"),
        ("backend", "backend/pkg/service.py", "pkg.service"),
        (".", "__init__.py", None),
        ("src", "src/__init__.py", None),
        (".", "foo-bar.py", None),
        (".", "class.py", None),
        (".", "café/service.py", "café.service"),
    ],
)
def test_module_mapping(root, path, name):
    index = build_repo_index(
        [parsed(path)],
        source_roots=(root,),
    )

    module = index.module_for_file(path)

    assert module.source_root == root
    assert module.module_name == name

    if name is None:
        assert not index.modules_by_name
    else:
        assert index.module_candidates(name) == (module,)


def test_duplicate_module_names_preserve_all_candidates():
    files = [
        parsed("pkg.py"),
        parsed("pkg/__init__.py"),
    ]

    index = build_repo_index(files)
    candidates = index.module_candidates("pkg")

    assert len(candidates) == 2
    assert {module.file_path for module in candidates} == {
        "pkg.py",
        "pkg/__init__.py",
    }
    assert [module.module_key for module in candidates] == sorted(
        module.module_key for module in candidates
    )


def test_same_module_name_across_disjoint_roots():
    files = [
        parsed("src_a/service.py"),
        parsed("src_b/service.py"),
    ]

    index = build_repo_index(
        files,
        source_roots=("src_b", "src_a"),
    )

    assert index.source_roots == ("src_a", "src_b")
    assert {
        module.file_path
        for module in index.module_candidates("service")
    } == {
        "src_a/service.py",
        "src_b/service.py",
    }


@pytest.mark.parametrize(
    "roots,code",
    [
        ((), "INVALID_SOURCE_ROOTS"),
        (".", "INVALID_SOURCE_ROOTS"),
        (("",), "INVALID_SOURCE_ROOT"),
        ((" ",), "INVALID_SOURCE_ROOT"),
        (("../src",), "INVALID_SOURCE_ROOT"),
        (("/src",), "INVALID_SOURCE_ROOT"),
        (("C:/src",), "INVALID_SOURCE_ROOT"),
        (("src\\pkg",), "INVALID_SOURCE_ROOT"),
        (("src/",), "INVALID_SOURCE_ROOT"),
        (("src//pkg",), "INVALID_SOURCE_ROOT"),
        (("src/./pkg",), "INVALID_SOURCE_ROOT"),
        (("src/../pkg",), "INVALID_SOURCE_ROOT"),
        (("src", "src"), "DUPLICATE_SOURCE_ROOT"),
        ((".", "src"), "OVERLAPPING_SOURCE_ROOTS"),
        (("src", "src/pkg"), "OVERLAPPING_SOURCE_ROOTS"),
        (("src/pkg", "src"), "OVERLAPPING_SOURCE_ROOTS"),
    ],
)
def test_invalid_source_roots(roots, code):
    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([], source_roots=roots)

    assert exc.value.code == code


def test_similar_root_prefixes_do_not_overlap():
    index = build_repo_index(
        [
            parsed("src/app.py"),
            parsed("src_extra/app.py"),
        ],
        source_roots=("src", "src_extra"),
    )

    assert len(index.files_by_path) == 2
    assert len(index.module_candidates("app")) == 2


@pytest.mark.parametrize("same_content", [False, True])
def test_duplicate_file_paths_are_rejected(same_content):
    first = parsed("app.py")

    second = parsed(
        "app.py",
        SOURCE.encode("utf-8")
        if same_content
        else b"def changed():\n    return 2\n",
    )

    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([first, second])

    assert exc.value.code == "DUPLICATE_FILE_PATH"
    assert exc.value.file_path == "app.py"


def test_file_outside_roots_is_rejected():
    with pytest.raises(RepoIndexError) as exc:
        build_repo_index(
            [parsed("other/app.py")],
            source_roots=("src",),
        )

    assert exc.value.code == "FILE_OUTSIDE_SOURCE_ROOTS"
    assert exc.value.file_path == "other/app.py"


def test_non_parsed_file_input_is_rejected():
    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([{"file_path": "app.py"}])

    assert exc.value.code == "INVALID_PARSED_FILE"


@pytest.mark.parametrize(
    "newline",
    ["\n", "\r\n"],
)
@pytest.mark.parametrize("bom", [False, True])
def test_unicode_newlines_and_bom_are_preserved(newline, bom):
    text = (
        f"def café():{newline}"
        f'    return "你好"{newline}'
    )
    source = text.encode("utf-8")

    if bom:
        source = b"\xef\xbb\xbf" + source

    original = parsed("unicode.py", source)
    index = build_repo_index([original])
    owned = index.files_by_path["unicode.py"]

    assert owned.source_text == text
    assert owned.source_sha256 == original.source_sha256
    assert owned.parse_buffer_sha256 == original.parse_buffer_sha256

    if bom:
        assert owned.source_sha256 != owned.parse_buffer_sha256
    else:
        assert owned.source_sha256 == owned.parse_buffer_sha256


@pytest.mark.parametrize(
    "field,value,expected_codes",
    [
        (
            "source_text",
            SOURCE.replace("return 1", "return 9"),
            {
                "INVALID_PARSED_FILE",
                "PARSE_BUFFER_HASH_MISMATCH",
            },
        ),
        (
            "parse_buffer_sha256",
            "0" * 64,
            {
                "INVALID_PARSED_FILE",
                "PARSE_BUFFER_HASH_MISMATCH",
            },
        ),
        (
            "source_sha256",
            "0" * 64,
            {
                "INVALID_PARSED_FILE",
                "SOURCE_HASH_MISMATCH",
            },
        ),
    ],
)
def test_mutated_parser_buffers_or_hashes_are_rejected(
    field,
    value,
    expected_codes,
):
    original = parsed()
    setattr(original, field, value)

    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([original])

    # Either the existing ParsedFile validator or the index's explicit
    # hash check may detect the inconsistency first.
    assert exc.value.code in expected_codes


def test_mutated_definition_identity_is_rejected():
    original = parsed()
    original.symbols[0].local_key = "wrong-key"

    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([original])

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "INVALID_DEFINITION_IDENTITY",
    }


def test_mutated_definition_range_is_rejected():
    original = parsed()
    original.symbols[0].content_end_byte = (
        len(original.source_text.encode("utf-8")) + 100
    )

    with pytest.raises(RepoIndexError) as exc:
        build_repo_index([original])

    assert exc.value.code in {
        "INVALID_PARSED_FILE",
        "INVALID_DEFINITION_RANGE",
    }


def test_index_owns_independent_parser_records():
    original = parsed()
    original_dump = original.model_dump()

    index = build_repo_index([original])
    owned = index.files_by_path[original.file_path]

    assert owned is not original
    assert owned.symbols[0] is not original.symbols[0]
    assert owned.model_dump() == original_dump

    original.source_text = "changed after indexing"
    original.symbols[0].name = "changed_after_indexing"

    assert owned.model_dump() == original_dump


@pytest.mark.parametrize(
    "attribute",
    [
        "files_by_path",
        "modules_by_path",
        "modules_by_key",
        "modules_by_name",
        "definitions_by_local_key",
    ],
)
def test_lookup_mapping_entries_are_read_only(attribute):
    index = build_repo_index([parsed()])
    mapping = getattr(index, attribute)
    key = next(iter(mapping))

    with pytest.raises(TypeError):
        mapping[key] = mapping[key]

    with pytest.raises(TypeError):
        del mapping[key]


def test_input_order_does_not_change_lookup_order():
    files = [
        parsed("z.py"),
        parsed("a.py"),
        parsed("pkg/__init__.py"),
    ]

    forward = build_repo_index(files)
    reverse = build_repo_index(list(reversed(files)))

    for attribute in (
        "files_by_path",
        "modules_by_path",
        "modules_by_key",
        "modules_by_name",
        "definitions_by_local_key",
    ):
        assert list(getattr(forward, attribute)) == list(
            getattr(reverse, attribute)
        )

    assert forward.modules_by_name == reverse.modules_by_name


def test_module_target_membership():
    index = build_repo_index([parsed()])
    target = index.module_target("pkg/service.py")
    module = index.module_for_file("pkg/service.py")

    assert target.target_kind == "module"
    assert target.symbol_key is None
    assert index.validate_target(target) is module


@pytest.mark.parametrize(
    "qualname",
    ["helper", "Service", "Service.run"],
)
def test_definition_target_membership(qualname):
    original = parsed()
    index = build_repo_index([original])
    target = symbol_target(original, qualname)

    definition = index.validate_target(target)

    assert definition.qualname == qualname
    assert definition is index.definitions_by_local_key[
        target.symbol_key
    ]


def test_unknown_file_is_rejected():
    index = build_repo_index([])

    with pytest.raises(RepoIndexError) as exc:
        index.module_for_file("missing.py")

    assert exc.value.code == "UNKNOWN_FILE"


def test_unknown_target_module_is_rejected():
    index = build_repo_index([parsed()])
    target = ResolverTarget(
        target_kind="module",
        module_key=make_module_key(".", "missing.py"),
        file_path="missing.py",
        symbol_key=None,
    )

    with pytest.raises(RepoIndexError) as exc:
        index.validate_target(target)

    assert exc.value.code == "UNKNOWN_TARGET_MODULE"


def test_unknown_target_definition_is_rejected():
    original = parsed()
    index = build_repo_index([original])

    other_version = parsed(
        original.file_path,
        b"def missing():\n    return 1\n",
    )
    target = symbol_target(other_version, "missing")

    with pytest.raises(RepoIndexError) as exc:
        index.validate_target(target)

    assert exc.value.code == "UNKNOWN_TARGET_SYMBOL"


def test_mutated_target_is_revalidated():
    original = parsed()
    index = build_repo_index([original])
    target = symbol_target(original, "helper")
    target.symbol_key = None

    with pytest.raises(RepoIndexError) as exc:
        index.validate_target(target)

    assert exc.value.code == "INVALID_TARGET"