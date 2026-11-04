from reposcope.graph.builder import (
    build_graph_plan,
    resolution_report,
)
from reposcope.parsing.python_parser import parse_python


def parse(source, path="api.py"):
    return parse_python(
        source.encode("utf-8"),
        file_path=path,
    )


def test_route_and_model_usage_are_linked_in_graph_plan():
    parsed = parse(
        'from fastapi import FastAPI\n'
        'from sqlmodel import SQLModel\n'
        'app = FastAPI()\n'
        'class User(SQLModel, table=True):\n'
        '    id: int\n'
        '@app.post("/users")\n'
        'def create_user():\n'
        '    return User()\n'
    )

    plan = build_graph_plan([parsed])

    module = next(
        node for node in plan.nodes
        if node.kind == "module"
    )
    endpoint = next(
        node for node in plan.nodes
        if node.kind == "endpoint"
    )
    handler = next(
        node for node in plan.nodes
        if node.kind == "function"
        and node.name == "create_user"
    )
    model = next(
        node for node in plan.nodes
        if node.kind == "class"
        and node.name == "User"
    )

    relationships = {
        (edge.source_key, edge.target_key, edge.kind)
        for edge in plan.edges
    }

    assert endpoint.name == "POST /users"
    assert (
        module.key,
        endpoint.key,
        "EXPOSES",
    ) in relationships
    assert (
        endpoint.key,
        handler.key,
        "CALLS",
    ) in relationships
    assert (
        handler.key,
        model.key,
        "USES",
    ) in relationships

    keys = {node.key for node in plan.nodes}

    assert all(
        edge.source_key in keys and edge.target_key in keys
        for edge in plan.edges
    )


def test_multiple_model_calls_merge_with_multiple_evidence_keys():
    parsed = parse(
        'from sqlmodel import SQLModel\n'
        'class User(SQLModel, table=True):\n'
        '    id: int\n'
        'def create_users():\n'
        '    first = User()\n'
        '    second = User()\n'
        '    return first, second\n',
        path="models.py",
    )

    plan = build_graph_plan([parsed])
    uses = [
        edge for edge in plan.edges
        if edge.kind == "USES"
    ]

    assert len(uses) == 1
    assert len(uses[0].reference_keys) == 2


def test_report_preserves_detector_gaps_and_endpoint_metadata():
    parsed = parse(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n'
        'PATH = "/dynamic"\n'
        '@app.get(PATH)\n'
        'def dynamic():\n'
        '    return []\n'
        '@app.get("/health")\n'
        'def health():\n'
        '    return "ok"\n'
    )

    plan = build_graph_plan([parsed])
    report = resolution_report(plan)

    assert len(plan.detection.endpoints) == 1
    assert len(plan.detection.gaps) == 1

    assert (
        report["detection"]["endpoints"][0]["path"]
        == "/health"
    )
    assert (
        report["detection"]["gaps"][0]["rule_id"]
        == "routes.unsupported"
    )


def test_same_route_registered_twice_has_distinct_endpoint_nodes():
    parsed = parse(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n'
        '@app.get("/users")\n'
        '@app.get("/users")\n'
        'def users():\n'
        '    return []\n'
    )

    plan = build_graph_plan([parsed])
    endpoints = [
        node for node in plan.nodes
        if node.kind == "endpoint"
    ]

    assert len(endpoints) == 2
    assert len({node.key for node in endpoints}) == 2
    assert len({node.qualname for node in endpoints}) == 2


def test_graph_without_frameworks_has_no_derived_records():
    parsed = parse(
        'def health():\n'
        '    return "ok"\n'
    )

    plan = build_graph_plan([parsed])

    assert plan.detection.endpoints == ()
    assert plan.detection.models == ()
    assert plan.detection.edges == ()
    assert plan.detection.gaps == ()
    assert not any(
        node.kind == "endpoint"
        for node in plan.nodes
    )