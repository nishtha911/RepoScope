from reposcope.parsing.detectors import (
    derive_model_uses,
    detect_models,
)
from reposcope.parsing.python_parser import parse_python
from reposcope.parsing.resolver_pipeline import analyze_python_files


def analyze_sources(sources):
    parsed_files = [
        parse_python(
            source.encode("utf-8"),
            file_path=path,
        )
        for path, source in sources.items()
    ]

    models = tuple(
        model
        for parsed in parsed_files
        for model in detect_models(parsed).models
    )

    analysis = analyze_python_files(parsed_files)
    usages = derive_model_uses(analysis.results, models)

    return parsed_files, usages


def symbol_key(parsed_files, path, name):
    return next(
        symbol.local_key
        for parsed in parsed_files
        if parsed.file_path == path
        for symbol in parsed.symbols
        if symbol.name == name
    )


def test_local_model_construction_emits_uses():
    parsed_files, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class User(SQLModel, table=True):\n'
                '    id: int\n'
                'def create_user():\n'
                '    return User()\n'
            ),
        }
    )

    assert len(result.edges) == 1

    edge = result.edges[0]

    assert edge.kind == "USES"
    assert edge.source_key == symbol_key(
        parsed_files,
        "models.py",
        "create_user",
    )
    assert edge.target_key == symbol_key(
        parsed_files,
        "models.py",
        "User",
    )


def test_imported_model_alias_emits_uses():
    parsed_files, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class User(SQLModel, table=True):\n'
                '    id: int\n'
            ),
            "service.py": (
                'from models import User as Account\n'
                'def create_user():\n'
                '    return Account()\n'
            ),
        }
    )

    assert len(result.edges) == 1

    edge = result.edges[0]

    assert edge.kind == "USES"
    assert edge.source_key == symbol_key(
        parsed_files,
        "service.py",
        "create_user",
    )
    assert edge.target_key == symbol_key(
        parsed_files,
        "models.py",
        "User",
    )


def test_non_table_schema_does_not_emit_uses():
    _, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class UserSchema(SQLModel):\n'
                '    name: str\n'
                'def create_schema():\n'
                '    return UserSchema()\n'
            ),
        }
    )

    assert result.edges == ()


def test_parameter_shadowing_does_not_emit_model_uses():
    _, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class User(SQLModel, table=True):\n'
                '    id: int\n'
                'def create_user(User):\n'
                '    return User()\n'
            ),
        }
    )

    assert result.edges == ()


def test_import_without_construction_does_not_emit_uses():
    _, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class User(SQLModel, table=True):\n'
                '    id: int\n'
            ),
            "service.py": (
                'from models import User\n'
                'def health():\n'
                '    return "ok"\n'
            ),
        }
    )

    assert result.edges == ()


def test_usage_evidence_matches_source():
    parsed_files, result = analyze_sources(
        {
            "models.py": (
                'from sqlmodel import SQLModel\n'
                'class User(SQLModel, table=True):\n'
                '    id: int\n'
                'def create_user():\n'
                '    return User()\n'
            ),
        }
    )

    assert len(result.edges) == 1

    evidence = result.edges[0].evidence
    parsed = parsed_files[0]
    buffer = parsed.source_text.encode("utf-8")

    assert (
        buffer[evidence.start_byte:evidence.end_byte].decode("utf-8")
        == evidence.expression
    )
    assert evidence.rule_id == "models.resolved_constructor_use"


def test_imported_unrelated_table_keyword_class_remains_unresolved():
    sources = {
        "models.py": (
            'class Base:\n'
            '    pass\n'
            'class User(Base, table=True):\n'
            '    id: int\n'
        ),
        "service.py": (
            'from models import User as Account\n'
            'def create_user():\n'
            '    return Account()\n'
        ),
    }

    parsed_files = [
        parse_python(
            source.encode("utf-8"),
            file_path=path,
        )
        for path, source in sources.items()
    ]

    detected_models = [
        model
        for parsed in parsed_files
        for model in detect_models(parsed).models
    ]

    assert detected_models == []

    analysis = analyze_python_files(parsed_files)

    calls = [
        result
        for result in analysis.results
        if result.reference.file_path == "service.py"
        and result.reference.reference_kind == "call"
        and result.reference.expression == "Account()"
    ]

    assert len(calls) == 1
    assert calls[0].status == "UNRESOLVED"
    assert calls[0].targets == []

    usages = derive_model_uses(
        analysis.results,
        detected_models,
    )

    assert usages.edges == ()


def test_imported_sqlmodel_with_custom_metaclass_remains_unresolved():
    sources = {
        "models.py": (
            'from sqlmodel import SQLModel\n'
            'class CustomMeta(type):\n'
            '    pass\n'
            'class User(SQLModel, table=True, metaclass=CustomMeta):\n'
            '    id: int\n'
        ),
        "service.py": (
            'from models import User as Account\n'
            'def create_user():\n'
            '    return Account()\n'
        ),
    }

    parsed_files = [
        parse_python(
            source.encode("utf-8"),
            file_path=path,
        )
        for path, source in sources.items()
    ]

    detected_models = [
        model
        for parsed in parsed_files
        for model in detect_models(parsed).models
    ]

    assert detected_models == []

    analysis = analyze_python_files(parsed_files)

    calls = [
        result
        for result in analysis.results
        if result.reference.file_path == "service.py"
        and result.reference.reference_kind == "call"
        and result.reference.expression == "Account()"
    ]

    assert len(calls) == 1
    assert calls[0].status == "UNRESOLVED"
    assert calls[0].targets == []

    usages = derive_model_uses(
        analysis.results,
        detected_models,
    )

    assert usages.edges == ()