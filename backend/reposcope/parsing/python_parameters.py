"""Extract callable parameter metadata from Python Tree-sitter nodes."""

from tree_sitter import Node

from reposcope.contracts.parsing import ParsedParameter


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _named_children(node: Node) -> list[Node]:
    return [
        child
        for child in node.named_children
        if child.type != "comment"
    ]


def _parameter_parts(
    node: Node,
    source: bytes,
) -> tuple[Node, str | None, str | None]:
    """Return the name/pattern node, annotation, and default text."""
    if node.type in {
        "identifier",
        "list_splat_pattern",
        "dictionary_splat_pattern",
    }:
        return node, None, None

    children = _named_children(node)

    if node.type == "typed_parameter":
        if len(children) != 2 or children[1].type != "type":
            raise ValueError(
                "unexpected typed_parameter structure"
            )

        return (
            children[0],
            _text(children[1], source),
            None,
        )

    if node.type == "default_parameter":
        if len(children) != 2:
            raise ValueError(
                "unexpected default_parameter structure"
            )

        return (
            children[0],
            None,
            _text(children[1], source),
        )

    if node.type == "typed_default_parameter":
        if len(children) != 3 or children[1].type != "type":
            raise ValueError(
                "unexpected typed_default_parameter structure"
            )

        return (
            children[0],
            _text(children[1], source),
            _text(children[2], source),
        )

    raise ValueError(
        f"unsupported parameter node: {node.type}"
    )


def _parameter_name(pattern: Node, source: bytes) -> str:
    if pattern.type == "identifier":
        return _text(pattern, source)

    if pattern.type in {
        "list_splat_pattern",
        "dictionary_splat_pattern",
    }:
        children = _named_children(pattern)

        if len(children) != 1 or children[0].type != "identifier":
            raise ValueError(
                "variadic parameter must contain one identifier"
            )

        return _text(children[0], source)

    raise ValueError(
        f"unsupported parameter name pattern: {pattern.type}"
    )


def extract_parameters(
    parameters_node: Node,
    source: bytes,
) -> list[ParsedParameter]:
    """Extract ordered metadata from a callable's parameters node.

    `source` must be the same UTF-8 buffer used to create the node.
    Tree-sitter nodes remain internal to the parser implementation.
    """
    if parameters_node.type != "parameters":
        raise ValueError(
            "extract_parameters requires a parameters node"
        )

    records: list[dict] = []
    keyword_only = False

    for node in _named_children(parameters_node):
        node_text = _text(node, source)

        if node.type == "positional_separator":
            for record in records:
                if record["kind"] == "positional_or_keyword":
                    record["kind"] = "positional_only"
            continue

        if node_text == "*":
            keyword_only = True
            continue

        pattern, annotation, default_text = _parameter_parts(
            node,
            source,
        )

        if pattern.type == "list_splat_pattern":
            kind = "var_positional"
            keyword_only = True

        elif pattern.type == "dictionary_splat_pattern":
            kind = "var_keyword"
            keyword_only = True

        elif keyword_only:
            kind = "keyword_only"

        else:
            kind = "positional_or_keyword"

        records.append(
            {
                "name": _parameter_name(pattern, source),
                "kind": kind,
                "annotation": annotation,
                "default_text": default_text,
            }
        )

    return [
        ParsedParameter.model_validate(record)
        for record in records
    ]