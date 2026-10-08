"""Versioned callable complexity calculation for cc_python_v1."""

import ast

from tree_sitter import Node


COMPLEXITY_POLICY = "cc_python_v1"


class ComplexityError(ValueError):
    """Raised when the metric cannot be calculated reliably."""


_SUPPORTED_NODE_NAMES = frozenset(
    """
    FunctionDef AsyncFunctionDef ClassDef Lambda
    Return Delete Assign AugAssign AnnAssign
    For AsyncFor While If With AsyncWith
    Match Raise Try TryStar Assert Import ImportFrom
    Global Nonlocal Expr Pass Break Continue
    BoolOp NamedExpr BinOp UnaryOp IfExp
    Dict Set ListComp SetComp DictComp GeneratorExp
    Await Yield YieldFrom Compare Call
    FormattedValue JoinedStr Constant
    Attribute Subscript Starred Name List Tuple Slice
    comprehension ExceptHandler keyword alias withitem
    match_case MatchValue MatchSingleton MatchSequence
    MatchMapping MatchClass MatchStar MatchAs MatchOr
    """.split()
)


def _is_catch_all(pattern: ast.pattern) -> bool:
    """Recognize an irrefutable capture/wildcard pattern."""
    if isinstance(pattern, ast.MatchAs):
        if pattern.pattern is None:
            return True

        return _is_catch_all(pattern.pattern)

    if isinstance(pattern, ast.MatchOr):
        return any(
            _is_catch_all(child)
            for child in pattern.patterns
        )

    return False


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.total = 1

    def visit(self, node: ast.AST):
        supported_operator = isinstance(
            node,
            (
                ast.operator,
                ast.unaryop,
                ast.boolop,
                ast.cmpop,
                ast.expr_context,
            ),
        )

        if (
            type(node).__name__ not in _SUPPORTED_NODE_NAMES
            and not supported_operator
        ):
            raise ComplexityError(
                "unsupported metric syntax node: "
                f"{type(node).__name__}"
            )

        return super().visit(node)

    def _visit_decision(self, node: ast.AST) -> None:
        self.total += 1
        self.generic_visit(node)

    visit_If = _visit_decision
    visit_IfExp = _visit_decision
    visit_For = _visit_decision
    visit_AsyncFor = _visit_decision
    visit_While = _visit_decision
    visit_ExceptHandler = _visit_decision
    visit_Assert = _visit_decision

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.total += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(
        self,
        node: ast.comprehension,
    ) -> None:
        self.total += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_match_case(
        self,
        node: ast.match_case,
    ) -> None:
        is_default = (
            node.guard is None
            and _is_catch_all(node.pattern)
        )

        if not is_default:
            self.total += 1

        if node.guard is not None:
            self.total += 1

        self.generic_visit(node)

    def _skip_nested_scope(self, node: ast.AST) -> None:
        return None

    visit_FunctionDef = _skip_nested_scope
    visit_AsyncFunctionDef = _skip_nested_scope
    visit_ClassDef = _skip_nested_scope
    visit_Lambda = _skip_nested_scope


def calculate_complexity(
    definition_node: Node,
    source: bytes,
) -> int:
    """Calculate complexity for one function/method definition.

    The source must be the same UTF-8 buffer used by Tree-sitter.
    Only the callable body is counted. Nested definition/lambda
    subtrees, headers, defaults, and decorators are excluded.
    """
    if definition_node.type != "function_definition":
        raise ComplexityError(
            "calculate_complexity requires a function_definition node"
        )

    start = definition_node.start_byte
    end = definition_node.end_byte

    if not 0 <= start < end <= len(source):
        raise ComplexityError(
            "definition range is outside the source buffer"
        )

    try:
        definition_text = source[start:end].decode("utf-8")
        module = ast.parse(definition_text)

    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ComplexityError(
            "definition cannot be analyzed by the current "
            "Python AST parser"
        ) from exc

    if (
        len(module.body) != 1
        or not isinstance(
            module.body[0],
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    ):
        raise ComplexityError(
            "definition slice must contain exactly one callable"
        )

    function = module.body[0]
    visitor = _ComplexityVisitor()

    try:
        for statement in function.body:
            visitor.visit(statement)

    except RecursionError as exc:
        raise ComplexityError(
            "definition exceeds supported AST traversal depth"
        ) from exc

    return visitor.total