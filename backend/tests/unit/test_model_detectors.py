from reposcope.parsing.detectors import detect_models
from reposcope.parsing.python_parser import parse_python


def detect(source):
    parsed = parse_python(
        source.encode("utf-8"),
        file_path="models.py",
    )
    return parsed, detect_models(parsed)


def model_names(parsed, result):
    names = {
        symbol.local_key: symbol.name
        for symbol in parsed.symbols
    }
    return [names[model.symbol_key] for model in result.models]


def test_sqlmodel_table_is_detected_but_schema_is_not():
    parsed, result = detect(
        'from sqlmodel import SQLModel\n'
        'class UserSchema(SQLModel):\n'
        '    name: str\n'
        'class User(SQLModel, table=True):\n'
        '    id: int\n'
    )

    assert model_names(parsed, result) == ["User"]
    assert result.models[0].framework == "sqlmodel"
    assert result.edges == ()


def test_sqlmodel_alias_and_local_schema_base():
    parsed, result = detect(
        'from sqlmodel import SQLModel as Model\n'
        'class UserBase(Model):\n'
        '    name: str\n'
        'class User(UserBase, table=True):\n'
        '    id: int\n'
    )

    assert model_names(parsed, result) == ["User"]


def test_sqlalchemy_declarative_base_factory():
    parsed, result = detect(
        'from sqlalchemy.orm import declarative_base as make_base\n'
        'Base = make_base()\n'
        'class User(Base):\n'
        '    __tablename__ = "users"\n'
        '    id: int\n'
    )

    assert model_names(parsed, result) == ["User"]
    assert result.models[0].framework == "sqlalchemy"


def test_sqlalchemy_declarative_base_class():
    parsed, result = detect(
        'from sqlalchemy.orm import DeclarativeBase\n'
        'class Base(DeclarativeBase):\n'
        '    pass\n'
        'class User(Base):\n'
        '    __tablename__ = "users"\n'
        '    id: int\n'
    )

    assert model_names(parsed, result) == ["User"]


def test_sqlalchemy_abstract_class_is_not_a_table_model():
    parsed, result = detect(
        'from sqlalchemy.orm import DeclarativeBase\n'
        'class Base(DeclarativeBase):\n'
        '    pass\n'
        'class AbstractEntity(Base):\n'
        '    __abstract__ = True\n'
        'class User(AbstractEntity):\n'
        '    __tablename__ = "users"\n'
        '    id: int\n'
    )

    assert model_names(parsed, result) == ["User"]


def test_unrelated_base_and_tablename_do_not_make_a_model():
    _, result = detect(
        'class Base:\n'
        '    pass\n'
        'class User(Base):\n'
        '    __tablename__ = "users"\n'
    )

    assert result.models == ()


def test_shadowed_sqlmodel_import_does_not_make_a_model():
    _, result = detect(
        'from sqlmodel import SQLModel\n'
        'SQLModel = other_base\n'
        'class User(SQLModel, table=True):\n'
        '    id: int\n'
    )

    assert result.models == ()


def test_dynamic_table_setting_produces_gap():
    _, result = detect(
        'from sqlmodel import SQLModel\n'
        'IS_TABLE = True\n'
        'class User(SQLModel, table=IS_TABLE):\n'
        '    id: int\n'
    )

    assert result.models == ()
    assert len(result.gaps) == 1
    assert result.gaps[0].rule_id == "models.unsupported"


def test_model_evidence_matches_source_bytes():
    parsed, result = detect(
        'from sqlmodel import SQLModel\n'
        'class User(SQLModel, table=True):\n'
        '    name: str = "café"\n'
    )

    assert len(result.models) == 1

    evidence = result.models[0].evidence
    buffer = parsed.source_text.encode("utf-8")

    assert (
        buffer[evidence.start_byte:evidence.end_byte].decode("utf-8")
        == evidence.expression
    )