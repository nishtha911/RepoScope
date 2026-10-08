# Shared contracts: proposed alignment

Status: implementation proposal. Not yet approved/frozen by the three tracks.

## Layers
- Domain contracts: Symbol, Edge, Chunk, Evidence, Finding, Repository, PRImpactReport.
- API DTOs: contracts/api.py. A DTO is the explicitly declared public JSON shape.
- ORM models: models/. Database column names need not equal public JSON names.
- All these Pydantic objects retain extra="forbid". This is extra-field rejection,
  not Pydantic strict=True; ordinary documented type coercions are still enabled.
- API routes return validated DTO objects and declare response_model.
- The endpoints are mocks. Schema validation does not make mock data real.

## Symbols
Canonical kinds: module, class, function, method, parameter, variable, endpoint.
These are lowercase and case-sensitive. Existing uppercase METHOD mock output becomes method.
Endpoint is a proposed public classification; Track 1 must confirm how it is represented.
No historical database values are migrated by this patch.

SymbolListItem includes id, file_id, name, kind, start_line, end_line, qualname, file_path.
SymbolDetailResponse extends it with nullable signature, docstring, cyclomatic_complexity.
Null means unknown/not applicable; it does not mean empty text or zero complexity.
Known complexity must be >= 1. Line ranges are inclusive and 1-based.
The core Symbol remains free of file_path/qualname and rejects those extra fields.

## Edges
Allowed kinds: CALLS, IMPORTS, INHERITS, EXPOSES, USES, TESTED_BY.
Kinds are uppercase and case-sensitive. TESTS is rejected, not silently reinterpreted.
Direction: CALLS caller -> callee; IMPORTS importer -> imported module/symbol;
INHERITS subclass -> base; TESTED_BY implementation -> test.
Proposed EXPOSES: exposing router/module -> endpoint symbol.
Proposed USES: consuming symbol -> used model/resource symbol.
Track 1 must approve derived-edge endpoints before EXPOSES/USES emitters are implemented.
Neighbors dir=in returns incoming neighbors; dir=out returns outgoing neighbors.
types is a comma-separated list of the allowed edge kinds. Empty means no kind filter.

Confidence is a nullable finite number in [0, 1]. Null means unassigned/unknown,
not zero and not an exact edge. Resolver labels EXACT/INFERRED/AMBIGUOUS/UNRESOLVED
are a separate concept; no numerical mapping from labels is frozen by this patch.
Unresolved targets must not be invented just to construct an Edge with a positive ID.
Finding score is nonnegative but not necessarily <=1. Search score is a finite ranking
score, not a probability, and is not given a [0,1] bound.

## Repository and snapshot semantics
RepositoryResponse extends Repository with required snapshot_id, file_count, symbol_count
fields whose values may be null. Its id is required and positive.
Counts and head_sha refer to the same explicitly selected indexing snapshot, never to a
mixture of repository history. Null count means unknown; zero means computed empty.
Without a snapshot, snapshot_id/head_sha/counts must all be null.
With a snapshot, head_sha is required. A partial/pending snapshot may have null counts.
The proposed identity of an indexing run is (repository_id, commit_sha, index_version),
matching the existing snapshot ORM uniqueness rule. A ready snapshot is intended to be
immutable; that lifecycle is a service/database responsibility, not proved by these DTOs.
Default/latest-snapshot selection must be supplied by the service before ORM-backed routes
replace mocks. Never guess the default branch from the repository URL.

repository_to_response explicitly maps full_name -> name and remote_url -> url.
It requires caller-supplied branch/status/snapshot/count context and does not run database
queries. Use it at the persistence/service boundary when connecting real routes.

Important persistence follow-up: files currently has unique(repository_id, path), not
unique(snapshot_id, path), and snapshot_id is nullable. This patch does not claim that
historical per-snapshot file inventories are already supported. Track 1 must resolve
that schema/lifecycle before storing multiple immutable snapshots. No migration is included.

## Requests and queries
Proposed MVP URL policy: HTTPS github.com only; repository URLs /owner/repo[.git][/],
PR URLs /owner/repo/pull/positive-number[/]. No credentials, ports, query or fragment.
SSH remotes/GitHub Enterprise/other hosts are not supported by this proposal.
Syntactic URL validation is not a substitute for safe cloning, redirect checks, or SSRF
protection in the ingestion implementation.

Search modes: hybrid, lexical, vector. Feedback: accepted, dismissed, not_useful.
The plan has accepted/dismissed in its API table and adds not_useful in Day 22;
this proposal reconciles them by allowing all three. Team approval remains required.
IDs > 0; limit 1..100 (default 20); k 1..100 (default 10).
Symbol query kind uses the canonical lowercase kinds; omitted/empty means all kinds.
Search q: 1..2000 characters after stripping surrounding whitespace.
Ask question: 1..10000 characters after stripping surrounding whitespace.
The limits are proposed operational bounds, not pre-existing team decisions.
Invalid inputs return 422 using the existing error envelope.

## Response envelopes
Keep existing keys: symbols, query/hits, answer/evidence/gaps, recommendations, neighbors.
Reuse Evidence for Q&A and Finding for recommendation items. Evidence IDs must be unique
within an answer. Full citation/claim grounding validation remains Track 2 work; schema
validation alone does not prove an answer is grounded.
Registration, repository detail, symbol detail, PR report, feedback, health, and errors
also have declared/validated response models.

## Route correction
The existing repos router put symbols/recs under /api/repos/symbols and /api/repos/recs,
while docs require /api/symbols and /api/recs. This patch corrects those paths without
legacy aliases. Frontend callers using accidental old paths must be updated.
The planned symbol-impact endpoint is still not implemented by this contracts patch.

## Frontend compatibility and approval
The uploaded bundle includes no frontend files. No frontend code is patched or verified.
Track 3 must check API URLs, uppercase kind badges/filters, required file_id, additional
qualname/file_path on detail responses, snapshot_id and nullable counts before merge.
Use OpenAPI as the backend schema source; update/generated TypeScript types as appropriate
for the actual frontend tooling. TypeScript types alone do not validate network JSON.

Required sign-off: Track 1 (kinds, edge semantics, adapters, snapshots), Track 2
(retrieval modes/evidence/confidence), Track 3 (response shapes/paths/frontend compatibility).
Tests verify implementation behavior, not agreement. The plan requires a shared-contract
PR approved by all three contributors, targeting dev unless the team explicitly changes
its workflow. Do not merge your own PR under the current plan.
