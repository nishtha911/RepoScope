"""Repository-local static resolution. Never imports or executes analyzed code."""
import ast
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from reposcope.contracts.resolution import ResolutionResult, ResolverTarget
from reposcope.parsing.name_resolver import (
    _SimpleNameResolver, _Outcome, _path_established, _unresolved,
)
from reposcope.parsing.resolver import collect_references, LookupExpression


def _outcome(targets, rule, *, inferred=False):
    unique = {(t.target_kind, t.module_key, t.symbol_key): t for t in targets}
    targets = tuple(unique[k] for k in sorted(unique, key=str))
    if not targets:
        return _unresolved(rule, "No supported repository-local target was established.")
    status = "AMBIGUOUS" if len(targets) > 1 else ("INFERRED" if inferred else "EXACT")
    return _Outcome(status, targets, rule, "Static repository lookup; not a runtime guarantee.")


class ReferenceResolver(_SimpleNameResolver):
    def __init__(self, collection):
        super().__init__(collection)
        self.active = set()
        self.nodes = {}
        self.definition_nodes = {}
        for path, parsed in self.repo.files_by_path.items():
            raw = parsed.source_text.encode("utf-8")
            starts = [0] + [i + 1 for i, value in enumerate(raw) if value == 10]
            for node in ast.walk(ast.parse(parsed.source_text, filename=path)):
                if not hasattr(node, "lineno"):
                    continue
                start = starts[node.lineno - 1] + node.col_offset
                end = starts[node.end_lineno - 1] + node.end_col_offset
                self.nodes[(path, type(node).__name__, start, end)] = node
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.definition_nodes[(path, start)] = node

    def select_events(self, events, reference):
        frame = self.execution_frame(reference.site.scope_key)
        if any(self.execution_frame(e.scope_key) == frame and
               _path_established(e.control_path, reference.control_path) for e in events):
            events = [e for e in events if self.execution_frame(e.scope_key) == frame or
                      self.scopes.scopes_by_key[self.execution_frame(e.scope_key)].kind != "module"]
        if all(self.execution_frame(e.scope_key) == frame for e in events):
            selected = []
            for event in reversed(events):
                selected.append(event)
                if _path_established(event.control_path, reference.control_path):
                    break
            events = list(reversed(selected))
        return events

    def module_lookup(self, name):
        return _outcome([self.repo.module_target(m.file_path)
                         for m in self.repo.module_candidates(name)], "MODULE_LOOKUP")

    def absolute_import_name(self, info, file_path):
        if info.level == 0:
            return info.module or ""
        module = self.repo.module_for_file(file_path)
        if not module.module_name:
            return None
        parts = module.module_name.split(".")
        if PurePosixPath(file_path).name != "__init__.py":
            parts = parts[:-1]
        if info.level > len(parts):
            return None
        parts = parts[:len(parts) - info.level + 1]
        if info.module:
            parts.extend(info.module.split("."))
        return ".".join(parts)

    def import_target(self, info, reference, *, binding=False):
        if info is None or info.imported_name == "*":
            return _unresolved("UNSUPPORTED_IMPORT", "Wildcard or missing import metadata.")
        name = self.absolute_import_name(info, reference.site.file_path)
        if name is None:
            return _unresolved("INVALID_RELATIVE_IMPORT", "Relative import escapes the package.")
        if info.form == "import":
            return self.module_lookup(info.bound_module if binding else name)
        parent = self.module_lookup(name)
        if parent.status == "UNRESOLVED":
            return parent
        results = [self.member(t, info.imported_name, reference) for t in parent.targets]
        return self.combine(results, "FROM_IMPORT")

    def combine(self, outcomes, rule, *, inferred=False):
        outcomes = list(outcomes)
        if not outcomes or any(o.status == "UNRESOLVED" for o in outcomes):
            return _unresolved(rule, "At least one possible lookup path is unsupported or unresolved.")
        return _outcome([t for o in outcomes for t in o.targets], rule,
                        inferred=inferred or any(o.status == "INFERRED" for o in outcomes))

    def export_reference(self, reference, scope):
        return replace(reference, site=reference.site.model_copy(update={
            "scope_key": scope.scope_key, "file_path": scope.file_path,
            "start_byte": scope.end_byte + 1,
        }), control_path=())

    def member(self, target, name, reference):
        token = (target.module_key, target.symbol_key, name)
        if token in self.active:
            return _unresolved("LOOKUP_CYCLE", "Cyclic import or member lookup.")
        self.active.add(token)
        try:
            if target.target_kind == "module":
                key = self.scopes.module_scope_keys_by_path[target.file_path]
            else:
                definition = self.repo.definitions_by_local_key[target.symbol_key]
                if definition.kind != "class":
                    return _unresolved("NON_CLASS_MEMBER", "Only modules and classes have modeled members.")
                node = self.definition_nodes[(target.file_path, definition.definition_start_byte)]
                if node.decorator_list or node.keywords:
                    return _unresolved("DYNAMIC_CLASS", "Decorated classes and explicit metaclasses are unsupported.")
                key = self.scopes.definition_scope_keys_by_local_key[target.symbol_key]
            scope = self.scopes.scopes_by_key[key]
            context = self.export_reference(reference, scope)
            if self.namespace_uncertainty(key, name, context):
                return _unresolved("NAMESPACE_UNCERTAINTY", "Member namespace can be modified dynamically.")
            events = self.available_events(key, name, context)
            if events:
                result = self.evaluate_events(events, context)
                if result.status in {"EXACT", "INFERRED", "AMBIGUOUS"}:
                    for candidate in result.targets:
                        if candidate.target_kind == "symbol":
                            symbol = self.repo.definitions_by_local_key[candidate.symbol_key]
                            node = self.definition_nodes[(candidate.file_path, symbol.definition_start_byte)]
                            allowed = {"staticmethod", "classmethod"}
                            if any(not isinstance(d, ast.Name) or d.id not in allowed
                                   for d in node.decorator_list):
                                return _unresolved("DECORATED_MEMBER", "Custom descriptors/decorators are unsupported.")
                return result
            if target.target_kind == "module":
                module = self.repo.module_for_file(target.file_path)
                if PurePosixPath(target.file_path).name == "__init__.py" and module.module_name:
                    return self.module_lookup(module.module_name + "." + name)
            # Do not guess Python MRO or inherited descriptor behavior.
            return _unresolved("MEMBER_NOT_ESTABLISHED", "No direct supported member; inherited lookup is not modeled.")
        finally:
            self.active.remove(token)

    def evaluate_events(self, events, reference):
        events = self.select_events(events, reference)
        if not any(e.kind == "import" for e in events):
            return super().evaluate_events(events, reference)
        if any(e.kind not in {"definition", "import"} or e.resolution_blocker for e in events):
            return _unresolved("SHADOWED_OR_UNKNOWN_BINDING", "Import can be shadowed by another binding.")
        if not any(_path_established(e.control_path, reference.control_path) for e in events):
            return _unresolved("CONDITIONAL_BINDING_NOT_ESTABLISHED", "Import binding is conditional.")
        outcomes = []
        for event in events:
            if event.kind == "definition":
                outcomes.append(_outcome([event.definition_target], "DEFINITION_BINDING"))
            else:
                context = replace(reference, site=reference.site.model_copy(update={"file_path": event.file_path}))
                outcomes.append(self.import_target(event.import_info, context, binding=True))
        return self.combine(outcomes, "IMPORTED_BINDING")

    def receiver_class(self, name, reference):
        scope = self.scopes.scopes_by_key[reference.site.scope_key]
        if scope.kind != "method" or scope.parent_scope_key is None:
            return _unresolved("UNSUPPORTED_RECEIVER", "Receiver inference is limited to a direct method parameter.")
        owner = self.scopes.scopes_by_key[scope.parent_scope_key]
        if owner.kind != "class" or self.namespace_uncertainty(scope.scope_key, name, reference):
            return _unresolved("UNSUPPORTED_RECEIVER", "No stable enclosing class.")
        events = self.select_events(self.available_events(scope.scope_key, name, reference), reference)
        if len(events) != 1 or events[0].kind != "parameter":
            return _unresolved("REBOUND_RECEIVER", "Receiver parameter is missing, reassigned, or shadowed.")
        method = self.repo.definitions_by_local_key[scope.source_owner.symbol_key]
        node = self.definition_nodes[(scope.file_path, method.definition_start_byte)]
        args = [*node.args.posonlyargs, *node.args.args]
        if not args or args[0].arg != name:
            return _unresolved("UNSUPPORTED_RECEIVER", "Only the first positional receiver is inferred.")
        decorators = node.decorator_list
        if any(not isinstance(d, ast.Name) or d.id != "classmethod" for d in decorators):
            return _unresolved("UNSUPPORTED_RECEIVER", "Static/custom decorated receiver is unsupported.")
        return _outcome([owner.source_owner], "METHOD_RECEIVER", inferred=True)

    def resolve(self, reference):
        if reference.resolution_blocker:
            return _unresolved("BLOCKED_REFERENCE", reference.resolution_blocker)
        if reference.site.reference_kind == "import":
            return self.import_target(reference.import_info, reference)
        lookup = reference.lookup
        if lookup is None or lookup.head_name is None:
            return super().resolve(reference)
        if not lookup.attributes:
            outcome = self.resolve_name(lookup.head_name, reference)
        else:
            outcome = self.resolve_name(lookup.head_name, reference)
            if outcome.status == "UNRESOLVED" and outcome.rule_id == "SHADOWED_OR_UNKNOWN_BINDING":
                outcome = self.receiver_class(lookup.head_name, reference)
            for attribute in lookup.attributes:
                if outcome.status == "UNRESOLVED":
                    break
                outcome = self.combine(
                    [self.member(t, attribute, reference) for t in outcome.targets],
                    "ATTRIBUTE_LOOKUP", inferred=outcome.status == "INFERRED",
                )
        if reference.site.reference_kind == "base_class" and any(
            t.target_kind != "symbol" or
            self.repo.definitions_by_local_key[t.symbol_key].kind != "class"
            for t in outcome.targets
        ):
            return _unresolved("BASE_TARGET_NOT_ESTABLISHED_AS_CLASS", "A base target must be a class.")
        return outcome


def resolve_references(collection):
    """Revalidate snapshot, then return one result for every reference."""
    owned = collect_references(collection.binding_index)
    resolver = ReferenceResolver(owned)
    results = []
    for reference in owned.references:
        outcome = resolver.resolve(reference)
        for target in outcome.targets:
            resolver.repo.validate_target(target)
        results.append(ResolutionResult(
            reference=reference.site, status=outcome.status,
            targets=list(outcome.targets), rule_id=outcome.rule_id,
            reason=outcome.reason,
            confidence={"EXACT": 1.0, "INFERRED": 0.5,
                        "AMBIGUOUS": None, "UNRESOLVED": None}[outcome.status],
        ))
    return tuple(results)


@dataclass(frozen=True)
class AnalysisEdge:
    source: ResolverTarget
    target: ResolverTarget
    kind: str
    status: str
    confidence: float
    reference_key: str


def resolved_edges(results):
    """Emit analysis edges only for unique targets; retain results for gaps."""
    kinds = {"call": "CALLS", "import": "IMPORTS", "base_class": "INHERITS"}
    return tuple(AnalysisEdge(
        source=r.reference.source_owner, target=r.targets[0],
        kind=kinds[r.reference.reference_kind], status=r.status,
        confidence=r.confidence, reference_key=r.reference.reference_key,
    ) for r in results if r.status in {"EXACT", "INFERRED"})
