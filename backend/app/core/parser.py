import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedSymbol:
    name: str
    kind: str
    start_line: int
    end_line: int
    qualified_name: str


def parse_python(source: str, module_name: str = "") -> list[ParsedSymbol]:
    """Extract top-level functions and classes from Python source."""
    tree = ast.parse(source)
    return [
        ParsedSymbol(
            name=node.name,
            kind="class" if isinstance(node, ast.ClassDef) else "function",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            qualified_name=f"{module_name}.{node.name}".strip("."),
        )
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]