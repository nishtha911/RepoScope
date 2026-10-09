"""Partial binding collection for the Python reference resolver.

Collects:
- Class/function declarations.
- Import aliases and wildcard-import markers.
- Named-function and lambda parameters.
- Global/nonlocal directives.

Assignments, other writes, deletions, and control-flow paths are added
in the next stage. This index is not ready for reference resolution.
"""

import ast
import symtable
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from reposcope.contracts.resolution import ResolverTarget
from reposcope.parsing.repo_index import RepoIndexError
from reposcope.parsing.scope_index import (
    ScopeIndex,
    ScopeInfo,
    build_scope_index,
    make_scope_key,
)


DeclarationKind = Literal[
    "definition",
    "import",
    "wildcard_import",
    "parameter",
]

NameNamespace = Literal["local", "global", "nonlocal"]


@dataclass(frozen=True)
class ScopeDirectives:
    global_names: frozenset[str]
    nonlocal_names: frozenset[str]


@dataclass(frozen=True)
class ImportInfo:
    form: Literal["import", "from"]
    module: str | None
    level: int
    imported_name: str | None
    alias: str | None
    bound_module: str | None


@dataclass(frozen=True)
class DeclarationEvent:
    kind: DeclarationKind
    name: str | None
    scope_key: str
    namespace: NameNamespace
    file_path: str
    start_byte: int
    end_byte: int
    definition_target: ResolverTarget | None
    import_info: ImportInfo | None
    parameter_kind: str | None


@dataclass(frozen=True)
class DeclarationIndex:
    scope_index: ScopeIndex
    directives_by_scope: Mapping[str, ScopeDirectives]
    events_by_scope: Mapping[str, tuple[DeclarationEvent, ...]]
    events_by_scope_and_name: Mapping[
        tuple[str, str],
        tuple[DeclarationEvent, ...],
    ]

    @property
    def is_complete(self) -> Literal[False]:
        return False

    def events_for(
        self,
        scope_key: str,
        name: str,
    ) -> tuple[DeclarationEvent, ...]:
        return self.events_by_scope_and_name.get(
            (scope_key, name),
            (),
        )


class _DeclarationCollector(ast.NodeVisitor):
    def __init__(
        self,
        scope_index: ScopeIndex,
        file_path: str,
        directives: Mapping[str, ScopeDirectives],
    ) -> None:
        self.scope_index = scope_index
        self.file_path = file_path
        self.directives = directives
        self.events: list[DeclarationEvent] = []

        parsed_file = scope_index.repo_index.files_by_path[file_path]
        buffer = parsed_file.source_text.encode("utf-8")

        self.line_starts = [0]
        self.line_starts.extend(
            position + 1
            for position, value in enumerate(buffer)
            if value == 10
        )

        self.named_scopes_by_start: dict[int, ScopeInfo] = {}

        for local_key, scope_key in (
            scope_index.definition_scope_keys_by_local_key.items()
        ):
            scope = scope_index.scopes_by_key[scope_key]

            if scope.file_path != file_path:
                continue

            symbol = (
                scope_index.repo_index.definitions_by_local_key[local_key]
            )
            self.named_scopes_by_start[
                symbol.definition_start_byte
            ] = scope

    def span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.line_starts[node.lineno - 1] + node.col_offset,
            self.line_starts[node.end_lineno - 1] + node.end_col_offset,
        )

    def context(self, node: ast.AST):
        start, end = self.span(node)

        return self.scope_index.context_for(
            self.file_path,
            type(node).__name__,
            start,
            end,
        )

    def namespace_for(
        self,
        scope_key: str,
        name: str | None,
    ) -> NameNamespace:
        scope = self.scope_index.scopes_by_key[scope_key]
        directives = self.directives[scope_key]

        if scope.kind == "module":
            return "global"

        if name in directives.global_names:
            return "global"

        if name in directives.nonlocal_names:
            return "nonlocal"

        return "local"

    def emit(
        self,
        node: ast.AST,
        kind: DeclarationKind,
        name: str | None,
        *,
        scope_key: str | None = None,
        definition_target: ResolverTarget | None = None,
        import_info: ImportInfo | None = None,
        parameter_kind: str | None = None,
    ) -> None:
        if scope_key is None:
            scope_key = self.context(node).scope_key

        start, end = self.span(node)

        self.events.append(
            DeclarationEvent(
                kind=kind,
                name=name,
                scope_key=scope_key,
                namespace=self.namespace_for(scope_key, name),
                file_path=self.file_path,
                start_byte=start,
                end_byte=end,
                definition_target=definition_target,
                import_info=import_info,
                parameter_kind=parameter_kind,
            )
        )

    def parameter_nodes(
        self,
        args: ast.arguments,
    ) -> list[tuple[ast.arg, str]]:
        result = [
            (argument, "positional_only")
            for argument in args.posonlyargs
        ]
        result.extend(
            (argument, "positional_or_keyword")
            for argument in args.args
        )

        if args.vararg is not None:
            result.append((args.vararg, "var_positional"))

        result.extend(
            (argument, "keyword_only")
            for argument in args.kwonlyargs
        )

        if args.kwarg is not None:
            result.append((args.kwarg, "var_keyword"))

        return result

    def emit_parameters(
        self,
        args: ast.arguments,
        scope: ScopeInfo,
        *,
        check_parser_metadata: bool,
    ) -> None:
        parameters = self.parameter_nodes(args)

        if check_parser_metadata:
            symbol = (
                self.scope_index.repo_index.definitions_by_local_key[
                    scope.source_owner.symbol_key
                ]
            )

            expected = [
                (
                    unicodedata.normalize("NFKC", parameter.name),
                    parameter.kind,
                )
                for parameter in symbol.parameters
            ]
            actual = [
                (argument.arg, kind)
                for argument, kind in parameters
            ]

            if actual != expected:
                raise RepoIndexError(
                    "PARAMETER_METADATA_MISMATCH",
                    "AST parameters do not match parser metadata",
                    file_path=self.file_path,
                )

        for argument, kind in parameters:
            self.emit(
                argument,
                "parameter",
                argument.arg,
                scope_key=scope.scope_key,
                parameter_kind=kind,
            )

    def visit_named_definition(self, node: ast.AST) -> None:
        start, _ = self.span(node)
        scope = self.named_scopes_by_start.get(start)

        if scope is None:
            raise RepoIndexError(
                "MISSING_DEFINITION_SCOPE",
                "declaration has no indexed definition scope",
                file_path=self.file_path,
            )

        self.emit(
            node,
            "definition",
            node.name,
            definition_target=scope.source_owner,
        )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.emit_parameters(
                node.args,
                scope,
                check_parser_metadata=True,
            )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_named_definition(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self.visit_named_definition(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.visit_named_definition(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        start, end = self.span(node)
        key = make_scope_key(
            self.file_path,
            "lambda",
            start,
            end,
        )
        scope = self.scope_index.scopes_by_key[key]

        self.emit_parameters(
            node.args,
            scope,
            check_parser_metadata=False,
        )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".")[0]
            bound_module = (
                alias.name
                if alias.asname is not None
                else alias.name.split(".")[0]
            )

            self.emit(
                alias,
                "import",
                bound_name,
                import_info=ImportInfo(
                    form="import",
                    module=alias.name,
                    level=0,
                    imported_name=None,
                    alias=alias.asname,
                    bound_module=bound_module,
                ),
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            wildcard = alias.name == "*"
            name = None if wildcard else (alias.asname or alias.name)

            self.emit(
                alias,
                "wildcard_import" if wildcard else "import",
                name,
                import_info=ImportInfo(
                    form="from",
                    module=node.module,
                    level=node.level,
                    imported_name=alias.name,
                    alias=alias.asname,
                    bound_module=None,
                ),
            )


def build_declaration_index(
    scope_index: ScopeIndex,
) -> DeclarationIndex:
    """Collect a partial binding index from freshly validated scopes."""
    owned_scopes = build_scope_index(scope_index.repo_index)

    trees: dict[str, ast.Module] = {}

    for file_path, parsed_file in (
        owned_scopes.repo_index.files_by_path.items()
    ):
        try:
            # Compiler scope validation only; repository code is not run.
            symtable.symtable(
                parsed_file.source_text,
                file_path,
                "exec",
            )
            trees[file_path] = ast.parse(
                parsed_file.source_text,
                filename=file_path,
            )
        except SyntaxError as exc:
            raise RepoIndexError(
                "INVALID_SCOPE_DECLARATION",
                exc.msg,
                file_path=file_path,
            ) from exc

    global_names: dict[str, set[str]] = {
        key: set()
        for key in owned_scopes.scopes_by_key
    }
    nonlocal_names: dict[str, set[str]] = {
        key: set()
        for key in owned_scopes.scopes_by_key
    }

    for file_path, tree in trees.items():
        collector = _DeclarationCollector(
            owned_scopes,
            file_path,
            {},
        )

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Global, ast.Nonlocal)):
                continue

            scope_key = collector.context(node).scope_key

            destination = (
                global_names
                if isinstance(node, ast.Global)
                else nonlocal_names
            )
            destination[scope_key].update(node.names)

    directives = {
        key: ScopeDirectives(
            global_names=frozenset(global_names[key]),
            nonlocal_names=frozenset(nonlocal_names[key]),
        )
        for key in sorted(owned_scopes.scopes_by_key)
    }

    events_by_scope: dict[str, list[DeclarationEvent]] = {
        key: []
        for key in owned_scopes.scopes_by_key
    }
    events_by_name: dict[
        tuple[str, str],
        list[DeclarationEvent],
    ] = {}

    for file_path, tree in trees.items():
        collector = _DeclarationCollector(
            owned_scopes,
            file_path,
            directives,
        )
        collector.visit(tree)

        for event in collector.events:
            events_by_scope[event.scope_key].append(event)

            if event.name is not None:
                events_by_name.setdefault(
                    (event.scope_key, event.name),
                    [],
                ).append(event)

    def ordered(
        events: list[DeclarationEvent],
    ) -> tuple[DeclarationEvent, ...]:
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.start_byte,
                    event.end_byte,
                    event.kind,
                    event.name or "",
                ),
            )
        )

    return DeclarationIndex(
        scope_index=owned_scopes,
        directives_by_scope=MappingProxyType(directives),
        events_by_scope=MappingProxyType({
            key: ordered(events)
            for key, events in sorted(events_by_scope.items())
        }),
        events_by_scope_and_name=MappingProxyType({
            key: ordered(events)
            for key, events in sorted(events_by_name.items())
        }),
    )