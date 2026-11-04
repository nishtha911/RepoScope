"""Conservative static detectors for framework-derived graph edges."""

import ast
from collections import Counter

from reposcope.contracts.detection import (
    DerivedEdge,
    DetectedEndpoint,
    DetectedModel,
    DetectionEvidence,
    DetectionGap,
    DetectionResult,
    make_endpoint_key,
)
from reposcope.contracts.parsing import ParsedFile


_CONSTRUCTORS = {
    "fastapi.FastAPI": "fastapi",
    "fastapi.APIRouter": "fastapi",
    "flask.Flask": "flask",
    "flask.Blueprint": "flask",
}

_HTTP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "TRACE",
}

_SQLALCHEMY_BASE_FACTORIES = {
    "sqlalchemy.orm.declarative_base",
    "sqlalchemy.ext.declarative.declarative_base",
}


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None

    return None


def _module_bindings(tree):
    """Reject names written more than once in this module.

    This intentionally favors missed edges over incorrect framework claims.
    Nested scopes are not traversed.
    """
    writes = Counter()
    imports = {}

    def visit_statement(node):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                writes[name] += 1
                imports[name] = (
                    alias.name
                    if alias.asname
                    else alias.name.split(".")[0]
                )
            return

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue

                name = alias.asname or alias.name
                writes[name] += 1

                if node.level == 0 and node.module:
                    imports[name] = f"{node.module}.{alias.name}"

            return

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            writes[node.name] += 1
            return

        if isinstance(node, ast.Name) and isinstance(
            node.ctx,
            (ast.Store, ast.Del),
        ):
            writes[node.id] += 1

        for child in ast.iter_child_nodes(node):
            visit_statement(child)

    for statement in tree.body:
        visit_statement(statement)

    imports = {
        name: target
        for name, target in imports.items()
        if writes[name] == 1
    }

    return writes, imports


def _resolve_import(node, imports):
    dotted = _dotted_name(node)
    if not dotted:
        return None

    head, separator, tail = dotted.partition(".")
    target = imports.get(head)

    if target is None:
        return None

    return f"{target}.{tail}" if separator else target


def _literal(node):
    if node is None:
        return None

    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return None


def _keyword(call, name):
    return next(
        (
            keyword.value
            for keyword in call.keywords
            if keyword.arg == name
        ),
        None,
    )


def _route_methods(call, framework):
    name = call.func.attr
    upper = name.upper()

    if upper in _HTTP_METHODS:
        return (upper,)

    generic = (
        framework == "fastapi" and name == "api_route"
    ) or (
        framework == "flask" and name == "route"
    )

    if not generic:
        return None

    methods_node = _keyword(call, "methods")
    if methods_node is None:
        return ("GET",)

    methods = _literal(methods_node)

    if (
        not isinstance(methods, (list, tuple, set))
        or not methods
        or any(
            not isinstance(method, str)
            or method.upper() not in _HTTP_METHODS
            for method in methods
        )
    ):
        return None

    return tuple(sorted({method.upper() for method in methods}))


def _evidence(parsed, node, rule_id):
    buffer = parsed.source_text.encode("utf-8")
    lines = buffer.splitlines(keepends=True)

    start = (
        sum(map(len, lines[:node.lineno - 1]))
        + node.col_offset
    )
    end = (
        sum(map(len, lines[:node.end_lineno - 1]))
        + node.end_col_offset
    )

    return DetectionEvidence(
        file_path=parsed.file_path,
        start_line=node.lineno,
        end_line=node.end_lineno,
        start_byte=start,
        end_byte=end,
        expression=buffer[start:end].decode("utf-8"),
        rule_id=rule_id,
    )


def detect_routes(
    parsed: ParsedFile,
    *,
    module_key: str,
) -> DetectionResult:
    """Detect direct module-level registrations.

    Supports imported constructor aliases and literal decorator paths/methods.
    Does not resolve imported receivers, factories, nested handlers, mounted
    paths, or application/blueprint registration. Paths remain declaration-local.
    """
    try:
        tree = ast.parse(parsed.source_text)
    except SyntaxError as exc:
        return DetectionResult(
            gaps=(
                DetectionGap(
                    file_path=parsed.file_path,
                    start_line=exc.lineno or 1,
                    rule_id="routes.ast_parse",
                    reason=(
                        "Source is not supported by the Python AST parser"
                    ),
                ),
            ),
        )

    writes, imports = _module_bindings(tree)
    receivers = {}

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                continue

            target = statement.targets[0]
            value = statement.value

        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
            value = statement.value

        else:
            continue

        if (
            not isinstance(target, ast.Name)
            or writes[target.id] != 1
            or not isinstance(value, ast.Call)
            or any(
                keyword.arg is None
                for keyword in value.keywords
            )
        ):
            continue

        constructor = _resolve_import(value.func, imports)
        framework = _CONSTRUCTORS.get(constructor)

        if framework:
            receivers[target.id] = (
                framework,
                statement.end_lineno,
            )

    symbols = {
        (symbol.start_line, symbol.name): symbol
        for symbol in parsed.symbols
        if symbol.kind == "function" and symbol.parent_key is None
    }

    endpoints = []
    edges = []
    gaps = []

    def gap(node, reason):
        gaps.append(
            DetectionGap(
                file_path=parsed.file_path,
                start_line=node.lineno,
                rule_id="routes.unsupported",
                reason=reason,
            )
        )

    for statement in tree.body:
        if not isinstance(
            statement,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        for decorator in statement.decorator_list:
            if (
                not isinstance(decorator, ast.Call)
                or not isinstance(decorator.func, ast.Attribute)
                or not isinstance(decorator.func.value, ast.Name)
            ):
                continue

            receiver = decorator.func.value.id
            registration = receivers.get(receiver)

            if registration is None:
                continue

            framework, receiver_line = registration

            if receiver_line >= decorator.lineno:
                gap(
                    decorator,
                    "Receiver is not defined before the decorator",
                )
                continue

            route_name = decorator.func.attr
            supported_name = (
                route_name.upper() in _HTTP_METHODS
                or route_name
                == (
                    "api_route"
                    if framework == "fastapi"
                    else "route"
                )
            )

            if not supported_name:
                continue

            if any(
                keyword.arg is None
                for keyword in decorator.keywords
            ):
                gap(
                    decorator,
                    "Dynamic decorator keyword arguments",
                )
                continue

            path_keyword = (
                "path"
                if framework == "fastapi"
                else "rule"
            )
            path_node = (
                decorator.args[0]
                if decorator.args
                else _keyword(decorator, path_keyword)
            )

            path = _literal(path_node)
            methods = _route_methods(decorator, framework)

            if not isinstance(path, str) or methods is None:
                gap(
                    decorator,
                    "Route path or methods are not supported literals",
                )
                continue

            handler = symbols.get(
                (statement.lineno, statement.name)
            )

            if handler is None:
                gap(
                    decorator,
                    "Handler does not match an existing parser symbol",
                )
                continue

            evidence = _evidence(
                parsed,
                decorator,
                f"{framework}.route_decorator",
            )

            for method in methods:
                key = make_endpoint_key(
                    parsed.file_path,
                    evidence.start_byte,
                    method,
                )

                endpoints.append(
                    DetectedEndpoint(
                        key=key,
                        module_key=module_key,
                        handler_key=handler.local_key,
                        framework=framework,
                        receiver=receiver,
                        method=method,
                        path=path,
                        evidence=evidence,
                    )
                )

                edges.extend(
                    (
                        DerivedEdge(
                            source_key=module_key,
                            target_key=key,
                            kind="EXPOSES",
                            confidence=1.0,
                            evidence=evidence,
                        ),
                        DerivedEdge(
                            source_key=key,
                            target_key=handler.local_key,
                            kind="CALLS",
                            confidence=1.0,
                            evidence=evidence,
                        ),
                    )
                )

    return DetectionResult(
        endpoints=tuple(endpoints),
        edges=tuple(edges),
        gaps=tuple(gaps),
    )


def _class_assignment(node, name):
    """Return the last direct assignment to a class attribute."""
    value = None

    for statement in node.body:
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == name
                for target in statement.targets
            ):
                value = statement.value

        elif isinstance(statement, ast.AnnAssign):
            if (
                isinstance(statement.target, ast.Name)
                and statement.target.id == name
            ):
                value = statement.value

    return value


def detect_models(parsed: ParsedFile) -> DetectionResult:
    """Detect supported, module-local declarative table models.

    Supports:
    - SQLModel inheritance with an explicit literal table=True.
    - SQLAlchemy declarative_base() with a literal __tablename__.
    - SQLAlchemy DeclarativeBase with a literal __tablename__.
    - Local abstract/schema base classes in those hierarchies.

    Does not resolve imported project bases, registry mappings, dynamic
    table names, __table__ mappings, or single-table inheritance.
    """
    try:
        tree = ast.parse(parsed.source_text)
    except SyntaxError as exc:
        return DetectionResult(
            gaps=(
                DetectionGap(
                    file_path=parsed.file_path,
                    start_line=exc.lineno or 1,
                    rule_id="models.ast_parse",
                    reason=(
                        "Source is not supported by the Python AST parser"
                    ),
                ),
            ),
        )

    writes, imports = _module_bindings(tree)

    symbols = {
        (symbol.start_line, symbol.name): symbol
        for symbol in parsed.symbols
        if symbol.kind == "class" and symbol.parent_key is None
    }

    # name -> (framework family, definition end line)
    families = {}
    models = []
    gaps = []

    def gap(node, reason):
        gaps.append(
            DetectionGap(
                file_path=parsed.file_path,
                start_line=node.lineno,
                rule_id="models.unsupported",
                reason=reason,
            )
        )

    def family_for_base(base, class_line):
        imported = _resolve_import(base, imports)

        if imported == "sqlmodel.SQLModel":
            return "sqlmodel"

        if imported == "sqlalchemy.orm.DeclarativeBase":
            return "sqlalchemy_root"

        if isinstance(base, ast.Name):
            known = families.get(base.id)

            if known is not None and known[1] < class_line:
                return known[0]

        return None

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                continue

            target = statement.targets[0]
            value = statement.value

            if (
                isinstance(target, ast.Name)
                and writes[target.id] == 1
                and isinstance(value, ast.Call)
                and _resolve_import(value.func, imports)
                in _SQLALCHEMY_BASE_FACTORIES
            ):
                if value.args or value.keywords:
                    gap(
                        statement,
                        "Customized declarative_base arguments are unsupported",
                    )
                else:
                    families[target.id] = (
                        "sqlalchemy",
                        statement.end_lineno,
                    )

            continue

        if not isinstance(statement, ast.ClassDef):
            continue

        if writes[statement.name] != 1:
            continue

        base_families = {
            family
            for base in statement.bases
            if (
                family := family_for_base(
                    base,
                    statement.lineno,
                )
            ) is not None
        }

        if not base_families:
            continue

        if statement.decorator_list or any(
            keyword.arg is None or keyword.arg == "metaclass"
            for keyword in statement.keywords
        ):
            gap(
                statement,
                "Decorated or dynamic model classes are unsupported",
            )
            continue

        normalized_families = {
            (
                "sqlalchemy"
                if family == "sqlalchemy_root"
                else family
            )
            for family in base_families
        }

        if len(normalized_families) != 1:
            gap(
                statement,
                "Multiple framework base families are unsupported",
            )
            continue

        framework = next(iter(normalized_families))

        # A direct DeclarativeBase subclass declares a base, not a table.
        if "sqlalchemy_root" in base_families:
            families[statement.name] = (
                "sqlalchemy",
                statement.end_lineno,
            )
            continue

        if framework == "sqlmodel":
            table_node = next(
                (
                    keyword.value
                    for keyword in statement.keywords
                    if keyword.arg == "table"
                ),
                None,
            )

            if table_node is not None and not (
                isinstance(table_node, ast.Constant)
                and type(table_node.value) is bool
            ):
                gap(
                    statement,
                    "SQLModel table setting is not a literal boolean",
                )
                continue

            families[statement.name] = (
                framework,
                statement.end_lineno,
            )

            is_table = (
                isinstance(table_node, ast.Constant)
                and table_node.value is True
            )

        else:
            abstract_node = _class_assignment(
                statement,
                "__abstract__",
            )

            if abstract_node is not None and not (
                isinstance(abstract_node, ast.Constant)
                and type(abstract_node.value) is bool
            ):
                gap(
                    statement,
                    "SQLAlchemy abstract setting is dynamic",
                )
                continue

            families[statement.name] = (
                framework,
                statement.end_lineno,
            )

            if (
                isinstance(abstract_node, ast.Constant)
                and abstract_node.value is True
            ):
                continue

            table_name = _literal(
                _class_assignment(statement, "__tablename__")
            )

            is_table = (
                isinstance(table_name, str)
                and bool(table_name)
            )

            if not is_table:
                gap(
                    statement,
                    "SQLAlchemy class has no supported literal table name",
                )

        if not is_table:
            continue

        symbol = symbols.get(
            (statement.lineno, statement.name)
        )

        if symbol is None:
            gap(
                statement,
                "Model does not match an existing parser symbol",
            )
            continue

        models.append(
            DetectedModel(
                symbol_key=symbol.local_key,
                framework=framework,
                evidence=_evidence(
                    parsed,
                    statement,
                    f"{framework}.table_model",
                ),
            )
        )

    return DetectionResult(
        models=tuple(models),
        gaps=tuple(gaps),
    )


def derive_model_uses(
    resolution_results,
    models,
) -> DetectionResult:
    """Derive USES edges from resolved calls to known model classes.

    Only EXACT and INFERRED call resolutions are eligible. Model identity
    comes from DetectedModel.symbol_key, not a class-name comparison.

    This rule covers model construction. It does not cover model names
    passed as arguments to select(), session.query(), or session.get().
    """
    model_keys = {
        model.symbol_key
        for model in models
    }
    edges = []

    for result in resolution_results:
        reference = result.reference

        if reference.reference_kind != "call":
            continue

        if result.status not in {"EXACT", "INFERRED"}:
            continue

        if len(result.targets) != 1:
            continue

        target = result.targets[0]

        if (
            target.target_kind != "symbol"
            or target.symbol_key not in model_keys
        ):
            continue

        owner = reference.source_owner
        source_key = (
            owner.module_key
            if owner.target_kind == "module"
            else owner.symbol_key
        )

        if source_key is None:
            continue

        evidence = DetectionEvidence(
            file_path=reference.file_path,
            start_line=reference.start_line,
            end_line=reference.end_line,
            start_byte=reference.start_byte,
            end_byte=reference.end_byte,
            expression=reference.expression,
            rule_id="models.resolved_constructor_use",
        )

        edges.append(
            DerivedEdge(
                source_key=source_key,
                target_key=target.symbol_key,
                kind="USES",
                confidence=result.confidence,
                evidence=evidence,
            )
        )

    return DetectionResult(edges=tuple(edges))