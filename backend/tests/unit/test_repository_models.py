from reposcope.graph.builder import build_graph_plan
from reposcope.parsing.python_parser import parse_python


def build(sources):
    return build_graph_plan(
        [
            parse_python(
                source.encode("utf-8"),
                file_path=path,
            )
            for path, source in sources.items()
        ]
    )


def detected_names(plan):
    names = {
        node.key: node.name
        for node in plan.nodes
    }

    return {
        names[model.symbol_key]
        for model in plan.detection.models
    }


def test_imported_sqlalchemy_base_and_model_constructor_usage():
    plan = build(
        {
            "base.py": (
                'from sqlalchemy.orm import DeclarativeBase\n'
                'class Base(DeclarativeBase):\n'
                '    pass\n'
            ),
            "models.py": (
                'from base import Base as ProjectBase\n'
                'class User(ProjectBase):\n'
                '    __tablename__ = "users"\n'
                '    id: int\n'
            ),
            "service.py": (
                'from models import User as Account\n'
                'def create_user():\n'
                '    return Account()\n'
            ),
        }
    )

    assert detected_names(plan) == {"User"}

    handler = next(
        node
        for node in plan.nodes
        if node.kind == "function"
        and node.name == "create_user"
    )
    model = next(
        node
        for node in plan.nodes
        if node.kind == "class"
        and node.name == "User"
    )

    assert any(
        edge.kind == "USES"
        and edge.source_key == handler.key
        and edge.target_key == model.key
        for edge in plan.edges
    )


def test_imported_abstract_sqlalchemy_base():
    plan = build(
        {
            "base.py": (
                'from sqlalchemy.orm import DeclarativeBase\n'
                'class Base(DeclarativeBase):\n'
                '    pass\n'
                'class AbstractEntity(Base):\n'
                '    __abstract__ = True\n'
            ),
            "models.py": (
                'from base import AbstractEntity\n'
                'class User(AbstractEntity):\n'
                '    __tablename__ = "users"\n'
                '    id: int\n'
            ),
        }
    )

    assert detected_names(plan) == {"User"}


def test_imported_unrelated_base_does_not_make_table_model():
    plan = build(
        {
            "base.py": (
                'class Base:\n'
                '    pass\n'
            ),
            "models.py": (
                'from base import Base\n'
                'class User(Base):\n'
                '    __tablename__ = "users"\n'
            ),
        }
    )

    assert detected_names(plan) == set()


def test_imported_sqlmodel_schema_base_identifies_table():
    plan = build(
        {
            "schemas.py": (
                'from sqlmodel import SQLModel\n'
                'class UserBase(SQLModel):\n'
                '    name: str\n'
            ),
            "models.py": (
                'from schemas import UserBase\n'
                'class User(UserBase, table=True):\n'
                '    id: int\n'
            ),
        }
    )

    assert detected_names(plan) == {"User"}


def test_imported_sqlmodel_table_with_imported_schema_emits_uses():
    plan = build(
        {
            "schemas.py": (
                'from sqlmodel import SQLModel\n'
                'class UserBase(SQLModel):\n'
                '    name: str\n'
            ),
            "models.py": (
                'from schemas import UserBase\n'
                'class User(UserBase, table=True):\n'
                '    id: int\n'
            ),
            "service.py": (
                'from models import User as Account\n'
                'def create_user():\n'
                '    return Account()\n'
            ),
        }
    )

    assert detected_names(plan) == {"User"}

    handler = next(
        node
        for node in plan.nodes
        if node.kind == "function"
        and node.name == "create_user"
    )
    model = next(
        node
        for node in plan.nodes
        if node.kind == "class"
        and node.name == "User"
    )

    assert any(
        edge.kind == "USES"
        and edge.source_key == handler.key
        and edge.target_key == model.key
        for edge in plan.edges
    )

    calls = [
        result
        for result in plan.results
        if result.reference.file_path == "service.py"
        and result.reference.reference_kind == "call"
        and result.reference.expression == "Account()"
    ]

    assert len(calls) == 1
    assert calls[0].status == "EXACT"
    assert len(calls[0].targets) == 1
    assert calls[0].targets[0].symbol_key == model.key