"""Lexical scopes and source-node contexts for the Python resolver.

This stage records:
- Module, class, function/method, lambda, and comprehension scopes.
- Lexical parents separately from name-lookup parents.
- The lookup scope and relationship owner of located source nodes.

It does not yet collect bindings or resolve references.
"""

import ast
import json
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterator, Literal, Mapping

from reposcope.contracts.parsing import ParsedSymbol
from reposcope.contracts.resolution import ResolverTarget
from reposcope.parsing.repo_index import (
    RepoIndex,
    RepoIndexError,
    build_repo_index,
)


ScopeKind = Literal[
    "module",
    "class",
    "function",
    "method",
    "lambda",
    "comprehension",
]

NodeLocation = tuple[str, str, int, int]


def make_scope_key(
    file_path: str,
    scope_kind: ScopeKind,
    start_byte: int,
    end_byte: int,
) -> str:
    return json.dumps(
        [
            "scope",
            file_path,
            scope_kind,
            start_byte,
            end_byte,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class ScopeInfo:
    scope_key: str
    file_path: str
    kind: ScopeKind
    parent_scope_key: str | None
    lookup_parent_scope_key: str | None
    source_owner: ResolverTarget
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class ExpressionContext:
    scope_key: str
    source_owner: ResolverTarget
    resolution_blocker: str | None


@dataclass(frozen=True)
class ScopeIndex:
    repo_index: RepoIndex
    scopes_by_key: Mapping[str, ScopeInfo]
    module_scope_keys_by_path: Mapping[str, str]
    definition_scope_keys_by_local_key: Mapping[str, str]
    contexts_by_location: Mapping[NodeLocation, ExpressionContext]

    def context_for(
        self,
        file_path: str,
        node_kind: str,
        start_byte: int,
        end_byte: int,
    ) -> ExpressionContext:
        key = (file_path, node_kind, start_byte, end_byte)
        context = self.contexts_by_location.get(key)

        if context is None:
            raise RepoIndexError(
                "UNKNOWN_NODE_CONTEXT",
                f"no indexed context for {node_kind} "
                f"at [{start_byte}, {end_byte})",
                file_path=file_path,
            )

        return context


class _ScopeVisitor(ast.NodeVisitor):
    def __init__(self, repo_index: RepoIndex, file_path: str) -> None:
        self.repo_index = repo_index
        self.file_path = file_path
        self.parsed_file = repo_index.files_by_path[file_path]
        self.buffer = self.parsed_file.source_text.encode("utf-8")

        if b"\r" in self.buffer.replace(b"\r\n", b""):
            raise RepoIndexError(
                "UNSUPPORTED_NEWLINE",
                "scope analysis supports LF and CRLF, not lone CR",
                file_path=file_path,
            )

        self.line_starts = [0]
        self.line_starts.extend(
            position + 1
            for position, value in enumerate(self.buffer)
            if value == 10
        )

        self.definitions_by_start: dict[int, ParsedSymbol] = {}

        for symbol in self.parsed_file.symbols:
            start = symbol.definition_start_byte

            if start in self.definitions_by_start:
                raise RepoIndexError(
                    "DUPLICATE_DEFINITION_START",
                    "multiple definitions share a source start",
                    file_path=file_path,
                )

            self.definitions_by_start[start] = symbol

        self.scopes: dict[str, ScopeInfo] = {}
        self.contexts: dict[NodeLocation, ExpressionContext] = {}
        self.definition_scopes: dict[str, str] = {}
        self.matched_definitions: set[str] = set()
        self.blocker: str | None = None

        owner = repo_index.module_target(file_path)
        module_key = make_scope_key(
            file_path,
            "module",
            0,
            len(self.buffer),
        )

        self.scopes[module_key] = ScopeInfo(
            scope_key=module_key,
            file_path=file_path,
            kind="module",
            parent_scope_key=None,
            lookup_parent_scope_key=None,
            source_owner=owner,
            start_byte=0,
            end_byte=len(self.buffer),
        )

        self.module_scope_key = module_key
        self.current_scope_key = module_key
        self.owner = owner

    def span(self, node: ast.AST) -> tuple[int, int]:
        positions = (
            getattr(node, "lineno", None),
            getattr(node, "col_offset", None),
            getattr(node, "end_lineno", None),
            getattr(node, "end_col_offset", None),
        )

        if any(value is None for value in positions):
            raise RepoIndexError(
                "MISSING_AST_LOCATION",
                f"{type(node).__name__} lacks a complete source span",
                file_path=self.file_path,
            )

        line, column, end_line, end_column = positions

        try:
            start = self.line_starts[line - 1] + column
            end = self.line_starts[end_line - 1] + end_column
        except IndexError as exc:
            raise RepoIndexError(
                "INVALID_AST_LOCATION",
                "AST line position exceeds the source buffer",
                file_path=self.file_path,
            ) from exc

        if not 0 <= start <= end <= len(self.buffer):
            raise RepoIndexError(
                "INVALID_AST_LOCATION",
                "AST byte position exceeds the source buffer",
                file_path=self.file_path,
            )

        return start, end

    def visit(self, node: ast.AST):
        if hasattr(node, "lineno"):
            start, end = self.span(node)
            key = (
                self.file_path,
                type(node).__name__,
                start,
                end,
            )
            context = ExpressionContext(
                scope_key=self.current_scope_key,
                source_owner=self.owner,
                resolution_blocker=self.blocker,
            )

            previous = self.contexts.get(key)

            if previous is not None and previous != context:
                raise RepoIndexError(
                    "CONFLICTING_NODE_CONTEXT",
                    "the same source-node identity has conflicting contexts",
                    file_path=self.file_path,
                )

            self.contexts[key] = context

        return super().visit(node)

    @contextmanager
    def using_owner(
        self,
        owner: ResolverTarget,
    ) -> Iterator[None]:
        previous = self.owner
        self.owner = owner

        try:
            yield
        finally:
            self.owner = previous

    @contextmanager
    def using_scope(
        self,
        scope: ScopeInfo,
    ) -> Iterator[None]:
        previous_scope = self.current_scope_key
        previous_owner = self.owner

        self.current_scope_key = scope.scope_key
        self.owner = scope.source_owner

        try:
            yield
        finally:
            self.current_scope_key = previous_scope
            self.owner = previous_owner

    def new_scope(
        self,
        node: ast.AST,
        kind: ScopeKind,
        owner: ResolverTarget,
    ) -> ScopeInfo:
        start, end = self.span(node)
        key = make_scope_key(
            self.file_path,
            kind,
            start,
            end,
        )

        if key in self.scopes:
            raise RepoIndexError(
                "DUPLICATE_SCOPE_KEY",
                "scope identity already exists",
                file_path=self.file_path,
            )

        lookup_parent = self.current_scope_key

        while (
            lookup_parent is not None
            and self.scopes[lookup_parent].kind == "class"
        ):
            lookup_parent = self.scopes[
                lookup_parent
            ].lookup_parent_scope_key

        scope = ScopeInfo(
            scope_key=key,
            file_path=self.file_path,
            kind=kind,
            parent_scope_key=self.current_scope_key,
            lookup_parent_scope_key=lookup_parent,
            source_owner=owner,
            start_byte=start,
            end_byte=end,
        )

        self.scopes[key] = scope
        return scope

    def definition_for(self, node: ast.AST) -> ParsedSymbol:
        start, _ = self.span(node)
        symbol = self.definitions_by_start.get(start)

        expected_kinds = (
            {"class"}
            if isinstance(node, ast.ClassDef)
            else {"function", "method"}
        )

        if (
            symbol is None
            or symbol.kind not in expected_kinds
            or unicodedata.normalize("NFKC", symbol.name) != node.name
        ):
            raise RepoIndexError(
                "DEFINITION_AST_MISMATCH",
                "AST declaration does not match parser metadata",
                file_path=self.file_path,
            )

        self.matched_definitions.add(symbol.local_key)
        return symbol

    def target_for(self, symbol: ParsedSymbol) -> ResolverTarget:
        module = self.repo_index.module_for_file(self.file_path)

        return ResolverTarget(
            target_kind="symbol",
            module_key=module.module_key,
            file_path=self.file_path,
            symbol_key=symbol.local_key,
        )

    def reject_type_parameters(self, node: ast.AST) -> None:
        if getattr(node, "type_params", ()):
            raise RepoIndexError(
                "UNSUPPORTED_ANNOTATION_SCOPE",
                "generic type-parameter scopes require explicit support",
                file_path=self.file_path,
            )

    def visit_annotation(self, node: ast.AST | None) -> None:
        if node is None:
            return

        previous = self.blocker
        self.blocker = "ANNOTATION_SEMANTICS_NOT_MODELED"

        try:
            self.visit(node)
        finally:
            self.blocker = previous

    def visit_argument_expressions(self, args: ast.arguments) -> None:
        for default in args.defaults:
            self.visit(default)

        for default in args.kw_defaults:
            if default is not None:
                self.visit(default)

        arguments = [
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
        ]

        if args.vararg is not None:
            arguments.append(args.vararg)

        if args.kwarg is not None:
            arguments.append(args.kwarg)

        for argument in arguments:
            self.visit_annotation(argument.annotation)

    def visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self.reject_type_parameters(node)

        symbol = self.definition_for(node)
        owner = self.target_for(symbol)
        scope = self.new_scope(node, symbol.kind, owner)
        self.definition_scopes[symbol.local_key] = scope.scope_key

        with self.using_owner(owner):
            for decorator in node.decorator_list:
                self.visit(decorator)

            self.visit_argument_expressions(node.args)
            self.visit_annotation(node.returns)

        with self.using_scope(scope):
            for statement in node.body:
                self.visit(statement)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self.visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.reject_type_parameters(node)

        symbol = self.definition_for(node)
        owner = self.target_for(symbol)
        scope = self.new_scope(node, "class", owner)
        self.definition_scopes[symbol.local_key] = scope.scope_key

        with self.using_owner(owner):
            for decorator in node.decorator_list:
                self.visit(decorator)

            for base in node.bases:
                self.visit(base)

            for class_keyword in node.keywords:
                self.visit(class_keyword.value)

        with self.using_scope(scope):
            for statement in node.body:
                self.visit(statement)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit_argument_expressions(node.args)
        scope = self.new_scope(node, "lambda", self.owner)

        with self.using_scope(scope):
            self.visit(node.body)

    def visit_comprehension_expression(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> None:
        first = node.generators[0]

        # The first iterable is evaluated outside the comprehension scope.
        self.visit(first.iter)
        scope = self.new_scope(node, "comprehension", self.owner)

        with self.using_scope(scope):
            self.visit(first.target)

            for condition in first.ifs:
                self.visit(condition)

            for generator in node.generators[1:]:
                self.visit(generator.iter)
                self.visit(generator.target)

                for condition in generator.ifs:
                    self.visit(condition)

            if isinstance(node, ast.DictComp):
                self.visit(node.key)
                self.visit(node.value)
            else:
                self.visit(node.elt)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.visit_comprehension_expression(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.visit_comprehension_expression(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.visit_comprehension_expression(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.visit_comprehension_expression(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        self.visit_annotation(node.annotation)

        if node.value is not None:
            self.visit(node.value)

    def visit_TypeAlias(self, node: ast.AST) -> None:
        raise RepoIndexError(
            "UNSUPPORTED_ANNOTATION_SCOPE",
            "type-alias annotation scopes require explicit support",
            file_path=self.file_path,
        )


def build_scope_index(repo_index: RepoIndex) -> ScopeIndex:
    """Build scope metadata from a freshly validated repository view."""
    owned_repo = build_repo_index(
        list(repo_index.files_by_path.values()),
        source_roots=repo_index.source_roots,
    )

    scopes: dict[str, ScopeInfo] = {}
    module_scopes: dict[str, str] = {}
    definition_scopes: dict[str, str] = {}
    contexts: dict[NodeLocation, ExpressionContext] = {}

    for file_path, parsed_file in owned_repo.files_by_path.items():
        visitor = _ScopeVisitor(owned_repo, file_path)

        try:
            tree = ast.parse(
                parsed_file.source_text,
                filename=file_path,
            )
        except SyntaxError as exc:
            raise RepoIndexError(
                "AST_PARSE_ERROR",
                "source is unsupported by the running Python AST "
                f"parser: {exc.msg}",
                file_path=file_path,
            ) from exc

        visitor.visit(tree)

        expected_definitions = {
            symbol.local_key
            for symbol in parsed_file.symbols
        }

        if visitor.matched_definitions != expected_definitions:
            raise RepoIndexError(
                "UNMATCHED_PARSER_DEFINITIONS",
                "not every parser definition matched an AST declaration",
                file_path=file_path,
            )

        scopes.update(visitor.scopes)
        module_scopes[file_path] = visitor.module_scope_key
        definition_scopes.update(visitor.definition_scopes)
        contexts.update(visitor.contexts)

    return ScopeIndex(
        repo_index=owned_repo,
        scopes_by_key=MappingProxyType(dict(sorted(scopes.items()))),
        module_scope_keys_by_path=MappingProxyType(module_scopes),
        definition_scope_keys_by_local_key=MappingProxyType(
            dict(sorted(definition_scopes.items()))
        ),
        contexts_by_location=MappingProxyType(
            dict(sorted(contexts.items()))
        ),
    )