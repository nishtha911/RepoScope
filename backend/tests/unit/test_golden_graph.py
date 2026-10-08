import ast
import json
from pathlib import Path

import pytest

from reposcope.contracts.edge import Edge
from reposcope.contracts.symbol import Symbol


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mini_repo"


@pytest.fixture
def graph():
    return json.loads((FIXTURE / "golden_graph.json").read_text(encoding="utf-8"))


def collect_definitions(path):
    definitions = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []

        def record(self, node, kind):
            qualified_name = ".".join([name for name, _ in self.scope] + [node.name])
            definitions[qualified_name] = (node, kind)
            self.scope.append((node.name, kind))
            self.generic_visit(node)
            self.scope.pop()

        def visit_ClassDef(self, node):
            self.record(node, "class")

        def visit_FunctionDef(self, node):
            kind = "method" if self.scope and self.scope[-1][1] == "class" else "function"
            self.record(node, kind)

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

    Visitor().visit(ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path)))
    return definitions


def lookup(graph):
    files = {item["id"]: item["path"] for item in graph["files"]}
    metadata = {item["symbol_id"]: item["qualified_name"] for item in graph["symbol_metadata"]}
    return {symbol["id"]: (files[symbol["file_id"]], metadata[symbol["id"]]) for symbol in graph["symbols"]}


def test_counts_and_scope(graph):
    assert graph["schema_version"] == 1
    assert graph["files_count"] == len(graph["files"]) == 15
    assert graph["symbols_count"] == len(graph["symbols"]) == 44
    assert graph["edges_count"] == len(graph["edges"]) == 45
    assert "Not an exhaustive" in graph["scope"]["edges"]
    assert graph["scope"]["test_edge_direction"] == "implementation symbol -> TESTED_BY -> test function"


def test_ids_and_paths_are_unique(graph):
    for key in ("files", "symbols", "edges"):
        ids = [item["id"] for item in graph[key]]
        assert all(isinstance(value, int) and value > 0 for value in ids)
        assert len(ids) == len(set(ids))
    paths = [item["path"] for item in graph["files"]]
    assert len(paths) == len(set(paths))
    relations = [(edge["source_symbol_id"], edge["target_symbol_id"], edge["kind"]) for edge in graph["edges"]]
    assert len(relations) == len(set(relations))


def test_file_inventory_matches_source(graph):
    actual = {path.relative_to(FIXTURE).as_posix() for path in FIXTURE.rglob("*.py")}
    assert {item["path"] for item in graph["files"]} == actual
    root = FIXTURE.resolve()
    for item in graph["files"]:
        path = FIXTURE / item["path"]
        assert not Path(item["path"]).is_absolute()
        assert path.resolve().is_relative_to(root)
        assert path.is_file()


def test_symbols_and_edges_match_contracts(graph):
    for symbol in graph["symbols"]:
        Symbol.model_validate(symbol)
    for edge in graph["edges"]:
        Edge.model_validate(edge)


def test_metadata_and_references_are_complete(graph):
    file_ids = {item["id"] for item in graph["files"]}
    symbol_ids = {item["id"] for item in graph["symbols"]}
    edge_ids = {item["id"] for item in graph["edges"]}
    assert len(graph["symbol_metadata"]) == len(symbol_ids)
    assert {item["symbol_id"] for item in graph["symbol_metadata"]} == symbol_ids
    assert len(graph["edge_metadata"]) == len(edge_ids)
    assert {item["edge_id"] for item in graph["edge_metadata"]} == edge_ids
    for symbol in graph["symbols"]:
        assert symbol["file_id"] in file_ids
    for edge in graph["edges"]:
        assert edge["source_symbol_id"] in symbol_ids
        assert edge["target_symbol_id"] in symbol_ids


def test_complete_symbol_inventory_and_line_ranges(graph):
    references = lookup(graph)
    actual = {}
    for item in graph["files"]:
        for qualified_name, (node, kind) in collect_definitions(FIXTURE / item["path"]).items():
            actual[(item["path"], qualified_name)] = (node.name, kind, node.lineno, node.end_lineno)
    expected = {}
    for symbol in graph["symbols"]:
        identity = references[symbol["id"]]
        assert identity not in expected
        expected[identity] = (symbol["name"], symbol["kind"], symbol["start_line"], symbol["end_line"])
    assert expected == actual


def relation_context(graph, edge):
    references = lookup(graph)
    source_path, source_name = references[edge["source_symbol_id"]]
    target_path, target_name = references[edge["target_symbol_id"]]
    source_node = collect_definitions(FIXTURE / source_path)[source_name][0]
    target_node = collect_definitions(FIXTURE / target_path)[target_name][0]
    expression = next(item["source_expression"] for item in graph["edge_metadata"] if item["edge_id"] == edge["id"])
    return source_node, target_node, expression, target_path


def test_selected_calls_have_source_call_sites(graph):
    for edge in graph["edges"]:
        if edge["kind"] != "CALLS":
            continue
        source, target, expression, _ = relation_context(graph, edge)
        assert isinstance(source, (ast.FunctionDef, ast.AsyncFunctionDef))
        calls = {ast.unparse(node.func) for node in ast.walk(source) if isinstance(node, ast.Call)}
        assert expression in calls
        assert expression.split(".")[-1] == target.name


def test_inheritance_matches_class_bases(graph):
    for edge in graph["edges"]:
        if edge["kind"] != "INHERITS":
            continue
        source, target, expression, _ = relation_context(graph, edge)
        assert isinstance(source, ast.ClassDef)
        assert isinstance(target, ast.ClassDef)
        assert expression in {ast.unparse(base) for base in source.bases}
        assert expression == target.name


def test_tested_by_direction_and_direct_call_sites(graph):
    for edge in graph["edges"]:
        assert edge["kind"] in {"CALLS", "INHERITS", "TESTED_BY"}
        if edge["kind"] != "TESTED_BY":
            continue
        implementation, test, expression, test_path = relation_context(graph, edge)
        assert Path(test_path).name.startswith("test_")
        assert isinstance(test, (ast.FunctionDef, ast.AsyncFunctionDef))
        assert test.name.startswith("test_")
        calls = {ast.unparse(node.func) for node in ast.walk(test) if isinstance(node, ast.Call)}
        assert expression in calls
        assert expression.split(".")[-1] == implementation.name