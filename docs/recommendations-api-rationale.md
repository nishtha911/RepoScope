# Day 13 Track 2: recommendations API, publication and constrained LLM rationale

## Lifecycle (no mock success)

1. Ingestion/enrichment supplies a complete CandidateDataset for one ready snapshot.
   Metadata must be verified against that revision. Do not set test_links_complete
   merely because graph loading succeeded. Existing source-enrichment work is a
   prerequisite; this patch does not invent complexity/docstring data in the ORM.
2. publish_recommendations(session, dataset) verifies all symbol identities and all
   internal stored edges, runs Day 11 detectors and the Day 12 scorer, and flushes
   an immutable publication plus ranked items. Caller commits or rolls back.
3. GET /api/repos/{id}/recommendations reads the publication and explains the top
   findings. GET never publishes or commits. Missing publication is 409, not mock
   data or a misleading empty-success response. A published empty batch is 200.

The current mock /recommendations route is removed before mounting the live
router. Other mock routes remain mocks (including feedback). One old unit-test
case asserting the mock recommendation response moves to real-service tests;
query validation and all unrelated API assertions remain.

## Schema and migration

The installer creates d13b7f2a9c40_recommendations.py and resolves down_revision
from the single local Alembic head without importing or connecting to a database.
Multiple or unresolvable heads stop installation for review. Run migration only
against the intended database, following normal backup/review procedure:

    cd backend
    python -m alembic upgrade head

Tables: recommendation_runs (repo, snapshot, digest, gaps, timestamp),
recommendation_items (persisted ID, rank, finding, computed features, exact facts,
evidence). IDs are database IDs, not list positions or symbol IDs. Identical
publication inputs/configurations reuse the same run/IDs. Concurrent identical
publication conflicts may raise IntegrityError: roll back and retry in the caller.
Changing input/config publishes a new immutable run, rather than mutating old IDs.
Bump the publication policy version when feature algorithms change.

PostgreSQL publication requires a REPEATABLE READ or SERIALIZABLE transaction;
SQLite tests verify SQL/service behaviour, not PostgreSQL isolation. Example:

```python
from sqlalchemy.orm import Session
from reposcope.db.session import engine
from reposcope.recommendations.pipeline import publish_recommendations

# dataset comes from the verified same-snapshot enrichment pipeline.
with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
    with Session(connection) as session, session.begin():
        run_id = publish_recommendations(session, dataset)
```

The installer never runs this transaction or the migration. Historical snapshot
storage limitations from Day 12 still apply. Publications are not automatically
regenerated when ingestion changes; republish after a reindex. The reader rejects
published IDs moved outside their selected snapshot but cannot prove that all
source metadata remains current after arbitrary in-place mutation. Ready snapshots
must be treated as immutable by the caller.

## Endpoint contract

GET /api/repos/{id}/recommendations?k=10&snapshot_id=123

- k: 1..100, default 10.
- snapshot_id: optional positive ID, must belong to the repository. Without it,
  select the ready snapshot with greatest ID (explicit policy, not Git HEAD).
- 404: missing repo or foreign/missing explicitly selected snapshot.
- 409: no ready snapshot or unpublished/stale recommendations.
- 422: invalid path/query.
- 200: existing Finding fields plus persisted id, rationale, rationale_source,
  rationale_degraded_reason, computed_features, detector_evidence, feature_citations.
- Response also includes repo_id, snapshot_id, commit_sha, run_id and explicit gaps.
- No fallback to an older snapshot's recommendations if the latest is unpublished.

Keep recommendation priority distinct from Track 1 PR risk. The priority score
is the existing (impact * likelihood / applied_effort) * confidence * multiplier,
with configured rounding. Applied effort includes the scorer's minimum clamp.
Returned computed_features preserves both original effort and applied_effort.

## Grounded rationale design

Unconstrained generated prose cannot be made entailed merely by checking numbers.
Instead, the model selects priority/fan-in/complexity/doc-gap templates and returns
only feature citations. Each required name/value is checked against the persisted
computed facts, including cache hits. Extra prose, unknown/duplicate/missing refs,
wrong values, and unsupported templates are rejected. The server renders only
approved sentences. This is constrained LLM-assisted generation, not freeform prose.

Every explanation cites impact, likelihood, applied effort, confidence, multiplier
and score. Measured detector values are separate from heuristic estimates. A
likelihood estimate is not a measured defect rate. Test links are not runtime
coverage; doc-gap policy concerns handler docstrings, not all external docs.
Model prompts contain numeric features/category/IDs only, not arbitrary repository
source, descriptions, or prompt-injection-bearing titles.

Existing LLMClient is reused (Gemini synthesis / configured fallback). Existing
GEMINI_API_KEY+GEMINI_MODEL or the established Groq fallback configuration apply;
.env loading is not introduced into the LLM client. No configured model or any
expected provider/output failure yields a clearly labelled deterministic rationale.
No live LLM call is required for tests. At most ten model calls per GET, concurrency
three, each eight-second timeout; subsequent items use deterministic rendering.
The existing scoped cache is reused process-locally (five-minute TTL). Cache scope
includes repo, snapshot and persisted finding ID; full evidence affects cache keys.
Authentication, rate limiting and tenant authorization remain deployment concerns;
this does not add an authentication boundary to an otherwise public API.

## Verification

python -m pytest tests/unit/test_recommendation_rationale.py tests/unit/test_recommendation_pipeline.py tests/unit/test_recommendations_api.py tests/unit/test_recommendation_migration.py -q -rs

18 rationale tests passed in the build environment. SQLAlchemy/FastAPI-dependent
pipeline, API and migration modules skipped there because those libraries were
not installed. Those tests must run locally before approval. No PostgreSQL,
production publication, real provider call or full regression success is claimed.
Then run python -m pytest tests -q -rs and git diff --check.

This patch supplies a live publication/reader workflow and strict explanation
boundary. It does not complete the previously deferred automatic source-enrichment
pipeline or wire it into ingestion, and does not implement real feedback storage/UI.
