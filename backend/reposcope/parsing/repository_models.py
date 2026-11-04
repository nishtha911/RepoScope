"""Repository-wide model classification using resolved inheritance.

The module-local detector remains independent of the resolver.
This module consumes existing resolution results; it never runs resolution.
"""

import ast

from reposcope.contracts.detection import (
    DetectedModel,
    DetectionResult,
)
from reposcope.parsing.detectors import (
    _SQLALCHEMY_BASE_FACTORIES,
    _class_assignment,
    _evidence,
    _literal,
    _module_bindings,
    _resolve_import,
    detect_models,
)


def detect_repository_models(parsed_files, resolution_results):
    """Propagate framework families through exact base-class resolutions.

    Supports imported project bases and local declarative_base() factories.
    SQLAlchemy tables require a literal __tablename__.
    SQLModel tables require an explicit literal table=True.

    Does not import or execute analyzed source.
    """
    records = {}
    families = {}
    detected = {}
    gaps = []

    for parsed in parsed_files:
        local = detect_models(parsed)
        gaps.extend(local.gaps)

        for model in local.models:
            detected[model.symbol_key] = model
            families[model.symbol_key] = model.framework

        try:
            tree = ast.parse(parsed.source_text)
        except SyntaxError:
            continue

        writes, imports = _module_bindings(tree)
        symbols = {
            (symbol.start_line, symbol.name): symbol
            for symbol in parsed.symbols
            if symbol.kind == "class"
            and symbol.parent_key is None
        }

        factories = {}

        for statement in tree.body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, ast.Call)
            ):
                name = statement.targets[0].id
                call = statement.value

                if (
                    writes[name] == 1
                    and not call.args
                    and not call.keywords
                    and _resolve_import(call.func, imports)
                    in _SQLALCHEMY_BASE_FACTORIES
                ):
                    factories[name] = statement.end_lineno

            if not isinstance(statement, ast.ClassDef):
                continue

            symbol = symbols.get(
                (statement.lineno, statement.name)
            )

            if (
                symbol is None
                or writes[statement.name] != 1
                or statement.decorator_list
            ):
                continue

            # Custom metaclasses, **kwargs, and other class keywords
            # remain outside this detector's supported scope.
            if any(
                keyword.arg != "table"
                for keyword in statement.keywords
            ):
                continue

            table_keywords = [
                keyword
                for keyword in statement.keywords
                if keyword.arg == "table"
            ]

            if len(table_keywords) > 1:
                continue

            if table_keywords and not (
                isinstance(
                    table_keywords[0].value,
                    ast.Constant,
                )
                and type(table_keywords[0].value.value) is bool
            ):
                continue

            abstract = _class_assignment(
                statement,
                "__abstract__",
            )

            if abstract is not None and not (
                isinstance(abstract, ast.Constant)
                and type(abstract.value) is bool
            ):
                continue

            seeds = set()
            declares_sqlalchemy_base = False

            for base in statement.bases:
                imported = _resolve_import(base, imports)

                if imported == "sqlmodel.SQLModel":
                    seeds.add("sqlmodel")

                elif imported == "sqlalchemy.orm.DeclarativeBase":
                    seeds.add("sqlalchemy")
                    declares_sqlalchemy_base = True

                elif (
                    isinstance(base, ast.Name)
                    and base.id in factories
                    and factories[base.id] < statement.lineno
                ):
                    seeds.add("sqlalchemy")

            records[symbol.local_key] = (
                parsed,
                statement,
                seeds,
                declares_sqlalchemy_base,
            )

    parents = {}

    for result in resolution_results:
        reference = result.reference

        if (
            reference.reference_kind != "base_class"
            or reference.source_owner.target_kind != "symbol"
            or result.status != "EXACT"
            or len(result.targets) != 1
        ):
            continue

        target = result.targets[0]

        if target.target_kind != "symbol":
            continue

        owner_key = reference.source_owner.symbol_key

        parents.setdefault(owner_key, set()).add(
            target.symbol_key
        )

    # Compute all reachable family candidates before accepting a class.
    # This avoids choosing a family merely because it appeared first.
    candidates = {
        key: set(record[2])
        for key, record in records.items()
    }

    for key, framework in families.items():
        if key in candidates:
            candidates[key].add(framework)

    changed = True

    while changed:
        changed = False

        for key in records:
            inherited = set()

            for parent in parents.get(key, ()):
                inherited.update(candidates.get(parent, ()))

            before = len(candidates[key])
            candidates[key].update(inherited)

            if len(candidates[key]) != before:
                changed = True

    for key, record in records.items():
        parsed, node, _, declares_sqlalchemy_base = record
        possible = candidates[key]

        if len(possible) != 1:
            # Do not retain an earlier local classification if the
            # repository-level evidence establishes a family conflict.
            detected.pop(key, None)
            continue

        framework = next(iter(possible))

        if framework == "sqlmodel":
            table = next(
                (
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "table"
                ),
                None,
            )
            is_table = (
                isinstance(table, ast.Constant)
                and table.value is True
            )

        else:
            # SQLAlchemy's supported styles here have no class keywords.
            if node.keywords or declares_sqlalchemy_base:
                detected.pop(key, None)
                continue

            abstract = _class_assignment(node, "__abstract__")
            table_name = _literal(
                _class_assignment(node, "__tablename__")
            )

            is_table = (
                not (
                    isinstance(abstract, ast.Constant)
                    and abstract.value is True
                )
                and isinstance(table_name, str)
                and bool(table_name)
            )

        if not is_table:
            detected.pop(key, None)
            continue

        detected[key] = DetectedModel(
            symbol_key=key,
            framework=framework,
            evidence=_evidence(
                parsed,
                node,
                f"{framework}.repository_table_model",
            ),
        )

    return DetectionResult(
        models=tuple(
            detected[key]
            for key in sorted(detected)
        ),
        gaps=tuple(gaps),
    )