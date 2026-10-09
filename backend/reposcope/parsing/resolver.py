"""Reference collection for the two-pass Python resolver.

This stage collects validated reference sites and lookup metadata.
Name resolution and ResolutionResult production are added next.
"""

import ast
from dataclasses import dataclass

from reposcope.contracts.resolution import (
    ReferenceKind,
    ReferenceSite,
    make_reference_key,
)
from reposcope.parsing.binding_index import (
    BindingIndex,
    build_binding_index,
)
from reposcope.parsing.declaration_index import ImportInfo
from reposcope.parsing.repo_index import RepoIndexError
from reposcope.parsing.scope_index import NodeLocation


@dataclass(frozen=True)
class LookupExpression:
    location: NodeLocation
    head_name: str | None
    attributes: tuple[str, ...]


@dataclass(frozen=True)
class CollectedReference:
    site: ReferenceSite
    node_location: NodeLocation
    lookup: LookupExpression | None
    import_info: ImportInfo | None
    control_path: tuple[str, ...]
    resolution_blocker: str | None


@dataclass(frozen=True)
class ReferenceCollection:
    binding_index: BindingIndex
    references: tuple[CollectedReference, ...]


class _ReferenceCollector:
    def __init__(
        self,
        binding_index: BindingIndex,
        file_path: str,
    ) -> None:
        self.binding_index = binding_index
        self.scope_index = binding_index.scope_index
        self.file_path = file_path

        self.parsed_file = (
            self.scope_index.repo_index.files_by_path[file_path]
        )
        self.buffer = self.parsed_file.source_text.encode("utf-8")

        self.line_starts = [0]
        self.line_starts.extend(
            position + 1
            for position, value in enumerate(self.buffer)
            if value == 10
        )

    def span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.line_starts[node.lineno - 1] + node.col_offset,
            self.line_starts[node.end_lineno - 1] + node.end_col_offset,
        )

    def location(self, node: ast.AST) -> NodeLocation:
        start, end = self.span(node)

        return (
            self.file_path,
            type(node).__name__,
            start,
            end,
        )

    def lookup_expression(self, node: ast.AST) -> LookupExpression:
        attributes: list[str] = []
        current = node

        while isinstance(current, ast.Attribute):
            attributes.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            head_name = current.id
            path = tuple(reversed(attributes))
        else:
            # Dynamic receivers and higher-order expressions remain
            # represented, but are not treated as simple dotted names.
            head_name = None
            path = ()

        return LookupExpression(
            location=self.location(node),
            head_name=head_name,
            attributes=path,
        )

    def collect_site(
        self,
        node: ast.AST,
        reference_kind: ReferenceKind,
        *,
        lookup_node: ast.AST | None = None,
        import_info: ImportInfo | None = None,
        import_control_path: tuple[str, ...] | None = None,
    ) -> CollectedReference:
        location = self.location(node)
        start, end = self.span(node)

        context = self.scope_index.context_for(
            self.file_path,
            type(node).__name__,
            start,
            end,
        )

        if context.scope_key not in self.scope_index.scopes_by_key:
            raise RepoIndexError(
                "UNKNOWN_REFERENCE_SCOPE",
                "reference lookup scope is missing",
                file_path=self.file_path,
            )

        self.scope_index.repo_index.validate_target(
            context.source_owner
        )

        expression = self.buffer[start:end].decode("utf-8")

        site = ReferenceSite(
            reference_key=make_reference_key(
                self.file_path,
                reference_kind,
                start,
                end,
                context.scope_key,
            ),
            reference_kind=reference_kind,
            file_path=self.file_path,
            source_sha256=self.parsed_file.source_sha256,
            parse_buffer_sha256=self.parsed_file.parse_buffer_sha256,
            scope_key=context.scope_key,
            source_owner=context.source_owner,
            expression=expression,
            start_line=self.buffer.count(b"\n", 0, start) + 1,
            end_line=self.buffer.count(b"\n", 0, end - 1) + 1,
            start_byte=start,
            end_byte=end,
        )
        site.validate_against_file(self.parsed_file)

        if import_control_path is not None:
            control_path = import_control_path
        else:
            control_path = (
                self.binding_index.control_paths_by_location.get(
                    location
                )
            )

            if control_path is None:
                raise RepoIndexError(
                    "MISSING_REFERENCE_CONTROL_PATH",
                    "reference has no indexed control-flow context",
                    file_path=self.file_path,
                )

        return CollectedReference(
            site=site,
            node_location=location,
            lookup=(
                self.lookup_expression(lookup_node)
                if lookup_node is not None
                else None
            ),
            import_info=import_info,
            control_path=control_path,
            resolution_blocker=context.resolution_blocker,
        )

    def collect_import(
        self,
        alias: ast.alias,
    ) -> CollectedReference:
        start, end = self.span(alias)
        context = self.scope_index.context_for(
            self.file_path,
            "alias",
            start,
            end,
        )

        matches = [
            event
            for event in self.binding_index.events_by_scope[
                context.scope_key
            ]
            if event.kind in {"import", "wildcard_import"}
            and event.file_path == self.file_path
            and event.start_byte == start
            and event.end_byte == end
        ]

        if len(matches) != 1 or matches[0].import_info is None:
            raise RepoIndexError(
                "IMPORT_BINDING_MISMATCH",
                "import item must match exactly one binding record",
                file_path=self.file_path,
            )

        event = matches[0]

        return self.collect_site(
            alias,
            "import",
            import_info=event.import_info,
            import_control_path=event.control_path,
        )

    def collect(self, tree: ast.Module) -> list[CollectedReference]:
        references: list[CollectedReference] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                references.append(
                    self.collect_site(
                        node,
                        "call",
                        lookup_node=node.func,
                    )
                )

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    references.append(self.collect_import(alias))

            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    references.append(
                        self.collect_site(
                            base,
                            "base_class",
                            lookup_node=base,
                        )
                    )

        return references


def collect_references(
    binding_index: BindingIndex,
) -> ReferenceCollection:
    """Collect references from a freshly validated analysis snapshot."""
    owned_bindings = build_binding_index(
        binding_index.scope_index
    )
    references: list[CollectedReference] = []

    for file_path, parsed_file in (
        owned_bindings.scope_index.repo_index.files_by_path.items()
    ):
        tree = ast.parse(
            parsed_file.source_text,
            filename=file_path,
        )
        collector = _ReferenceCollector(
            owned_bindings,
            file_path,
        )
        references.extend(collector.collect(tree))

    keys = [
        reference.site.reference_key
        for reference in references
    ]

    if len(set(keys)) != len(keys):
        raise RepoIndexError(
            "DUPLICATE_REFERENCE_KEY",
            "reference collection produced duplicate identities",
        )

    ordered = tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.site.file_path,
                reference.site.start_byte,
                reference.site.end_byte,
                reference.site.reference_kind,
            ),
        )
    )

    return ReferenceCollection(
        binding_index=owned_bindings,
        references=ordered,
    )