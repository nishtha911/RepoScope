import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from reposcope.contracts.parsing import ParsedFile
from reposcope.parsing.python_parser import parse_python


BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = (
    BACKEND_ROOT / "tests" / "fixtures" / "mini_repo"
)
GOLDEN_PATH = FIXTURE_ROOT / "golden_graph.json"

DEFINITION_KINDS = {"class", "function", "method"}


@pytest.fixture(scope="module")
def golden_graph():
    data = json.loads(
        GOLDEN_PATH.read_text(encoding="utf-8-sig")
    )

    assert data["schema_version"] == 1
    assert data["repository"] == "tests/fixtures/mini_repo"

    file_ids = [record["id"] for record in data["files"]]
    file_paths = [record["path"] for record in data["files"]]
    symbol_ids = [
        record["id"]
        for record in data["symbols"]
    ]
    metadata_ids = [
        record["symbol_id"]
        for record in data["symbol_metadata"]
    ]

    assert len(file_ids) == len(set(file_ids))
    assert len(file_paths) == len(set(file_paths))
    assert len(symbol_ids) == len(set(symbol_ids))
    assert len(metadata_ids) == len(set(metadata_ids))
    assert set(symbol_ids) == set(metadata_ids)

    assert all(
        symbol["file_id"] in set(file_ids)
        for symbol in data["symbols"]
    )

    return data


@pytest.fixture(scope="module")
def parsed_files(golden_graph):
    results = {}

    for record in golden_graph["files"]:
        relative_path = record["path"]
        source_path = (FIXTURE_ROOT / relative_path).resolve()

        assert source_path.is_relative_to(
            FIXTURE_ROOT.resolve()
        ), f"Fixture path escapes mini_repo: {relative_path}"

        assert source_path.is_file(), (
            f"Missing fixture file: {relative_path}"
        )

        results[relative_path] = parse_python(
            source_path.read_bytes(),
            file_path=relative_path,
        )

    return results


def test_fixture_manifest_matches_declared_scope(golden_graph):
    assert golden_graph["files_count"] == 15
    assert len(golden_graph["files"]) == 15

    assert golden_graph["symbols_count"] == 44
    assert len(golden_graph["symbols"]) == 44
    assert len(golden_graph["symbol_metadata"]) == 44

    declared_paths = {
        record["path"]
        for record in golden_graph["files"]
    }

    discovered_paths = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*.py")
        if path.is_file()
    }

    assert discovered_paths == declared_paths

    assert all(
        symbol["kind"] in DEFINITION_KINDS
        for symbol in golden_graph["symbols"]
    )


def test_definitions_match_golden_graph(
    golden_graph,
    parsed_files,
):
    paths_by_file_id = {
        record["id"]: record["path"]
        for record in golden_graph["files"]
    }

    qualnames_by_symbol_id = {
        record["symbol_id"]: record["qualified_name"]
        for record in golden_graph["symbol_metadata"]
    }

    # Fixture IDs are used only to join expected records.
    # They are not assigned to parser output.
    expected = Counter(
        (
            paths_by_file_id[symbol["file_id"]],
            qualnames_by_symbol_id[symbol["id"]],
            symbol["kind"],
            symbol["name"],
            symbol["start_line"],
            symbol["end_line"],
        )
        for symbol in golden_graph["symbols"]
    )

    actual = Counter(
        (
            parsed.file_path,
            symbol.qualname,
            symbol.kind,
            symbol.name,
            symbol.start_line,
            symbol.end_line,
        )
        for parsed in parsed_files.values()
        for symbol in parsed.symbols
    )

    missing = expected - actual
    unexpected = actual - expected

    assert not missing and not unexpected, (
        "\nRecord format: "
        "(path, qualname, kind, name, start_line, end_line)"
        "\nMissing/different expected records:\n"
        f"{list(missing.elements())}"
        "\nUnexpected/different extracted records:\n"
        f"{list(unexpected.elements())}"
    )


def test_extracted_definition_count_and_kinds(
    golden_graph,
    parsed_files,
):
    symbols = [
        symbol
        for parsed in parsed_files.values()
        for symbol in parsed.symbols
    ]

    assert len(symbols) == golden_graph["symbols_count"] == 44

    assert all(
        symbol.kind in DEFINITION_KINDS
        for symbol in symbols
    )


def test_real_sources_hashes_and_serialization(parsed_files):
    for relative_path, parsed in parsed_files.items():
        original = (
            FIXTURE_ROOT / relative_path
        ).read_bytes()

        buffer = parsed.source_text.encode("utf-8")

        assert parsed.file_path == relative_path
        assert parsed.source_sha256 == hashlib.sha256(
            original
        ).hexdigest()
        assert parsed.parse_buffer_sha256 == hashlib.sha256(
            buffer
        ).hexdigest()

        restored = ParsedFile.model_validate_json(
            parsed.model_dump_json()
        )

        assert restored == parsed

        for symbol in parsed.symbols:
            definition = buffer[
                symbol.definition_start_byte:
                symbol.definition_end_byte
            ].decode("utf-8")

            content = buffer[
                symbol.content_start_byte:
                symbol.content_end_byte
            ].decode("utf-8")

            assert definition
            assert content
            assert definition in content

            if symbol.kind == "class":
                assert definition.startswith("class ")
                assert symbol.signature is None
                assert symbol.parameters == []
                assert symbol.cyclomatic_complexity is None
                assert symbol.complexity_policy is None

            else:
                assert definition.startswith(
                    ("def ", "async def ")
                )
                assert symbol.signature is not None
                assert definition.startswith(symbol.signature)
                assert symbol.cyclomatic_complexity >= 1
                assert symbol.complexity_policy == "cc_python_v1"


def test_parent_references_and_nested_ranges(parsed_files):
    for parsed in parsed_files.values():
        by_key = {
            symbol.local_key: symbol
            for symbol in parsed.symbols
        }

        assert len(by_key) == len(parsed.symbols)

        for symbol in parsed.symbols:
            if symbol.parent_key is None:
                continue

            assert symbol.parent_key in by_key
            parent = by_key[symbol.parent_key]

            assert (
                parent.definition_start_byte
                <= symbol.definition_start_byte
                < symbol.definition_end_byte
                <= parent.definition_end_byte
            )