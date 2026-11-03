"""Compare generated graph to the existing curated mini_repo oracle.

This checks all definition identities and the oracle's CALLS/INHERITS subset.
Extra generated edges are reported, not rejected: the legacy oracle explicitly
is not exhaustive. TESTED_BY is excluded as a later detector milestone.
"""
import argparse
import json
from pathlib import Path

from reposcope.graph.builder import build_graph_plan, target_key
from reposcope.parsing.python_parser import parse_python


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path(__file__).resolve().parents[1]
                        / "tests" / "fixtures" / "mini_repo")
    args = parser.parse_args()
    root = args.fixture.resolve()
    golden = json.loads((root / "golden_graph.json").read_text(encoding="utf-8"))
    parsed = [parse_python(path.read_bytes(), file_path=path.relative_to(root.parent).as_posix())
              for path in sorted(root.rglob("*.py"))]
    plan = build_graph_plan(parsed)
    prefix = root.name + "/"
    paths = {f["id"]: prefix + f["path"] for f in golden["files"]}
    names = {m["symbol_id"]: m["qualified_name"] for m in golden["symbol_metadata"]}
    expected_nodes = {(paths[s["file_id"]], names[s["id"]], s["kind"],
                       s["start_line"], s["end_line"]) for s in golden["symbols"]}
    actual_nodes = {(n.path, n.qualname, n.kind, n.start_line, n.end_line)
                    for n in plan.nodes if n.kind != "module"}
    oracle_labels = {s["id"]: (paths[s["file_id"]], names[s["id"]]) for s in golden["symbols"]}
    actual_labels = {n.key: (n.path, n.qualname) for n in plan.nodes}
    expected_edges = {(oracle_labels[e["source_symbol_id"]], oracle_labels[e["target_symbol_id"]], e["kind"])
                      for e in golden["edges"] if e["kind"] in {"CALLS", "INHERITS"}}
    actual_edges = {(actual_labels[e.source_key], actual_labels[e.target_key], e.kind)
                    for e in plan.edges if e.kind in {"CALLS", "INHERITS"}}
    report = {
        "missing_symbols": sorted(expected_nodes - actual_nodes),
        "extra_symbols": sorted(actual_nodes - expected_nodes),
        "missing_expected_edges": sorted(expected_edges - actual_edges),
        "extra_generated_edges": sorted(actual_edges - expected_edges),
        "expected_edge_count_in_scope": len(expected_edges),
        "matched_expected_edge_count": len(expected_edges & actual_edges),
        "excluded_later_stage_edges": sum(e["kind"] not in {"CALLS", "INHERITS"} for e in golden["edges"]),
        "resolution_counts": {status: sum(r.status == status for r in plan.results)
                              for status in ("EXACT", "INFERRED", "AMBIGUOUS", "UNRESOLVED")},
    }
    print(json.dumps(report, indent=2))
    return int(bool(report["missing_symbols"] or report["extra_symbols"] or report["missing_expected_edges"]))


if __name__ == "__main__":
    raise SystemExit(main())
