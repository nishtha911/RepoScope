# Day 12 Track 1: bounded multi-source blast radius

## Public entry points

- blast_radius(graph, repository_id, snapshot_id, modified_symbol_ids, ...)
- load_snapshot_graph(session, repository_id, snapshot_id, ...)
- analyze_snapshot_blast_radius(session, repository_id, snapshot_id, modified_symbol_ids, ...)
- resolve_diff_seeds(diff_report, graph, side, local_key_to_symbol_id)

The graph is a NetworkX MultiDiGraph. Node metadata requires repository_id,
snapshot_id, file_id, file_path, name and kind. Loader adds qualname and line
ranges for checked diff bindings. Edges require globally unique persisted IDs,
kind and confidence. A database model is an explicit verified node flag, not any
class. The loader accepts verified database_model_ids for this purpose.

## Direction and endpoints

CALLS: caller -> callee. INHERITS: subclass -> base. USES: consumer -> model.
Reverse BFS propagates from changed dependencies to their dependents.
Endpoint -> CALLS -> handler lets changed service code reach handlers/endpoints.
Module -> EXPOSES -> endpoint is preserved in endpoint_exposures, not used to
fan out into sibling endpoints. Module membership alone is not call dependence.
A changed endpoint seed is included even with no callers.

## Weight and paths

Seeds have weight 1. For depth d >= 1:
weight = product(edge confidences) * 0.8 ** (d - 1).
Decay is configurable in [0,1]. No edge-kind multipliers are guessed.
A queue explores bounded simple paths breadth-first, from all unique seeds.
Results retain strongest paths; ties use depth, symbol path, then edge IDs.
min_depth records shortest valid reachability independently of strongest path.
A weaker shorter route is still expanded because it may reach further nodes
within the depth budget. Seeds and affected nodes are returned once, sorted by ID.
Counts derived from affected_file_ids and endpoint/model IDs INCLUDE changed seeds.

Defaults: depth 4 (maximum 8), 10000 results, 100000 edge examinations.
Result/expansion exhaustion raises existing TraversalBudgetExceeded; it never
returns an apparently complete partial report. depth_limited flags a valid edge
toward an as-yet-unreached symbol at the configured horizon. It does not claim
whole-repository completeness. Null/invalid confidences are skipped and reported
for examined propagation edges; zero confidence is preserved as zero weight.
Reachability weight is not a probability, severity, coverage or Day 13 risk score.

## Snapshot and database safety

Loader requires a ready snapshot belonging to the selected repository. Both ends
of every loaded edge are scoped to that snapshot. Legacy NULL snapshots and
cross-repository/cross-snapshot edges are excluded. It performs SELECTs only,
does not commit, and requires a clean read session under an outer REPEATABLE READ
transaction on PostgreSQL for a consistent view across its queries. Loader node/
edge budgets bound returned rows; database statement timeout remains the caller's
responsibility. No migration or new dependency is introduced.

Current file storage uses uniqueness on (repository_id, path). This patch does
not invent durable historical graph storage: a base graph must actually exist
in the provided snapshot/session or be supplied independently in memory.

## Day 11 bridge

Resolve each side separately. The graph commit_sha must exactly equal that
side's diff revision. Supply side-specific local-key-to-persisted-ID bindings.
Every bound ID is checked against file path, qualified name, kind and line range.
Missing bindings return gaps, invalid bindings fail, upstream mapper gaps are
carried as an incompleteness warning. Added symbols have no base seed; removed
symbols have no head seed. Analyze base and head separately, never union their
IDs as if they belonged to one snapshot. Mapping-gap handling must remain visible
at the orchestration boundary. PR fetching/report/API orchestration is not added.

## Verification

python -m pytest tests/unit/test_blast_radius.py tests/unit/test_blast_radius_loader.py -q -rs

48 graph/bridge tests passed in the build environment. SQLAlchemy was absent there,
so the loader-test module skipped. Locally the loader tests use SQLAlchemy with
SQLite to execute snapshot and edge-scoping queries; that is NOT PostgreSQL
transaction/isolation verification. No PostgreSQL execution is claimed.
Run the full existing backend regression after focused tests.

## Out of scope

Track 2 heuristic scoring, Track 3 UI, risk scoring, PR fetching, historical graph
persistence, inferred database-model labels, and live HTTP endpoint integration.
