from dataclasses import dataclass

from backend.app.core.parser import parse_python


@dataclass(frozen=True)
class CodeChunk:
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    text: str


def chunk_python(source: str, module_name: str = "") -> list[CodeChunk]:
    lines = source.splitlines()
    return [
        CodeChunk(
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            text="\n".join(lines[symbol.start_line - 1 : symbol.end_line]),
        )
        for symbol in parse_python(source, module_name)
    ]