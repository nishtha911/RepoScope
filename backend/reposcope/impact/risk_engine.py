"""Day 11 diff + Day 12 traversal -> auditable Day 13 risk features.

Callers supply verified same-revision parser complexity measurements and roles.
No LLM, database write, source execution, risk API replacement, or schema change.
"""
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Literal
from math import isfinite
from reposcope.impact.blast_radius import resolve_diff_seeds
from reposcope.impact.risk_score import Record, RiskFeatures, RiskPolicy, RiskScore, score_risk
from reposcope.impact.test_gap import TestGapReport, analyze_test_gaps


@dataclass(frozen=True)
class RiskSnapshot:
    graph: Any
    blast_radius: Any
    bindings: Mapping[str, int]
    symbol_roles: Mapping[int, str] = field(default_factory=dict)
    test_links_complete: bool = False
    sensitive_symbol_ids: tuple[int, ...] = ()
    sensitivity_complete: bool = False


class UntestedModifiedSymbol(Record):
    side: Literal["base", "head"]
    snapshot_id: int
    symbol_id: int
    local_key: str
    qualname: str
    filepath: str


class SideRiskEvidence(Record):
    side: Literal["base", "head"]
    snapshot_id: int
    blast_mass: float
    seed_ids: tuple[int, ...]
    test_gaps: TestGapReport


class RiskAssessment(Record):
    repository_id: int
    base_revision: str | None
    head_revision: str | None
    features: RiskFeatures
    risk: RiskScore
    policy: RiskPolicy
    changed_lines: int
    contract_change_count: int
    maximum_complexity_increase: int | None
    untested_modified_symbols: tuple[UntestedModifiedSymbol, ...]
    sides: tuple[SideRiskEvidence, ...]
    gaps: tuple[str, ...]


def assess_pr_risk(diff_report, repository_id, snapshots, *,
                   base_complexities=None, head_complexities=None, policy=None):
    """Analyze separate base/head graphs without mixing their persisted IDs.

    Blast feature: max(per-side sum of affected weights) / cap, clamped to 1.
    Sensitivity: max signal (endpoint=.6, verified model=.8, sensitive symbol=1).
    Test gap: missing-link fraction among modified production callables, using
    head where present and base for removals. Unknown role/link data -> unknown.
    Contract: mean classification cost (body=0, added=.5, removed/signature=1).
    Complexity: max positive increase over changed callables / cap (added base=0,
    removal increase=0); class complexity is not a callable measurement.
    Size: added+deleted patch rows / cap. Defaults are initial explicit policies,
    not empirically calibrated predictors or semantic breaking-change detection.
    """
    if type(repository_id) is not int or repository_id < 1:
        raise ValueError("repository_id must be positive integer")
    if any(side not in ("base", "head") for side in snapshots):
        raise ValueError("Snapshot keys must be base/head")
    policy = RiskPolicy.model_validate((policy or RiskPolicy()).model_dump())
    measurements = {"base": base_complexities, "head": head_complexities}
    for values in measurements.values():
        if values is not None:
            if not isinstance(values, Mapping):
                raise TypeError("Complexity input must map local keys to measurements")
            if any(not isinstance(k, str) or type(v) is not int or v < 1 for k,v in values.items()):
                raise ValueError("Complexity measurements must be positive integers")
    gaps = [f"DIFF_MAPPING:{g.code}:{g.path}:{g.side}" for g in diff_report.gaps]
    side_evidence, gap_lookup, contexts = [], {}, {}
    binding_incomplete, blast_incomplete = bool(diff_report.gaps), bool(diff_report.gaps)
    sensitivity_unknown = False
    sensitivity_values = []
    all_masses = []
    required = {side for side in ("base", "head")
                if any(getattr(c, f"{side}_symbol") is not None for c in diff_report.changes)}
    for side in sorted(required):
        ctx = snapshots.get(side)
        if ctx is None:
            gaps.append(f"MISSING_{side.upper()}_SNAPSHOT")
            binding_incomplete = blast_incomplete = sensitivity_unknown = True
            continue
        graph, blast = ctx.graph, ctx.blast_radius
        if type(ctx.sensitivity_complete) is not bool:
            raise ValueError("sensitivity_complete must be bool")
        if (graph.graph.get("repository_id") != repository_id
                or blast.repository_id != repository_id
                or graph.graph.get("snapshot_id") != blast.snapshot_id):
            raise ValueError("Blast radius and graph scope mismatch")
        resolution = resolve_diff_seeds(diff_report, graph, side, ctx.bindings)
        if tuple(sorted(blast.seed_symbol_ids)) != resolution.seed_symbol_ids:
            raise ValueError("Blast seeds must equal resolved modified symbols for this side")
        if resolution.gaps:
            binding_incomplete = blast_incomplete = True
            gaps.extend(f"{side}:{g}" for g in resolution.gaps)
        if blast.depth_limited or blast.skipped_confidence_edge_ids:
            blast_incomplete = True
            gaps.append(f"{side}:BLAST_TRUNCATED_OR_UNKNOWN_CONFIDENCE")
        hit_ids = [h.symbol_id for h in blast.hits]
        if len(hit_ids) != len(set(hit_ids)) or not set(resolution.seed_symbol_ids) <= set(hit_ids):
            raise ValueError("Invalid blast inventory")
        for hit in blast.hits:
            if hit.symbol_id not in graph or not isfinite(hit.weight) or not 0 <= hit.weight <= 1:
                raise ValueError("Invalid blast hit")
        mass = sum(h.weight for h in blast.hits)
        all_masses.append(mass)
        sensitive = set(ctx.sensitive_symbol_ids)
        if any(type(sid) is not int or sid < 1 for sid in sensitive) or not sensitive <= set(graph):
            raise ValueError("Foreign sensitive-symbol ID")
        signal = max((1.0 if h.symbol_id in sensitive else .8 if h.is_database_model
                      else .6 if h.is_endpoint else 0.0 for h in blast.hits), default=0.0)
        sensitivity_values.append(signal)
        if not ctx.sensitivity_complete:
            sensitivity_unknown = True
            gaps.append(f"{side}:SENSITIVITY_CLASSIFICATION_INCOMPLETE")
        test_gaps = analyze_test_gaps(graph, repository_id, blast.snapshot_id,
            resolution.seed_symbol_ids, symbol_roles=ctx.symbol_roles,
            test_links_complete=ctx.test_links_complete)
        for item in test_gaps.items:
            gap_lookup[side, item.symbol_id] = item
        side_evidence.append(SideRiskEvidence(side=side, snapshot_id=blast.snapshot_id,
            blast_mass=mass, seed_ids=resolution.seed_symbol_ids, test_gaps=test_gaps))
        contexts[side] = ctx
    primary, untested, unknown_primary = [], [], binding_incomplete
    complexity_increases, complexity_unknown = [], bool(diff_report.gaps)
    for change in diff_report.changes:
        side = "head" if change.head_symbol is not None else "base"
        version = getattr(change, f"{side}_symbol")
        ctx = contexts.get(side)
        sid = ctx.bindings.get(version.local_key) if ctx else None
        item = gap_lookup.get((side, sid))
        if item is None:
            unknown_primary = True
        elif item.status == "UNKNOWN":
            unknown_primary = True
            gaps.append(f"{side}:TEST_LINKS_OR_ROLE_UNKNOWN:{sid}")
        elif item.status != "NOT_APPLICABLE":
            primary.append(item)
            if item.status == "NO_KNOWN_TEST_LINK":
                untested.append(UntestedModifiedSymbol(side=side,
                    snapshot_id=ctx.blast_radius.snapshot_id, symbol_id=sid,
                    local_key=version.local_key, qualname=version.qualname, filepath=version.path))
        if version.kind not in ("function", "method"):
            continue
        before, after = change.base_symbol, change.head_symbol
        if after is None:
            complexity_increases.append(0)
            continue
        new = (head_complexities or {}).get(after.local_key)
        old = 0 if before is None else (base_complexities or {}).get(before.local_key)
        if new is None or old is None:
            complexity_unknown = True
            gaps.append(f"COMPLEXITY_UNKNOWN:{version.local_key}")
        else:
            complexity_increases.append(max(0, new - old))
    unknown_files = any(f.binary or f.symlink or f.submodule or f.status == "COPIED"
                        for f in diff_report.patch.files)
    if unknown_files:
        gaps.append("UNMEASURED_PATCH_ENTRIES")
        blast_incomplete = unknown_primary = sensitivity_unknown = complexity_unknown = True
    changed_lines = sum(row.kind in ("+", "-") for f in diff_report.patch.files
                        for h in f.hunks for row in h.lines)
    costs = {"BODY_CHANGED": 0, "ADDED": .5, "REMOVED": 1, "SIGNATURE_CHANGED": 1}
    changes = diff_report.changes
    contract = sum(costs[c.classification] for c in changes) / len(changes) if changes else 0.0
    contract_count = sum(c.classification != "BODY_CHANGED" for c in changes)
    maximum_delta = None if complexity_unknown else max(complexity_increases, default=0)
    known_signal = max(sensitivity_values, default=0)
    features = RiskFeatures(
        blast_radius=None if blast_incomplete else min(1, max(all_masses, default=0) / policy.blast_mass_cap),
        sensitivity=None if sensitivity_unknown and known_signal < 1 else known_signal,
        test_gap=None if unknown_primary else sum(x.status == "NO_KNOWN_TEST_LINK" for x in primary) / len(primary) if primary else 0,
        contract_changes=None if diff_report.gaps or unknown_files else contract,
        complexity_delta=None if maximum_delta is None else min(1, maximum_delta / policy.complexity_increase_cap),
        size=None if unknown_files else min(1, changed_lines / policy.changed_lines_cap))
    return RiskAssessment(repository_id=repository_id, base_revision=diff_report.base_revision,
        head_revision=diff_report.head_revision, features=features, risk=score_risk(features), policy=policy,
        changed_lines=changed_lines, contract_change_count=contract_count,
        maximum_complexity_increase=maximum_delta,
        untested_modified_symbols=tuple(sorted(untested, key=lambda x:(x.side,x.symbol_id))),
        sides=tuple(side_evidence), gaps=tuple(sorted(set(gaps))))
