"""Conservative simple-name resolution for collected references.

Supported:
- Unqualified repository definition names.
- Lexical lookup, global/nonlocal directives, and local shadowing.
- Immediate source ordering and conservative deferred lookup.
- Conditional binding evidence.
- Class-only exact base targets.

Import and attribute lookup are added in later stages.
"""

import ast
import json
from dataclasses import dataclass

from reposcope.contracts.resolution import (
    ResolutionResult,
    ResolutionStatus,
    ResolverTarget,
)
from reposcope.parsing.binding_index import BindingEvent
from reposcope.parsing.resolver import (
    CollectedReference,
    ReferenceCollection,
    collect_references,
)


@dataclass(frozen=True)
class _Outcome:
    status: ResolutionStatus
    targets: tuple[ResolverTarget, ...]
    rule_id: str
    reason: str


def _unresolved(rule_id: str, reason: str) -> _Outcome:
    return _Outcome(
        status="UNRESOLVED",
        targets=(),
        rule_id=rule_id,
        reason=reason,
    )


def _unique_targets(
    events: list[BindingEvent],
) -> tuple[ResolverTarget, ...]:
    targets = {}

    for event in events:
        target = event.definition_target

        if target is None:
            continue

        key = (
            target.target_kind,
            target.module_key,
            target.symbol_key,
        )
        targets[key] = target

    return tuple(
        targets[key]
        for key in sorted(targets)
    )


def _compatible_paths(
    event_path: tuple[str, ...],
    reference_path: tuple[str, ...],
) -> bool:
    exclusive_types = {"If", "IfExp", "MatchOr"}

    for event_label in event_path:
        event_parts = json.loads(event_label)

        if event_parts[2] not in exclusive_types:
            continue

        for reference_label in reference_path:
            reference_parts = json.loads(reference_label)

            if (
                event_parts[:-1] == reference_parts[:-1]
                and event_parts[-1] != reference_parts[-1]
            ):
                return False

    return True


def _path_established(
    event_path: tuple[str, ...],
    reference_path: tuple[str, ...],
) -> bool:
    return (
        len(event_path) <= len(reference_path)
        and reference_path[:len(event_path)] == event_path
    )


class _SimpleNameResolver:
    def __init__(self, collection: ReferenceCollection) -> None:
        self.collection = collection
        self.bindings = collection.binding_index
        self.scopes = self.bindings.scope_index
        self.repo = self.scopes.repo_index

        self.mutation_nodes: dict[
            tuple[str, int, int],
            list[ast.AST],
        ] = {}

        for file_path, parsed_file in self.repo.files_by_path.items():
            buffer = parsed_file.source_text.encode("utf-8")
            starts = [0]
            starts.extend(
                position + 1
                for position, value in enumerate(buffer)
                if value == 10
            )

            tree = ast.parse(
                parsed_file.source_text,
                filename=file_path,
            )

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    (ast.Attribute, ast.Subscript, ast.Call),
                ):
                    continue

                start = starts[node.lineno - 1] + node.col_offset
                end = starts[node.end_lineno - 1] + node.end_col_offset

                self.mutation_nodes.setdefault(
                    (file_path, start, end),
                    [],
                ).append(node)

    def execution_frame(self, scope_key: str) -> str:
        current = scope_key

        while True:
            scope = self.scopes.scopes_by_key[current]

            if scope.kind in {
                "module",
                "function",
                "method",
                "lambda",
            }:
                return current

            if scope.kind == "comprehension":
                generator_location = (
                    scope.file_path,
                    "GeneratorExp",
                    scope.start_byte,
                    scope.end_byte,
                )

                if (
                    generator_location
                    in self.scopes.contexts_by_location
                ):
                    return current

            if scope.parent_scope_key is None:
                return current

            current = scope.parent_scope_key

    def mutation_may_affect_name(
        self,
        event: BindingEvent,
        name: str,
    ) -> bool:
        nodes = self.mutation_nodes.get(
            (
                event.file_path,
                event.start_byte,
                event.end_byte,
            ),
            (),
        )

        for node in nodes:
            if isinstance(node, ast.Attribute):
                if node.attr == name:
                    return True

            elif isinstance(node, ast.Subscript):
                key = node.slice

                if isinstance(key, ast.Constant):
                    if key.value == name:
                        return True
                else:
                    return True

            elif isinstance(node, ast.Call):
                if len(node.args) < 2:
                    return True

                attribute = node.args[1]

                if not isinstance(attribute, ast.Constant):
                    return True

                if attribute.value == name:
                    return True

        return False

    def namespace_uncertainty(
        self,
        scope_key: str,
        name: str,
        reference: CollectedReference,
    ) -> str | None:
        scope = self.scopes.scopes_by_key[scope_key]
        reference_frame = self.execution_frame(
            reference.site.scope_key
        )

        if scope.kind == "module":
            candidate_events = [
                event
                for events in self.bindings.events_by_scope.values()
                for event in events
                if event.file_path == scope.file_path
            ]
        else:
            candidate_events = self.bindings.events_by_scope[scope_key]

        for event in candidate_events:
            if event.kind not in {
                "wildcard_import",
                "dynamic_namespace",
                "namespace_mutation",
            }:
                continue

            if not _compatible_paths(
                event.control_path,
                reference.control_path,
            ):
                continue

            if (
                self.execution_frame(event.scope_key) == reference_frame
                and event.activation_byte > reference.site.start_byte
            ):
                continue

            if (
                event.kind == "namespace_mutation"
                and not self.mutation_may_affect_name(event, name)
            ):
                continue

            return event.kind

        return None

    def available_events(
        self,
        scope_key: str,
        name: str,
        reference: CollectedReference,
    ) -> list[BindingEvent]:
        scope = self.scopes.scopes_by_key[scope_key]
        reference_frame = self.execution_frame(
            reference.site.scope_key
        )
        result = []

        for event in self.bindings.events_for(scope_key, name):
            if not _compatible_paths(
                event.control_path,
                reference.control_path,
            ):
                continue

            # Annotation-only statements do not establish a runtime
            # binding in module/class namespaces.
            if (
                event.kind == "annotation"
                and scope.kind in {"module", "class"}
            ):
                continue

            # Comprehension source order is not execution order.
            if (
                scope.kind != "comprehension"
                and self.execution_frame(event.scope_key)
                == reference_frame
                and event.activation_byte > reference.site.start_byte
            ):
                continue

            result.append(event)

        return result

    def evaluate_events(
        self,
        events: list[BindingEvent],
        reference: CollectedReference,
    ) -> _Outcome:
        reference_frame = self.execution_frame(
            reference.site.scope_key
        )

        current_frame_established = any(
            self.execution_frame(event.scope_key) == reference_frame
            and _path_established(
                event.control_path,
                reference.control_path,
            )
            for event in events
        )

        if current_frame_established:
            # A current-frame binding can supersede module-initialization
            # bindings. Keep other deferred function writes as uncertainty.
            events = [
                event
                for event in events
                if (
                    self.execution_frame(event.scope_key) == reference_frame
                    or self.scopes.scopes_by_key[
                        self.execution_frame(event.scope_key)
                    ].kind != "module"
                )
            ]

        immediate = all(
            self.execution_frame(event.scope_key) == reference_frame
            for event in events
        )

        if immediate:
            possible = []

            for event in reversed(events):
                possible.append(event)

                if _path_established(
                    event.control_path,
                    reference.control_path,
                ):
                    break

            events = list(reversed(possible))

        if any(
            event.resolution_blocker is not None
            for event in events
        ):
            return _unresolved(
                "BLOCKED_BINDING",
                "A possible binding has unsupported annotation semantics.",
            )

        if any(event.kind == "import" for event in events):
            return _unresolved(
                "IMPORT_LOOKUP_PENDING",
                "The name can be supplied by an import; import lookup "
                "is not implemented in this stage.",
            )

        if any(event.kind != "definition" for event in events):
            return _unresolved(
                "SHADOWED_OR_UNKNOWN_BINDING",
                "A parameter, assignment, deletion, or other non-definition "
                "binding prevents establishing a named-definition target.",
            )

        targets = _unique_targets(events)

        if not targets:
            return _unresolved(
                "MISSING_DEFINITION_TARGET",
                "No repository definition target is established.",
            )

        if reference.site.reference_kind == "base_class":
            if any(
                self.repo.definitions_by_local_key[
                    target.symbol_key
                ].kind != "class"
                for target in targets
            ):
                return _unresolved(
                    "BASE_TARGET_NOT_ESTABLISHED_AS_CLASS",
                    "A possible named target is not a class definition.",
                )

        if len(targets) > 1:
            return _Outcome(
                status="AMBIGUOUS",
                targets=targets,
                rule_id="AMBIGUOUS_NAMED_DEFINITION",
                reason=(
                    "Multiple named-definition targets remain possible "
                    "after scope, ordering, and branch checks."
                ),
            )

        if not any(
            _path_established(
                event.control_path,
                reference.control_path,
            )
            for event in events
        ):
            return _unresolved(
                "CONDITIONAL_BINDING_NOT_ESTABLISHED",
                "The only possible definition is conditional and its "
                "binding is not established for this reference.",
            )

        return _Outcome(
            status="EXACT",
            targets=targets,
            rule_id="EXACT_NAMED_DEFINITION",
            reason=(
                "One repository definition is established under the "
                "supported static name-binding rules; runtime success "
                "is not guaranteed."
            ),
        )

    def enclosing_nonlocal_scope(
        self,
        scope_key: str,
        name: str,
    ) -> str | None:
        parent = self.scopes.scopes_by_key[
            scope_key
        ].lookup_parent_scope_key

        while parent is not None:
            scope = self.scopes.scopes_by_key[parent]

            if (
                scope.kind in {"function", "method", "lambda"}
                and name in self.bindings.local_names_by_scope[parent]
            ):
                return parent

            parent = scope.lookup_parent_scope_key

        return None

    def resolve_name(
        self,
        name: str,
        reference: CollectedReference,
    ) -> _Outcome:
        current = reference.site.scope_key
        module_scope = self.scopes.module_scope_keys_by_path[
            reference.site.file_path
        ]
        visited = set()

        while current is not None:
            if current in visited:
                return _unresolved(
                    "LOOKUP_SCOPE_CYCLE",
                    "Name lookup encountered a repeated scope.",
                )

            visited.add(current)
            scope = self.scopes.scopes_by_key[current]
            directives = self.bindings.directives_by_scope[current]

            if (
                name in directives.global_names
                and current != module_scope
            ):
                current = module_scope
                continue

            if name in directives.nonlocal_names:
                current = self.enclosing_nonlocal_scope(
                    current,
                    name,
                )

                if current is None:
                    return _unresolved(
                        "MISSING_NONLOCAL_BINDING",
                        "No enclosing function binding was established.",
                    )

                continue

            uncertainty = self.namespace_uncertainty(
                current,
                name,
                reference,
            )

            if uncertainty is not None:
                return _unresolved(
                    "NAMESPACE_UNCERTAINTY",
                    f"Possible {uncertainty} prevents establishing "
                    f"the binding of {name!r}.",
                )

            events = self.available_events(
                current,
                name,
                reference,
            )

            if events:
                return self.evaluate_events(events, reference)

            locally_declared = (
                name in self.bindings.local_names_by_scope[current]
            )

            if scope.kind in {
                "function",
                "method",
                "lambda",
                "comprehension",
            } and locally_declared:
                return _unresolved(
                    "LOCAL_BINDING_NOT_AVAILABLE",
                    f"{name!r} is local to this scope, but no usable "
                    "binding is established at the reference.",
                )

            if scope.kind == "class" and locally_declared:
                # A class-local name absent from the class namespace
                # falls back to globals, not an enclosing function local.
                current = module_scope
            else:
                current = scope.lookup_parent_scope_key

        return _unresolved(
            "NAME_NOT_ESTABLISHED",
            f"No repository binding was established for {name!r}; "
            "builtin and external targets are not modeled here.",
        )

    def resolve(self, reference: CollectedReference) -> _Outcome:
        if reference.resolution_blocker is not None:
            return _unresolved(
                "BLOCKED_REFERENCE",
                reference.resolution_blocker,
            )

        if reference.site.reference_kind == "import":
            return _unresolved(
                "IMPORT_LOOKUP_PENDING",
                "Import-reference target lookup is added in the next stage.",
            )

        lookup = reference.lookup

        if lookup is None or lookup.head_name is None:
            return _unresolved(
                "DYNAMIC_LOOKUP_EXPRESSION",
                "The referenced expression is not a supported simple name.",
            )

        if lookup.attributes:
            return _unresolved(
                "ATTRIBUTE_LOOKUP_PENDING",
                "Dotted module/class/receiver lookup is added later.",
            )

        return self.resolve_name(
            lookup.head_name,
            reference,
        )


def resolve_simple_names(
    collection: ReferenceCollection,
) -> tuple[ResolutionResult, ...]:
    """Produce one result per freshly collected reference."""
    owned_collection = collect_references(
        collection.binding_index
    )
    resolver = _SimpleNameResolver(owned_collection)
    results = []

    for reference in owned_collection.references:
        outcome = resolver.resolve(reference)

        for target in outcome.targets:
            resolver.repo.validate_target(target)

        results.append(
            ResolutionResult(
                reference=reference.site,
                status=outcome.status,
                targets=list(outcome.targets),
                rule_id=outcome.rule_id,
                reason=outcome.reason,
                confidence=(
                    1.0
                    if outcome.status == "EXACT"
                    else None
                ),
            )
        )

    return tuple(results)