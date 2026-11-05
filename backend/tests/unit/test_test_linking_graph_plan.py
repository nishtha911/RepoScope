from reposcope.graph.builder import (
    build_graph_plan,
    resolution_report,
)
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


def test_tested_by_direction_and_report_evidence():
    plan = build(
        {
            "users.py": (
                "def create_user():\n"
                "    return 1\n"
            ),
            "tests/test_users.py": (
                "from users import create_user\n"
                "def test_create_user():\n"
                "    assert create_user() == 1\n"
            ),
        }
    )

    assert len(plan.test_linking.links) == 1
    link = plan.test_linking.links[0]

    edges = [
        edge
        for edge in plan.edges
        if edge.kind == "TESTED_BY"
    ]

    assert len(edges) == 1
    assert edges[0].source_key == link.implementation_key
    assert edges[0].target_key == link.test_key
    assert edges[0].confidence == link.confidence

    report = resolution_report(plan)
    recorded = report["test_linking"]["links"][0]

    assert recorded["rule"] == "direct_call"
    assert recorded["call_path"] == list(link.call_path)
    assert recorded["reference_keys"] == list(
        link.reference_keys
    )


def test_repeated_calls_merge_edge_but_preserve_paths():
    plan = build(
        {
            "users.py": (
                "def create_user():\n"
                "    return 1\n"
            ),
            "tests/test_users.py": (
                "from users import create_user\n"
                "def test_create_user():\n"
                "    first = create_user()\n"
                "    second = create_user()\n"
                "    assert first == second\n"
            ),
        }
    )

    assert len(plan.test_linking.links) == 2

    edges = [
        edge
        for edge in plan.edges
        if edge.kind == "TESTED_BY"
    ]

    assert len(edges) == 1
    assert len(edges[0].reference_keys) == 2


def test_unlinked_test_gap_is_preserved_separately():
    plan = build(
        {
            "tests/test_unknown.py": (
                "def test_unknown():\n"
                "    assert True\n"
            ),
        }
    )

    assert plan.test_linking.links == ()
    assert len(plan.test_linking.gaps) == 1

    report = resolution_report(plan)

    assert (
        report["test_linking"]["gaps"][0]["rule_id"]
        == "tests.no_supported_link"
    )

    assert not any(
        edge.kind == "TESTED_BY"
        for edge in plan.edges
    )