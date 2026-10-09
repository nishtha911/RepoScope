"""Static binding events and control-flow evidence for the resolver.

This index records static name-binding operations. It does not simulate
execution, resolve references, or guarantee runtime target identity.
"""

import ast
import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Iterator, Literal, Mapping

from reposcope.contracts.resolution import ResolverTarget
from reposcope.parsing.declaration_index import (
    DeclarationKind,
    ImportInfo,
    NameNamespace,
    ScopeDirectives,
    _DeclarationCollector,
    build_declaration_index,
)
from reposcope.parsing.repo_index import RepoIndexError
from reposcope.parsing.scope_index import NodeLocation, ScopeIndex


BindingKind = DeclarationKind | Literal[
    "assignment",
    "annotation",
    "loop",
    "with",
    "exception",
    "pattern",
    "delete",
    "namespace_mutation",
    "dynamic_namespace",
]


@dataclass(frozen=True)
class BindingEvent:
    kind: BindingKind
    name: str | None

    # Scope executing the operation, versus scope storing the name.
    scope_key: str
    binding_scope_key: str | None
    namespace: NameNamespace

    file_path: str
    start_byte: int
    end_byte: int

    # Source-position evidence, not a complete execution timeline.
    activation_byte: int
    ordinal: int

    definition_target: ResolverTarget | None
    import_info: ImportInfo | None
    parameter_kind: str | None
    value_location: NodeLocation | None

    control_path: tuple[str, ...]
    resolution_blocker: str | None


@dataclass(frozen=True)
class _PendingBinding:
    event: BindingEvent
    name_scope_key: str


@dataclass(frozen=True)
class BindingIndex:
    scope_index: ScopeIndex
    directives_by_scope: Mapping[str, ScopeDirectives]
    local_names_by_scope: Mapping[str, frozenset[str]]

    events_by_scope: Mapping[str, tuple[BindingEvent, ...]]
    events_by_binding_scope_and_name: Mapping[
        tuple[str, str],
        tuple[BindingEvent, ...],
    ]
    control_paths_by_location: Mapping[
        NodeLocation,
        tuple[str, ...],
    ]

    @property
    def coverage(self) -> Literal["static_bindings"]:
        return "static_bindings"

    def events_for(
        self,
        binding_scope_key: str,
        name: str,
    ) -> tuple[BindingEvent, ...]:
        return self.events_by_binding_scope_and_name.get(
            (binding_scope_key, name),
            (),
        )


class _BindingCollector(_DeclarationCollector):
    def __init__(
        self,
        scope_index: ScopeIndex,
        file_path: str,
        directives: Mapping[str, ScopeDirectives],
    ) -> None:
        super().__init__(scope_index, file_path, directives)
        self.pending: list[_PendingBinding] = []
        self.control_path: tuple[str, ...] = ()
        self.paths: dict[NodeLocation, tuple[str, ...]] = {}

    def location(self, node: ast.AST) -> NodeLocation:
        start, end = self.span(node)
        return (
            self.file_path,
            type(node).__name__,
            start,
            end,
        )

    def visit(self, node: ast.AST):
        if hasattr(node, "lineno"):
            self.paths[self.location(node)] = self.control_path

        return super().visit(node)

    @contextmanager
    def under(
        self,
        node: ast.AST,
        branch: str,
    ) -> Iterator[None]:
        start, end = self.span(node)
        label = json.dumps(
            [
                "control",
                self.file_path,
                type(node).__name__,
                start,
                end,
                branch,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

        previous = self.control_path
        self.control_path = (*previous, label)

        try:
            yield
        finally:
            self.control_path = previous

    @contextmanager
    def fresh_execution_path(self) -> Iterator[None]:
        previous = self.control_path
        self.control_path = ()

        try:
            yield
        finally:
            self.control_path = previous

    def emit(
        self,
        node: ast.AST,
        kind: BindingKind,
        name: str | None,
        *,
        scope_key: str | None = None,
        definition_target: ResolverTarget | None = None,
        import_info: ImportInfo | None = None,
        parameter_kind: str | None = None,
        value_node: ast.AST | None = None,
        activation_byte: int | None = None,
        name_scope_key: str | None = None,
    ) -> None:
        location = self.location(node)
        context = self.scope_index.contexts_by_location.get(location)

        if scope_key is None:
            scope_key = self.context(node).scope_key

        if name_scope_key is None:
            name_scope_key = scope_key

        start, end = self.span(node)

        if activation_byte is None:
            activation_byte = (
                self.scope_index.scopes_by_key[scope_key].start_byte
                if kind == "parameter"
                else end
            )

        path = () if kind == "parameter" else self.control_path

        event = BindingEvent(
            kind=kind,
            name=name,
            scope_key=scope_key,
            binding_scope_key=None,
            namespace=self.namespace_for(name_scope_key, name),
            file_path=self.file_path,
            start_byte=start,
            end_byte=end,
            activation_byte=activation_byte,
            ordinal=len(self.pending),
            definition_target=definition_target,
            import_info=import_info,
            parameter_kind=parameter_kind,
            value_location=(
                self.location(value_node)
                if value_node is not None
                else None
            ),
            control_path=path,
            resolution_blocker=(
                context.resolution_blocker
                if context is not None
                else None
            ),
        )

        self.pending.append(
            _PendingBinding(
                event=event,
                name_scope_key=name_scope_key,
            )
        )

    def generic_visit(self, node: ast.AST):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                self.visit(decorator)

            self.visit(node.args)

            if node.returns is not None:
                self.visit(node.returns)

            with self.fresh_execution_path():
                for statement in node.body:
                    self.visit(statement)

            return None

        if isinstance(node, ast.Lambda):
            self.visit(node.args)

            with self.fresh_execution_path():
                self.visit(node.body)

            return None

        return super().generic_visit(node)

    def bind_target(
        self,
        target: ast.AST,
        kind: BindingKind,
        *,
        value_node: ast.AST | None = None,
        activation_byte: int | None = None,
        name_scope_key: str | None = None,
    ) -> None:
        if isinstance(target, ast.Name):
            self.emit(
                target,
                kind,
                target.id,
                value_node=value_node,
                activation_byte=activation_byte,
                name_scope_key=name_scope_key,
            )
            return

        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.bind_target(
                    element,
                    kind,
                    activation_byte=activation_byte,
                    name_scope_key=name_scope_key,
                )
            return

        if isinstance(target, ast.Starred):
            self.bind_target(
                target.value,
                kind,
                activation_byte=activation_byte,
                name_scope_key=name_scope_key,
            )
            return

        if isinstance(target, (ast.Attribute, ast.Subscript)):
            self.emit(
                target,
                "namespace_mutation",
                None,
                activation_byte=activation_byte,
            )
            return

        raise RepoIndexError(
            "UNSUPPORTED_BINDING_TARGET",
            f"unsupported target: {type(target).__name__}",
            file_path=self.file_path,
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        activation = self.span(node)[1]

        for target in node.targets:
            self.visit(target)
            self.bind_target(
                target,
                "assignment",
                value_node=(
                    node.value
                    if isinstance(target, ast.Name)
                    else None
                ),
                activation_byte=activation,
            )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)

        if node.value is not None:
            self.visit(node.value)

        self.visit(node.target)
        self.bind_target(
            node.target,
            "annotation" if node.value is None else "assignment",
            value_node=node.value,
            activation_byte=self.span(node)[1],
        )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.target)
        self.visit(node.value)
        self.bind_target(
            node.target,
            "assignment",
            activation_byte=self.span(node)[1],
        )

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.visit(node.target)

        execution_scope = self.context(node.target).scope_key
        name_scope = execution_scope

        while (
            self.scope_index.scopes_by_key[name_scope].kind
            == "comprehension"
        ):
            parent = self.scope_index.scopes_by_key[
                name_scope
            ].parent_scope_key

            if parent is None:
                raise RepoIndexError(
                    "INVALID_WALRUS_SCOPE",
                    "comprehension has no enclosing scope",
                    file_path=self.file_path,
                )

            name_scope = parent

        self.bind_target(
            node.target,
            "assignment",
            value_node=node.value,
            activation_byte=self.span(node)[1],
            name_scope_key=name_scope,
        )

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.visit(target)
            self.bind_target(
                target,
                "delete",
                activation_byte=self.span(node)[1],
            )

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)

        for branch, statements in (
            ("body", node.body),
            ("else", node.orelse),
        ):
            with self.under(node, branch):
                for statement in statements:
                    self.visit(statement)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)

        with self.under(node, "body"):
            self.visit(node.body)

        with self.under(node, "else"):
            self.visit(node.orelse)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.visit(node.values[0])

        for position, value in enumerate(node.values[1:], start=1):
            with self.under(node, f"short-circuit:{position}"):
                self.visit(value)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)

        with self.under(node, "body"):
            self.visit(node.target)
            self.bind_target(
                node.target,
                "loop",
                activation_byte=self.span(node.iter)[1],
            )

            for statement in node.body:
                self.visit(statement)

        with self.under(node, "else"):
            for statement in node.orelse:
                self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)

        for branch, statements in (
            ("body", node.body),
            ("else", node.orelse),
        ):
            with self.under(node, branch):
                for statement in statements:
                    self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        with self.under(node, "body"):
            for item in node.items:
                self.visit(item.context_expr)

                if item.optional_vars is not None:
                    self.visit(item.optional_vars)
                    self.bind_target(
                        item.optional_vars,
                        "with",
                        activation_byte=self.span(item.context_expr)[1],
                    )

            for statement in node.body:
                self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_Try(self, node: ast.Try) -> None:
        for branch, statements in (
            ("body", node.body),
            ("else", node.orelse),
            ("finally", node.finalbody),
        ):
            with self.under(node, branch):
                for statement in statements:
                    self.visit(statement)

        for position, handler in enumerate(node.handlers):
            with self.under(node, f"handler:{position}"):
                self.visit(handler)

    visit_TryStar = visit_Try

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)

        if node.name is not None:
            self.emit(
                node,
                "exception",
                node.name,
                activation_byte=self.span(node.body[0])[0],
            )

        for statement in node.body:
            self.visit(statement)

        if node.name is not None:
            self.emit(
                node,
                "delete",
                node.name,
                activation_byte=self.span(node)[1],
            )

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)

        for position, case in enumerate(node.cases):
            with self.under(case.pattern, f"case:{position}"):
                self.visit(case.pattern)

                if case.guard is not None:
                    self.visit(case.guard)

                for statement in case.body:
                    self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)

        if node.name is not None:
            self.emit(node, "pattern", node.name)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.emit(node, "pattern", node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        self.generic_visit(node)

        if node.rest is not None:
            self.emit(node, "pattern", node.rest)

    def visit_MatchOr(self, node: ast.MatchOr) -> None:
        for position, pattern in enumerate(node.patterns):
            with self.under(node, f"alternative:{position}"):
                self.visit(pattern)

    def visit_comprehension(self, node: ast.AST) -> None:
        first = node.generators[0]
        self.visit(first.iter)

        with self.under(node, "iteration"):
            self.visit(first.target)
            self.bind_target(
                first.target,
                "loop",
                activation_byte=self.span(first.iter)[1],
            )

            for condition in first.ifs:
                self.visit(condition)

            for generator in node.generators[1:]:
                self.visit(generator.iter)
                self.visit(generator.target)
                self.bind_target(
                    generator.target,
                    "loop",
                    activation_byte=self.span(generator.iter)[1],
                )

                for condition in generator.ifs:
                    self.visit(condition)

            if isinstance(node, ast.DictComp):
                self.visit(node.key)
                self.visit(node.value)
            else:
                self.visit(node.elt)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.visit_comprehension(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name):
            return

        if node.func.id in {"exec", "eval", "globals", "locals", "vars"}:
            self.emit(node, "dynamic_namespace", None)

        elif node.func.id in {"setattr", "delattr"}:
            self.emit(node, "namespace_mutation", None)


def build_binding_index(scope_index: ScopeIndex) -> BindingIndex:
    """Collect static bindings, including storage-scope routing."""
    declarations = build_declaration_index(scope_index)
    scopes = declarations.scope_index
    directives = declarations.directives_by_scope

    pending: list[_PendingBinding] = []
    paths: dict[NodeLocation, tuple[str, ...]] = {}

    for file_path, parsed_file in scopes.repo_index.files_by_path.items():
        collector = _BindingCollector(
            scopes,
            file_path,
            directives,
        )
        collector.visit(
            ast.parse(parsed_file.source_text, filename=file_path)
        )
        pending.extend(collector.pending)
        paths.update(collector.paths)

    local_names: dict[str, set[str]] = {
        key: set()
        for key in scopes.scopes_by_key
    }

    for row in pending:
        event = row.event
        name_scope = scopes.scopes_by_key[row.name_scope_key]

        if event.name is not None and (
            event.namespace == "local"
            or name_scope.kind == "module"
        ):
            local_names[row.name_scope_key].add(event.name)

    def storage_scope(row: _PendingBinding) -> str | None:
        event = row.event

        if event.name is None:
            return None

        if event.namespace == "global":
            return scopes.module_scope_keys_by_path[event.file_path]

        if event.namespace == "local":
            return row.name_scope_key

        parent = scopes.scopes_by_key[
            row.name_scope_key
        ].lookup_parent_scope_key

        while parent is not None:
            candidate = scopes.scopes_by_key[parent]

            if (
                candidate.kind in {"function", "method", "lambda"}
                and event.name in local_names[parent]
            ):
                return parent

            parent = candidate.lookup_parent_scope_key

        raise RepoIndexError(
            "UNBOUND_NONLOCAL",
            f"no enclosing function binding for {event.name!r}",
            file_path=event.file_path,
        )

    by_execution: dict[str, list[BindingEvent]] = {
        key: []
        for key in scopes.scopes_by_key
    }
    by_name: dict[tuple[str, str], list[BindingEvent]] = {}

    for row in pending:
        binding_scope = storage_scope(row)
        event = replace(
            row.event,
            binding_scope_key=binding_scope,
        )

        by_execution[event.scope_key].append(event)

        if event.name is not None:
            by_name.setdefault(
                (binding_scope, event.name),
                [],
            ).append(event)

    def ordered(events: list[BindingEvent]) -> tuple[BindingEvent, ...]:
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.activation_byte,
                    event.ordinal,
                ),
            )
        )

    return BindingIndex(
        scope_index=scopes,
        directives_by_scope=directives,
        local_names_by_scope=MappingProxyType({
            key: frozenset(names)
            for key, names in sorted(local_names.items())
        }),
        events_by_scope=MappingProxyType({
            key: ordered(events)
            for key, events in sorted(by_execution.items())
        }),
        events_by_binding_scope_and_name=MappingProxyType({
            key: ordered(events)
            for key, events in sorted(by_name.items())
        }),
        control_paths_by_location=MappingProxyType(
            dict(sorted(paths.items()))
        ),
    )