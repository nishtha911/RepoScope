"""Static repository resolver: imports, members and bounded type inference.

Analyzed source is never imported or executed. Type annotations are evidence,
not runtime guarantees. Unsupported/ambiguous flows remain unresolved.
"""
import ast
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from reposcope.contracts.resolution import ResolutionResult, ResolverTarget
from reposcope.parsing.name_resolver import (
    _SimpleNameResolver, _Outcome, _path_established, _unresolved,
)
from reposcope.parsing.resolver import collect_references


def _outcome(targets, rule, *, inferred=False):
    unique = {(t.target_kind, t.module_key, t.symbol_key): t for t in targets}
    targets = tuple(unique[k] for k in sorted(unique, key=str))
    if not targets:
        return _unresolved(rule, "No supported repository-local target was established.")
    status = "AMBIGUOUS" if len(targets) > 1 else ("INFERRED" if inferred else "EXACT")
    return _Outcome(status, targets, rule, "Static repository evidence; not a runtime guarantee.")


class _CoreResolver(_SimpleNameResolver):
    def __init__(self, collection):
        super().__init__(collection)
        self.active = set()
        self.nodes = {}
        self.definition_nodes = {}
        self.locations = {}
        for path, parsed in self.repo.files_by_path.items():
            raw = parsed.source_text.encode("utf-8")
            starts = [0] + [i + 1 for i, value in enumerate(raw) if value == 10]
            for node in ast.walk(ast.parse(parsed.source_text, filename=path)):
                if not hasattr(node, "lineno"):
                    continue
                start = starts[node.lineno - 1] + node.col_offset
                end = starts[node.end_lineno - 1] + node.end_col_offset
                location = (path, type(node).__name__, start, end)
                self.nodes[location] = node
                self.locations[id(node)] = location
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.definition_nodes[(path, start)] = node

    def mutation_may_affect_name(self, event, name):
        scope = self.scopes.scopes_by_key[event.scope_key]
        if scope.kind != "method":
            return super().mutation_may_affect_name(event, name)
        method = self.repo.definitions_by_local_key.get(scope.source_owner.symbol_key)
        node = self.definition_nodes.get((event.file_path, method.definition_start_byte)) if method else None
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.decorator_list:
            return super().mutation_may_affect_name(event, name)
        args = [*node.args.posonlyargs, *node.args.args]
        if not args:
            return super().mutation_may_affect_name(event, name)
        receiver = args[0].arg
        bindings = self.bindings.events_for(scope.scope_key, receiver)
        if len(bindings) != 1 or bindings[0].kind != "parameter":
            return super().mutation_may_affect_name(event, name)
        nodes = self.mutation_nodes.get((event.file_path, event.start_byte, event.end_byte), ())
        if not nodes:
            return super().mutation_may_affect_name(event, name)
        for item in nodes:
            current, has_attribute = item, False
            if not isinstance(current, (ast.Attribute, ast.Subscript)):
                return super().mutation_may_affect_name(event, name)
            while isinstance(current, (ast.Attribute, ast.Subscript)):
                has_attribute |= isinstance(current, ast.Attribute)
                current = current.value
            if not has_attribute or not isinstance(current, ast.Name) or current.id != receiver:
                return super().mutation_may_affect_name(event, name)
        return False

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

    def absolute_import_name(self, info, path):
        if info.level == 0:
            return info.module or ""
        module = self.repo.module_for_file(path)
        if not module.module_name:
            return None
        parts = module.module_name.split(".")
        if PurePosixPath(path).name != "__init__.py":
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
        return self.combine([self.member(t, info.imported_name, reference) for t in parent.targets], "FROM_IMPORT")

    def combine(self, outcomes, rule, *, inferred=False):
        outcomes = list(outcomes)
        if not outcomes or any(o.status == "UNRESOLVED" for o in outcomes):
            return _unresolved(rule, "At least one possible lookup path is unsupported or unresolved.")
        return _outcome([t for o in outcomes for t in o.targets], rule,
                        inferred=inferred or any(o.status == "INFERRED" for o in outcomes))

    def context(self, reference, scope_key, path, start, control_path=()):
        return replace(reference, site=reference.site.model_copy(update={
            "scope_key": scope_key, "file_path": path, "start_byte": start,
        }), control_path=control_path, resolution_blocker=None)

    def export_reference(self, reference, scope):
        return self.context(reference, scope.scope_key, scope.file_path, scope.end_byte + 1)

    def stdlib_binding(self, name, module, imported, path, before):
        if self.repo.module_candidates(module):
            return False
        key = self.scopes.module_scope_keys_by_path[path]
        events = self.bindings.events_for(key, name)
        if len(events) != 1:
            return False
        event = events[0]
        info = event.import_info
        return bool(event.kind == "import" and event.scope_key == key
                    and not event.control_path and not event.resolution_blocker
                    and event.activation_byte <= before and info
                    and info.form == "from" and info.level == 0
                    and info.module == module and info.imported_name == imported)

    def is_supported_dataclass(self, node, path):
        if not isinstance(node, ast.ClassDef) or not node.decorator_list:
            return False
        return all(isinstance(d, ast.Name) and self.stdlib_binding(
            d.id, "dataclasses", "dataclass", path, self.locations[id(d)][2]
        ) for d in node.decorator_list)

    def supported_definition(self, node, path, reference):
        if isinstance(node, ast.ClassDef):
            return not node.keywords and (not node.decorator_list or self.is_supported_dataclass(node, path))
        return all(isinstance(d, ast.Name) and d.id in {"staticmethod", "classmethod"}
                   for d in node.decorator_list)

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
                if not self.supported_definition(node, target.file_path, reference):
                    return _unresolved("DYNAMIC_CLASS", "Unsupported class decoration/metaclass.")
                key = self.scopes.definition_scope_keys_by_local_key[target.symbol_key]
            scope = self.scopes.scopes_by_key[key]
            context = self.export_reference(reference, scope)
            if self.namespace_uncertainty(key, name, context):
                return _unresolved("NAMESPACE_UNCERTAINTY", "Member namespace can be modified dynamically.")
            events = self.available_events(key, name, context)
            if events:
                result = self.evaluate_events(events, context)
                inferred = result.status == "INFERRED"
                for candidate in result.targets:
                    if candidate.target_kind != "symbol":
                        continue
                    symbol = self.repo.definitions_by_local_key[candidate.symbol_key]
                    node = self.definition_nodes[(candidate.file_path, symbol.definition_start_byte)]
                    if not self.supported_definition(node, candidate.file_path, context):
                        return _unresolved("DECORATED_MEMBER", "Unsupported decorator/descriptor.")
                    if not isinstance(node, ast.ClassDef) and any(
                        not isinstance(d, ast.Name) or d.id not in {"staticmethod", "classmethod"}
                        for d in node.decorator_list
                    ):
                        inferred = True
                if result.targets:
                    return _outcome(result.targets, result.rule_id, inferred=inferred)
                return result
            if target.target_kind == "module":
                module = self.repo.module_for_file(target.file_path)
                if PurePosixPath(target.file_path).name == "__init__.py" and module.module_name:
                    return self.module_lookup(module.module_name + "." + name)
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


@dataclass(frozen=True)
class _Value:
    target: ResolverTarget
    kind: str  # namespace (definition/module) or instance (inferred class)
    inferred: bool = False


class ReferenceResolver(_CoreResolver):
    def __init__(self, collection):
        super().__init__(collection)
        self.inference_active = set()
        self.forward_active = set()
        self.forward_cache = {}

    def node_reference(self, node, path, reference):
        location = self.locations.get(id(node))
        if location is None or location[0] != path:
            return None
        context = self.scopes.contexts_by_location.get(location)
        if context is None:
            return None
        return self.context(reference, context.scope_key, path, location[2],
                            self.bindings.control_paths_by_location.get(location, ()))

    def definition_context(self, target, reference):
        key = self.scopes.definition_scope_keys_by_local_key[target.symbol_key]
        scope = self.scopes.scopes_by_key[key]
        definition = self.repo.definitions_by_local_key[target.symbol_key]
        parent = scope.parent_scope_key
        return self.context(reference, parent, target.file_path,
                            definition.definition_start_byte) if parent is not None else None

    def forwarding_decorator(self, decorator, path, reference):
        key = (path, self.locations.get(id(decorator)))
        if key in self.forward_cache:
            return self.forward_cache[key]
        if key in self.forward_active:
            return False
        self.forward_active.add(key)
        try:
            context = self.node_reference(decorator, path, reference)
            if context is None:
                return False
            value = self.namespace_expression(decorator, context)
            if value is None or value.target.target_kind != "symbol":
                return False
            target = value.target
            symbol = self.repo.definitions_by_local_key[target.symbol_key]
            if symbol.kind != "function":
                return False
            node = self.definition_nodes[(target.file_path, symbol.definition_start_byte)]
            valid = self.valid_forwarder(node, target.file_path)
            self.forward_cache[key] = valid
            return valid
        finally:
            self.forward_active.remove(key)

    def valid_forwarder(self, node, path):
        # Recognize a deliberately narrow forwarding shape, not a decorator name.
        if not isinstance(node, ast.FunctionDef) or node.decorator_list:
            return False
        args = node.args
        positional = [*args.posonlyargs, *args.args]
        if len(positional) != 1 or args.vararg or args.kwarg or args.kwonlyargs or args.defaults:
            return False
        func = positional[0].arg
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body.pop(0)
        if len(body) != 2 or not isinstance(body[0], ast.FunctionDef) or not isinstance(body[1], ast.Return):
            return False
        wrapper, returned = body
        if not isinstance(returned.value, ast.Name) or returned.value.id != wrapper.name:
            return False
        wa = wrapper.args
        if wa.posonlyargs or wa.args or wa.kwonlyargs or not wa.vararg or not wa.kwarg:
            return False
        if len({func, wa.vararg.arg, wa.kwarg.arg}) != 3:
            return False
        if len(wrapper.decorator_list) != 1:
            return False
        decor = wrapper.decorator_list[0]
        if (not isinstance(decor, ast.Call) or not isinstance(decor.func, ast.Name)
                or decor.keywords or len(decor.args) != 1
                or not isinstance(decor.args[0], ast.Name) or decor.args[0].id != func):
            return False
        if not self.stdlib_binding(decor.func.id, "functools", "wraps", path,
                                   self.locations[id(decor)][2]):
            return False
        statements = wrapper.body
        if not statements or not isinstance(statements[-1], ast.Return):
            return False
        call = statements[-1].value
        if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                or call.func.id != func or len(call.args) != 1
                or not isinstance(call.args[0], ast.Starred)
                or not isinstance(call.args[0].value, ast.Name)
                or call.args[0].value.id != wa.vararg.arg
                or len(call.keywords) != 1 or call.keywords[0].arg is not None
                or not isinstance(call.keywords[0].value, ast.Name)
                or call.keywords[0].value.id != wa.kwarg.arg):
            return False
        # Allow only simple observational print logging before delegation.
        module = self.scopes.module_scope_keys_by_path[path]
        for statement in statements[:-1]:
            if (not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call)
                    or not isinstance(statement.value.func, ast.Name)
                    or statement.value.func.id != "print"
                    or self.bindings.events_for(module, "print") or statement.value.keywords):
                return False
            for arg in statement.value.args:
                if any(isinstance(n, (ast.Call, ast.Subscript, ast.NamedExpr, ast.Lambda,
                                      ast.Await, ast.Yield, ast.YieldFrom)) for n in ast.walk(arg)):
                    return False
                if any(isinstance(n, ast.Name) and n.id != func for n in ast.walk(arg)):
                    return False
                if any(isinstance(n, ast.Attribute) and not (
                    isinstance(n.value, ast.Name) and n.value.id == func and n.attr == "__name__"
                ) for n in ast.walk(arg)):
                    return False
        return True

    def supported_definition(self, node, path, reference):
        if super().supported_definition(node, path, reference):
            return True
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        return bool(node.decorator_list) and all(
            self.forwarding_decorator(d, path, reference) for d in node.decorator_list
        )

    def namespace_expression(self, node, reference):
        if isinstance(node, ast.Name):
            outcome = self.resolve_name(node.id, reference)
        elif isinstance(node, ast.Attribute):
            owner = self.namespace_expression(node.value, reference)
            if owner is None:
                return None
            outcome = self.member(owner.target, node.attr, reference)
        else:
            return None
        if outcome.status not in {"EXACT", "INFERRED"}:
            return None
        return _Value(outcome.targets[0], "namespace", outcome.status == "INFERRED")

    def visible_events(self, name, reference):
        current = reference.site.scope_key
        module = self.scopes.module_scope_keys_by_path[reference.site.file_path]
        seen = set()
        while current is not None and current not in seen:
            seen.add(current)
            scope = self.scopes.scopes_by_key[current]
            directives = self.bindings.directives_by_scope[current]
            if name in directives.global_names and current != module:
                current = module
                continue
            if name in directives.nonlocal_names:
                current = self.enclosing_nonlocal_scope(current, name)
                continue
            if self.namespace_uncertainty(current, name, reference):
                return []
            events = self.available_events(current, name, reference)
            if events:
                return self.select_events(events, reference)
            if name in self.bindings.local_names_by_scope[current]:
                if scope.kind in {"function", "method", "lambda", "comprehension"}:
                    return []
                if scope.kind == "class":
                    current = module
                    continue
            current = scope.lookup_parent_scope_key
        return []

    def annotated_class(self, annotation, target, reference):
        if annotation is None:
            return None
        context = self.definition_context(target, reference)
        if context is None:
            return None
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                annotation = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return None
        value = self.namespace_expression(annotation, context)
        if value is None or value.target.target_kind != "symbol":
            return None
        symbol = self.repo.definitions_by_local_key[value.target.symbol_key]
        if symbol.kind != "class":
            return None
        node = self.definition_nodes[(value.target.file_path, symbol.definition_start_byte)]
        if not self.supported_definition(node, value.target.file_path, context):
            return None
        return _Value(value.target, "instance", True)

    def infer_name(self, name, reference, depth):
        events = self.visible_events(name, reference)
        if len(events) != 1:
            return None
        event = events[0]
        if event.resolution_blocker or not _path_established(event.control_path, reference.control_path):
            return None
        if event.kind == "assignment" and event.value_location:
            node = self.nodes.get(event.value_location)
            context = self.node_reference(node, event.file_path, reference) if node else None
            return self.value(node, context, depth + 1) if context else None
        if event.kind != "parameter":
            return None
        scope = self.scopes.scopes_by_key[event.scope_key]
        if scope.kind not in {"function", "method"} or scope.source_owner.target_kind != "symbol":
            return None
        symbol = self.repo.definitions_by_local_key[scope.source_owner.symbol_key]
        node = self.definition_nodes[(event.file_path, symbol.definition_start_byte)]
        if not self.supported_definition(node, event.file_path, reference):
            return None
        # Any write to a receiver/parameter anywhere in its scope blocks this inference.
        all_events = self.bindings.events_for(scope.scope_key, name)
        if len(all_events) != 1 or all_events[0].kind != "parameter":
            return None
        positional = [*node.args.posonlyargs, *node.args.args]
        if scope.kind == "method" and positional and positional[0].arg == name:
            if any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list):
                return None
            owner = self.scopes.scopes_by_key.get(scope.parent_scope_key)
            if owner is None or owner.kind != "class":
                return None
            kind = "namespace" if any(isinstance(d, ast.Name) and d.id == "classmethod"
                                      for d in node.decorator_list) else "instance"
            return _Value(owner.source_owner, kind, True)
        arguments = [*positional, *node.args.kwonlyargs]
        argument = next((a for a in arguments if a.arg == name), None)
        return self.annotated_class(argument.annotation, scope.source_owner, reference) if argument else None

    def instance_attribute(self, owner, name, reference, depth):
        symbol = self.repo.definitions_by_local_key.get(owner.target.symbol_key)
        if symbol is None or symbol.kind != "class":
            return None
        class_node = self.definition_nodes[(owner.target.file_path, symbol.definition_start_byte)]
        if not self.supported_definition(class_node, owner.target.file_path, reference):
            return None
        methods = [n for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if any(n.name in {"__getattr__", "__getattribute__", "__setattr__"} for n in methods):
            return None
        initializers = [n for n in methods if n.name == "__init__"]
        if len(initializers) != 1:
            return None
        init = initializers[0]
        if init.decorator_list:
            return None
        arguments = [*init.args.posonlyargs, *init.args.args]
        if not arguments:
            return None
        receiver = arguments[0].arg
        writes = []
        for method in methods:
            args = [*method.args.posonlyargs, *method.args.args]
            if not args:
                continue
            for node in ast.walk(method):
                if (isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del))
                        and node.attr == name and isinstance(node.value, ast.Name)
                        and node.value.id == args[0].arg):
                    writes.append(node)
        if len(writes) != 1:
            return None
        assignment = next((statement for statement in init.body if (
            isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and statement.targets[0] is writes[0]
        ) or (isinstance(statement, ast.AnnAssign) and statement.target is writes[0])), None)
        if assignment is None or assignment.value is None or writes[0].value.id != receiver:
            return None
        context = self.node_reference(assignment.value, owner.target.file_path, reference)
        value = self.value(assignment.value, context, depth + 1) if context else None
        if value is None or value.kind != "instance":
            return None
        return _Value(value.target, value.kind, True)

    def value(self, node, reference, depth=0):
        if node is None or reference is None or depth > 24:
            return None
        key = (id(node), reference.site.file_path, reference.site.scope_key, reference.site.start_byte)
        if key in self.inference_active:
            return None
        self.inference_active.add(key)
        try:
            if isinstance(node, ast.Name):
                value = self.namespace_expression(node, reference)
                if value is not None:
                    return value
                outcome = self.resolve_name(node.id, reference)
                if outcome.status == "UNRESOLVED" and outcome.rule_id == "SHADOWED_OR_UNKNOWN_BINDING":
                    return self.infer_name(node.id, reference, depth)
                return None
            if isinstance(node, ast.Attribute):
                owner = self.value(node.value, reference, depth + 1)
                if owner is None:
                    return None
                outcome = self.member(owner.target, node.attr, reference)
                if outcome.status in {"EXACT", "INFERRED"}:
                    return _Value(outcome.targets[0], "namespace",
                                  owner.inferred or outcome.status == "INFERRED")
                if owner.kind == "instance" and outcome.rule_id == "MEMBER_NOT_ESTABLISHED":
                    return self.instance_attribute(owner, node.attr, reference, depth + 1)
                return None
            if isinstance(node, ast.Call):
                callable_value = self.value(node.func, reference, depth + 1)
                if callable_value is None or callable_value.kind != "namespace":
                    return None
                target = callable_value.target
                if target.target_kind != "symbol":
                    return None
                symbol = self.repo.definitions_by_local_key[target.symbol_key]
                definition = self.definition_nodes[(target.file_path, symbol.definition_start_byte)]
                if not self.supported_definition(definition, target.file_path, reference):
                    return None
                if symbol.kind == "class":
                    return _Value(target, "instance", True)
                if isinstance(definition, ast.AsyncFunctionDef):
                    return None  # Coroutine objects are not their awaited return type.
                if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(definition)):
                    return None
                return self.annotated_class(definition.returns, target, reference)
            return None
        finally:
            self.inference_active.remove(key)

    def resolve(self, reference):
        if reference.resolution_blocker:
            return _unresolved("BLOCKED_REFERENCE", reference.resolution_blocker)
        if reference.site.reference_kind == "import":
            return self.import_target(reference.import_info, reference)
        lookup = reference.lookup
        if lookup is None or lookup.head_name is None:
            return _unresolved("DYNAMIC_LOOKUP_EXPRESSION", "Unsupported dynamic callable/base expression.")
        if not lookup.attributes:
            outcome = self.resolve_name(lookup.head_name, reference)
        else:
            expression = ast.Name(id=lookup.head_name, ctx=ast.Load())
            for attribute in lookup.attributes:
                expression = ast.Attribute(value=expression, attr=attribute, ctx=ast.Load())
            value = self.value(expression, reference)
            if value is None or value.kind != "namespace":
                return _unresolved("TYPE_OR_MEMBER_NOT_ESTABLISHED", "No unique supported receiver/member type.")
            outcome = _outcome([value.target], "TYPED_MEMBER_LOOKUP", inferred=value.inferred)
        if reference.site.reference_kind == "base_class" and any(
            t.target_kind != "symbol" or self.repo.definitions_by_local_key[t.symbol_key].kind != "class"
            for t in outcome.targets
        ):
            return _unresolved("BASE_TARGET_NOT_ESTABLISHED_AS_CLASS", "A base target must be a class.")
        return outcome


def resolve_references(collection):
    owned = collect_references(collection.binding_index)
    resolver = ReferenceResolver(owned)
    results = []
    for reference in owned.references:
        outcome = resolver.resolve(reference)
        for target in outcome.targets:
            resolver.repo.validate_target(target)
        results.append(ResolutionResult(
            reference=reference.site, status=outcome.status, targets=list(outcome.targets),
            rule_id=outcome.rule_id, reason=outcome.reason,
            confidence={"EXACT": 1.0, "INFERRED": 0.5, "AMBIGUOUS": None, "UNRESOLVED": None}[outcome.status],
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
    kinds = {"call": "CALLS", "import": "IMPORTS", "base_class": "INHERITS"}
    return tuple(AnalysisEdge(
        source=r.reference.source_owner, target=r.targets[0], kind=kinds[r.reference.reference_kind],
        status=r.status, confidence=r.confidence, reference_key=r.reference.reference_key,
    ) for r in results if r.status in {"EXACT", "INFERRED"})
