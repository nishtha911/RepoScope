"""Snapshot-scoped absence of static test associations, never runtime coverage."""
from typing import Literal
from pydantic import Field
from reposcope.impact.risk_score import Record
from reposcope.graph.traversal_types import positive_int, edge_confidence


class SymbolTestGap(Record):
    symbol_id: int
    status: Literal["LINKED", "NO_KNOWN_TEST_LINK", "UNKNOWN", "NOT_APPLICABLE"]
    test_symbol_ids: tuple[int, ...] = ()
    edge_ids: tuple[int, ...] = ()
    reason: str


class TestGapReport(Record):
    __test__ = False
    repository_id: int
    snapshot_id: int
    items: tuple[SymbolTestGap, ...]
    untested_modified_symbol_ids: tuple[int, ...]
    unknown_symbol_ids: tuple[int, ...]
    gap_ratio: float | None = Field(ge=0, le=1)


def analyze_test_gaps(graph, repository_id, snapshot_id, modified_symbol_ids, *,
                      symbol_roles=None, test_links_complete=False):
    """Roles are verified production/test/unknown assignments for this snapshot.

    A recorded but unverifiable TESTED_BY association blocks an absence claim.
    Fully loaded links do not imply complete static resolution or runtime coverage.
    """
    positive_int(repository_id, "repository_id")
    positive_int(snapshot_id, "snapshot_id")
    if type(test_links_complete) is not bool:
        raise ValueError("test_links_complete must be bool")
    if graph.graph.get("repository_id") != repository_id or graph.graph.get("snapshot_id") != snapshot_id:
        raise ValueError("Graph scope mismatch")
    roles = dict(symbol_roles or {})
    for sid, role in roles.items():
        positive_int(sid, "role_symbol_id")
        if sid not in graph or role not in ("production", "test", "unknown"):
            raise ValueError("Invalid or foreign role assignment")
    for sid, node in graph.nodes(data=True):
        if node.get("repository_id") != repository_id or node.get("snapshot_id") != snapshot_id:
            raise ValueError("Foreign or unscoped graph node")
    if isinstance(modified_symbol_ids, (str, bytes)):
        raise ValueError("Pass symbol IDs")
    raw = tuple(modified_symbol_ids)
    for sid in raw:
        positive_int(sid, "modified_symbol_id")
        if sid not in graph:
            raise ValueError("Modified symbol missing from snapshot")
    items = []
    for sid in sorted(set(raw)):
        node = graph.nodes[sid]
        role = roles.get(sid, "unknown")
        if node.get("kind") not in ("function", "method") or role == "test":
            status, reason, linked, evidence = "NOT_APPLICABLE", "Not a production callable", (), ()
        elif role != "production":
            status, reason, linked, evidence = "UNKNOWN", "Callable test role was not verified", (), ()
        else:
            linked_set, evidence_set, uncertain = set(), set(), False
            for _, target, key, edge in graph.out_edges(sid, keys=True, data=True):
                if edge.get("kind") != "TESTED_BY":
                    continue
                confidence = edge_confidence(edge.get("confidence"))
                eid = edge.get("edge_id", key)
                if (target == sid or roles.get(target) != "test" or confidence is None
                        or confidence <= 0 or type(eid) is not int or eid < 1
                        or graph.nodes[target].get("kind") not in ("function", "method")):
                    uncertain = True
                    continue
                linked_set.add(target)
                evidence_set.add(eid)
            linked, evidence = tuple(sorted(linked_set)), tuple(sorted(evidence_set))
            if linked:
                status, reason = "LINKED", "Static test association found; no runtime coverage claim"
            elif uncertain or not test_links_complete:
                status, reason = "UNKNOWN", "Incomplete or unverifiable static test associations"
            else:
                status, reason = "NO_KNOWN_TEST_LINK", "No association in the fully loaded static test-link index"
        items.append(SymbolTestGap(symbol_id=sid, status=status, reason=reason,
                                  test_symbol_ids=linked, edge_ids=evidence))
    applicable = [x for x in items if x.status != "NOT_APPLICABLE"]
    unknown = tuple(x.symbol_id for x in applicable if x.status == "UNKNOWN")
    untested = tuple(x.symbol_id for x in applicable if x.status == "NO_KNOWN_TEST_LINK")
    ratio = None if unknown else (len(untested) / len(applicable) if applicable else 0.0)
    return TestGapReport(repository_id=repository_id, snapshot_id=snapshot_id,
        items=tuple(items), untested_modified_symbol_ids=untested,
        unknown_symbol_ids=unknown, gap_ratio=ratio)
