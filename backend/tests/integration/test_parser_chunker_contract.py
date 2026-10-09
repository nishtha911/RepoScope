import ast
import json
from hashlib import sha256
from pathlib import Path

import pytest

from reposcope.contracts.chunking import SOURCE_SEPARATOR
from reposcope.parsing.python_parser import parse_python
from reposcope.retrieval.chunker import build_symbol_chunks


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "mini_repo"
)


def _collect_ast_definitions(tree):
    """Independent source inventory; do not execute fixture code."""
    definitions = {}

    def visit(node, scopes):
        next_scopes = scopes

        if isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            if isinstance(node, ast.ClassDef):
                kind = "class"
            elif scopes and scopes[-1][1] == "class":
                kind = "method"
            else:
                kind = "function"

            qualname = ".".join(
                [name for name, _ in scopes] + [node.name]
            )

            definitions[(qualname, node.lineno)] = {
                "node": node,
                "kind": kind,
            }

            next_scopes = scopes + [(node.name, kind)]

        for child in ast.iter_child_nodes(node):
            visit(child, next_scopes)

    visit(tree, [])
    return definitions


@pytest.fixture(scope="module")
def mini_repo_results():
    paths = sorted(FIXTURE_ROOT.rglob("*.py"))

    assert len(paths) == 15

    results = []

    for path in paths:
        original_bytes = path.read_bytes()
        relative_path = path.relative_to(FIXTURE_ROOT).as_posix()

        parsed = parse_python(
            original_bytes,
            file_path=relative_path,
        )

        chunks = build_symbol_chunks(parsed)

        tree = ast.parse(
            parsed.source_text,
            filename=relative_path,
        )

        results.append(
            (
                original_bytes,
                parsed,
                chunks,
                _collect_ast_definitions(tree),
            )
        )

    return results


def test_one_chunk_per_real_fixture_definition(mini_repo_results):
    total_definitions = 0
    total_chunks = 0

    for _, parsed, chunks, definitions in mini_repo_results:
        actual_definitions = {
            (symbol.qualname, symbol.start_line): (
                symbol.kind,
                symbol.end_line,
            )
            for symbol in parsed.symbols
        }

        expected_definitions = {
            key: (
                item["kind"],
                item["node"].end_lineno,
            )
            for key, item in definitions.items()
        }

        assert actual_definitions == expected_definitions
        assert len(chunks) == len(parsed.symbols)

        assert [chunk.symbol_key for chunk in chunks] == [
            symbol.local_key for symbol in parsed.symbols
        ]

        assert len({chunk.symbol_key for chunk in chunks}) == len(chunks)

        total_definitions += len(definitions)
        total_chunks += len(chunks)

    # Expected definition scope documented by the Track 1 handoff.
    assert total_definitions == 44
    assert total_chunks == 44


def test_complete_source_and_headers(mini_repo_results):
    for original_bytes, parsed, chunks, definitions in mini_repo_results:
        buffer = parsed.source_text.encode("utf-8")

        assert parsed.source_sha256 == sha256(original_bytes).hexdigest()
        assert parsed.parse_buffer_sha256 == sha256(buffer).hexdigest()

        line_starts = [0]
        line_starts.extend(
            index + 1
            for index, byte in enumerate(buffer)
            if byte == 10
        )

        for symbol, chunk in zip(parsed.symbols, chunks):
            definition = definitions[
                (symbol.qualname, symbol.start_line)
            ]["node"]

            # Python AST provides an independent definition endpoint.
            expected_end = (
                line_starts[definition.end_lineno - 1]
                + definition.end_col_offset
            )

            assert symbol.definition_end_byte == expected_end
            assert symbol.content_end_byte == expected_end

            # Fixture decorators begin on their decorator-expression line.
            expected_first_line = min(
                [definition.lineno]
                + [
                    decorator.lineno
                    for decorator in definition.decorator_list
                ]
            )

            assert symbol.content_start_line == expected_first_line
            assert symbol.content_start_byte == (
                line_starts[expected_first_line - 1]
            )

            expected_body = buffer[
                symbol.content_start_byte:expected_end
            ].decode("utf-8")

            assert chunk.body_text == expected_body

            assert json.loads(chunk.header_text) == {
                "file_path": parsed.file_path,
                "qualname": symbol.qualname,
                "kind": symbol.kind,
                "signature": symbol.signature,
                "docstring": symbol.docstring,
            }

            assert chunk.start_line == symbol.content_start_line
            assert chunk.end_line == symbol.content_end_line

            assert chunk.source_sha256 == parsed.source_sha256
            assert chunk.parse_buffer_sha256 == parsed.parse_buffer_sha256

            assert chunk.text == (
                chunk.header_text
                + SOURCE_SEPARATOR
                + expected_body
            )


def test_enclosing_and_nested_chunks_overlap(mini_repo_results):
    for _, parsed, chunks, _ in mini_repo_results:
        by_key = {
            chunk.symbol_key: chunk
            for chunk in chunks
        }

        for symbol in parsed.symbols:
            if symbol.parent_key is None:
                continue

            child_chunk = by_key[symbol.local_key]
            parent_chunk = by_key[symbol.parent_key]

            assert child_chunk.body_text in parent_chunk.body_text


def test_deterministic_output_without_reopening_files(
    mini_repo_results,
    monkeypatch,
):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Chunker must not reopen source files.")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read)
    monkeypatch.setattr(Path, "read_text", forbidden_read)

    for _, parsed, original_chunks, _ in mini_repo_results:
        rebuilt = build_symbol_chunks(parsed)

        assert [
            chunk.model_dump()
            for chunk in rebuilt
        ] == [
            chunk.model_dump()
            for chunk in original_chunks
        ]