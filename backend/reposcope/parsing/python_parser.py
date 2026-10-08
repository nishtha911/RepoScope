"""Python definition extraction for the Option A contract."""

import ast
import codecs
import hashlib
from io import BytesIO
from tokenize import detect_encoding
from typing import Iterator

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from reposcope.contracts.parsing import (
    ParsedFile,
    ParsedSymbol,
    make_local_key,
)
from reposcope.parsing.python_complexity import (
    COMPLEXITY_POLICY,
    calculate_complexity,
)
from reposcope.parsing.python_parameters import (
    extract_parameters,
)


class PythonParserError(ValueError):
    """Raised when source cannot be parsed under the supported policy."""

    def __init__(self, message: str, *, file_path: str) -> None:
        self.file_path = file_path
        super().__init__(f"{file_path}: {message}")


def _decode_source(source: bytes, *, file_path: str) -> str:
    try:
        encoding, _ = detect_encoding(
            BytesIO(source).readline
        )
        canonical_encoding = codecs.lookup(encoding).name

    except (SyntaxError, LookupError, UnicodeError) as exc:
        raise PythonParserError(
            "invalid source encoding declaration or byte sequence",
            file_path=file_path,
        ) from exc

    if canonical_encoding not in {"utf-8", "utf-8-sig"}:
        raise PythonParserError(
            f"unsupported source encoding: {encoding}; expected UTF-8",
            file_path=file_path,
        )

    try:
        return source.decode("utf-8-sig")

    except UnicodeDecodeError as exc:
        raise PythonParserError(
            "source contains invalid UTF-8 bytes",
            file_path=file_path,
        ) from exc


def _walk_nodes(root: Node) -> Iterator[Node]:
    stack = [root]

    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _required_field(node: Node, field_name: str) -> Node:
    child = node.child_by_field_name(field_name)

    if child is None:
        raise ValueError(
            f"{node.type} is missing its {field_name!r} field"
        )

    return child


def _line_range(
    source: bytes,
    start: int,
    end: int,
) -> tuple[int, int]:
    return (
        source.count(b"\n", 0, start) + 1,
        source.count(b"\n", 0, end - 1) + 1,
    )


def _content_range(
    node: Node,
    source: bytes,
) -> tuple[int, int]:
    content_node = node

    if (
        node.parent is not None
        and node.parent.type == "decorated_definition"
    ):
        content_node = node.parent

    start = content_node.start_byte
    end = content_node.end_byte

    line_start = source.rfind(b"\n", 0, start) + 1
    prefix = source[line_start:start]

    if all(byte in b" \t\f" for byte in prefix):
        start = line_start

    return start, end


def _signature(node: Node, source: bytes) -> str:
    for child in node.children:
        if child.type == ":":
            return source[
                node.start_byte:child.end_byte
            ].decode("utf-8")

    raise ValueError(
        "function definition has no header-ending colon"
    )


def _docstring(node: Node, source: bytes) -> str | None:
    body = _required_field(node, "body")

    statements = [
        child
        for child in body.named_children
        if child.type != "comment"
    ]

    if not statements:
        return None

    first = statements[0]

    if first.type != "expression_statement":
        return None

    expressions = [
        child
        for child in first.named_children
        if child.type != "comment"
    ]

    if len(expressions) != 1:
        return None

    expression = expressions[0]

    if expression.type not in {
        "string",
        "concatenated_string",
        "parenthesized_expression",
    }:
        return None

    parsed_expression = ast.parse(
        _text(expression, source),
        mode="eval",
    ).body

    if (
        isinstance(parsed_expression, ast.Constant)
        and isinstance(parsed_expression.value, str)
    ):
        return parsed_expression.value

    return None


def _parent_symbol(
    node: Node,
    symbols_by_node: dict[int, ParsedSymbol],
) -> ParsedSymbol | None:
    parent = node.parent

    while parent is not None:
        if parent.type in {
            "class_definition",
            "function_definition",
        }:
            return symbols_by_node[parent.id]

        parent = parent.parent

    return None


def _extract_symbols(
    root: Node,
    source: bytes,
    *,
    file_path: str,
) -> list[ParsedSymbol]:
    symbols: list[ParsedSymbol] = []
    symbols_by_node: dict[int, ParsedSymbol] = {}

    for node in _walk_nodes(root):
        if node.type not in {
            "class_definition",
            "function_definition",
        }:
            continue

        name_node = _required_field(node, "name")
        name = _text(name_node, source)
        parent = _parent_symbol(node, symbols_by_node)

        if node.type == "class_definition":
            kind = "class"

        elif parent is not None and parent.kind == "class":
            kind = "method"

        else:
            kind = "function"

        qualname = (
            f"{parent.qualname}.{name}"
            if parent is not None
            else name
        )

        definition_start = node.start_byte
        definition_end = node.end_byte

        start_line, end_line = _line_range(
            source,
            definition_start,
            definition_end,
        )

        content_start, content_end = _content_range(
            node,
            source,
        )

        content_start_line, content_end_line = _line_range(
            source,
            content_start,
            content_end,
        )

        if kind == "class":
            signature = None
            parameters = []
            is_async = False
            complexity = None
            complexity_policy = None

        else:
            parameters_node = _required_field(
                node,
                "parameters",
            )

            parameters = extract_parameters(
                parameters_node,
                source,
            )

            signature = _signature(node, source)

            is_async = any(
                child.type == "async"
                for child in node.children
            )

            complexity = calculate_complexity(
                node,
                source,
            )
            complexity_policy = COMPLEXITY_POLICY

        symbol = ParsedSymbol(
            local_key=make_local_key(
                file_path,
                kind,
                qualname,
                definition_start,
            ),
            parent_key=(
                parent.local_key
                if parent is not None
                else None
            ),
            name=name,
            qualname=qualname,
            kind=kind,
            start_line=start_line,
            end_line=end_line,
            definition_start_byte=definition_start,
            definition_end_byte=definition_end,
            content_start_line=content_start_line,
            content_end_line=content_end_line,
            content_start_byte=content_start,
            content_end_byte=content_end,
            signature=signature,
            docstring=_docstring(node, source),
            parameters=parameters,
            is_async=is_async,
            cyclomatic_complexity=complexity,
            complexity_policy=complexity_policy,
        )

        symbols.append(symbol)
        symbols_by_node[node.id] = symbol

    return sorted(
        symbols,
        key=lambda symbol: (
            symbol.definition_start_byte,
            symbol.definition_end_byte,
            symbol.local_key,
        ),
    )


def parse_python(source: bytes, *, file_path: str) -> ParsedFile:
    """Extract definition records from the supplied source bytes."""
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")

    source_text = _decode_source(
        source,
        file_path=file_path,
    )
    parse_buffer = source_text.encode("utf-8")

    language = Language(tree_sitter_python.language())
    parser = Parser(language)
    tree = parser.parse(parse_buffer)
    root = tree.root_node

    if root.has_error:
        raise PythonParserError(
            "source contains syntax errors or missing syntax nodes",
            file_path=file_path,
        )

    for node in _walk_nodes(root):
        if node.is_missing:
            raise PythonParserError(
                "source contains missing syntax nodes",
                file_path=file_path,
            )

    try:
        symbols = _extract_symbols(
            root,
            parse_buffer,
            file_path=file_path,
        )

    except (ValueError, SyntaxError) as exc:
        raise PythonParserError(
            f"definition metadata extraction failed: {exc}",
            file_path=file_path,
        ) from exc

    return ParsedFile(
        schema_version=1,
        file_path=file_path,
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_text=source_text,
        parse_buffer_sha256=hashlib.sha256(
            parse_buffer
        ).hexdigest(),
        symbols=symbols,
    )