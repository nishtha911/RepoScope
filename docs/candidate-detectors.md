# Day 11 candidate detectors

`reposcope.recommendations.detectors.detect_candidates(dataset, config)` emits
unranked existing Finding contracts, parallel structured evidence, and explicit gaps.
No new dependency, schema migration, LLM request, or database write is required.

## Input boundary

The caller must load one repository snapshot, verify all file ownership, and supply
persisted Symbol/Edge contracts. CandidateDataset rejects dangling edges and
inconsistent file identities, but cannot independently verify database ownership.
It must not be used to stamp arbitrary symbols with a snapshot ID.

The current stored Symbol model lacks complexity/docstring metadata. Supply those
from matching, validated parser output for the same snapshot. Do not join by name
alone. documentation_known=False means not inspected, not undocumented.
is_test=None means unknown. test_links_complete defaults to False: set it only
when the supplied snapshot's static test-link index has been fully loaded.

## Rules (initial configurable policies)

* UNTESTED_HOTSPOT: at least 5 distinct known non-test incoming callers with
  confidence >= 0.5 and no outgoing TESTED_BY association. Any TESTED_BY link
  suppresses the absence claim. Requires complete test-link input. This is not
  proof of absent runtime test coverage. Self-calls and endpoint dispatch do not
  count. Unknown/low-confidence calls do not count.
* COMPLEXITY_HOTSPOT: measured complexity >= 10, with its measurement policy.
  Unknown measurements generate gaps; complexity is never inferred from length.
* API_DOC_GAP: endpoint has exactly one eligible endpoint-to-callable CALLS link,
  and that handler was inspected and has no nonblank docstring. This narrowly
  defined handler_docstring_v1 policy does not assess external docs or OpenAPI.

Known test functions/methods are excluded from callable hotspots. Unknown test
roles are excluded with a gap. Findings sort by symbol ID, then detector order;
related IDs and gaps are sorted. Duplicate caller edges count once.
Finding score/confidence remain None: graph confidence is not a calibrated finding
probability. Priority scoring is Day 12.

## Verification and limits

Run: python -m pytest tests/unit/test_candidate_detectors.py -q -rs

32 focused tests cover boundaries, duplicates, scoping checks, test-link direction,
confidence filters, unknown metadata, documentation policies, and stable ordering.
The implementation was tested in isolation with the uploaded shared contracts.
It has not been run against PostgreSQL or the full local backend suite.

This patch provides the detector core, not a database loader/enrichment adapter,
persistence pipeline, ranking, recommendation API, or UI integration. Those are
not silently implemented by calling detect_candidates.
