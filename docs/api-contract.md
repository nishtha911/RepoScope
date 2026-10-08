# RepoScope OpenAPI Specification & Contract Documentation
Version: 1.1.0 (proposed; cross-track review pending)

See `shared-contracts.md` for vocabulary, nullability, snapshot semantics and bounds.
These endpoints remain mock implementations.

## Standard Error Envelope
All error responses return HTTP status >= 400 and adhere to the standard JSON error envelope:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable description",
    "details": {},
    "status": 400
  }
}
```

Standard error codes:
- `BAD_REQUEST` (400)
- `UNAUTHORIZED` (401)
- `FORBIDDEN` (403)
- `NOT_FOUND` (404)
- `METHOD_NOT_ALLOWED` (405)
- `CONFLICT` (409)
- `VALIDATION_ERROR` (422)
- `RATE_LIMITED` (429)
- `INTERNAL_ERROR` (500)
- `NOT_IMPLEMENTED` (501)

---

## Endpoints Specification

### 1. Health Check
`GET /api/health`
- **Response 200 OK:**
  ```json
  {
    "status": "ok",
    "v": "1.0"
  }
  ```

### 2. Repositories
`POST /api/repos`
- **Request Body:**
  ```json
  {
    "url": "https://github.com/owner/repo.git"
  }
  ```
- **Response 202 Accepted:**
  ```json
  {
    "repo_id": 1,
    "status": "pending",
    "message": "Mock registration accepted; no ingestion job was enqueued"
  }
  ```

`GET /api/repos/{id}`
- **Response 200 OK:**
  ```json
  {
    "id": 1,
    "url": "https://github.com/owner/repo",
    "name": "owner/repo",
    "default_branch": "main",
    "status": "ready",
    "head_sha": "d631c3f98581ab3ebdb0c8daa28cc8bf122f749a",
    "snapshot_id": 1,
    "symbol_count": 3412,
    "file_count": 142
  }
  ```

`GET /api/repos/{id}/symbols?q={str}&kind={str}&limit={int}`
- **Response 200 OK:**
  ```json
  {
    "symbols": [
      {
        "id": 101,
        "file_id": 12,
        "name": "resolve_calls",
        "qualname": "SymbolResolver.resolve_calls",
        "kind": "method",
        "file_path": "backend/reposcope/parsing/resolver.py",
        "start_line": 142,
        "end_line": 180
      }
    ]
  }
  ```

### 3. Symbol Inspection & Graph Neighbors
`GET /api/symbols/{id}`
- **Response 200 OK:**
  ```json
  {
    "id": 101,
    "file_id": 12,
    "qualname": "SymbolResolver.resolve_calls",
    "file_path": "backend/reposcope/parsing/resolver.py",
    "name": "resolve_calls",
    "kind": "method",
    "start_line": 142,
    "end_line": 180,
    "signature": "def resolve_calls(self, ast_tree) -> list[Edge]:",
    "docstring": "Resolves call expressions to candidate symbol IDs.",
    "cyclomatic_complexity": 4
  }
  ```

`GET /api/symbols/{id}/neighbors?dir={in|out}&types={str}`
- **Response 200 OK:**
  ```json
  {
    "neighbors": [
      {
        "symbol_id": 204,
        "name": "SymbolScanner.scan",
        "relationship_type": "CALLS",
        "confidence": 1.0,
        "direction": "in"
      }
    ]
  }
  ```

`GET /api/symbols/{id}/impact?depth={int}`

Planned endpoint: not implemented by the current mock router or this contracts patch.

Proposed future response shape (not an implemented 200 response):
  ```json
  {
    "root_symbol_id": 101,
    "max_depth": 3,
    "affected_nodes": [
      {
        "symbol_id": 204,
        "name": "SymbolScanner.scan",
        "depth": 1,
        "reachability_confidence": 0.8
      }
    ]
  }
  ```

### 4. Search & GraphRAG Q&A
`POST /api/repos/{id}/search`
- **Request Body:**
  ```json
  {
    "q": "symbol resolver call pass",
    "mode": "hybrid"
  }
  ```
- **Response 200 OK:**
  ```json
  {
    "query": "symbol resolver call pass",
    "hits": [
      {
        "symbol_id": 101,
        "name": "SymbolResolver.resolve_calls",
        "score": 0.032,
        "file_path": "backend/reposcope/parsing/resolver.py",
        "snippet": "def resolve_calls(self, ast_tree):"
      }
    ]
  }
  ```

`POST /api/repos/{id}/ask`
- **Request Body:**
  ```json
  {
    "question": "How does the scope resolution pass handle call expressions?"
  }
  ```
- **Response 200 OK:**
  ```json
  {
    "answer": "The scope resolver matches function calls against the symbol table [E1].",
    "evidence": [
      {
        "evidence_id": "E1",
        "snapshot_id": 1,
        "file_id": 12,
        "file_path": "backend/reposcope/parsing/resolver.py",
        "symbol_id": 101,
        "chunk_id": 5,
        "start_line": 142,
        "end_line": 160,
        "text": "def resolve_calls(self, ast_tree): ..."
      }
    ],
    "gaps": []
  }
  ```

### 5. PR Impact & Action Recommendations
`POST /api/repos/{id}/pr-impact`
- **Request Body:**
  ```json
  {
    "pr_url": "https://github.com/owner/repo/pull/42"
  }
  ```
- **Response 200 OK:**
  ```json
  {
    "pr_url": "https://github.com/owner/repo/pull/42",
    "risk_level": "LOW",
    "risk_score": 0.04,
    "files_changed_count": 3,
    "impacted_symbols_count": 14,
    "affected_endpoints_count": 0,
    "impacted_tests_count": 2,
    "summary": "Modifies internal helper methods in resolver.py without API signature breaking changes."
  }
  ```

`GET /api/repos/{id}/recommendations?k={int}`
- **Response 200 OK:**
  ```json
  {
    "recommendations": [
      {
        "id": 1,
        "snapshot_id": 1,
        "symbol_id": 101,
        "category": "UNTESTED_HOTSPOT",
        "title": "Add unit test for SymbolResolver.resolve_calls",
        "description": "High fan-in symbol lacks direct unit test coverage.",
        "score": 0.94,
        "confidence": 0.9
      }
    ]
  }
  ```

`POST /api/recs/{id}/feedback`
- **Request Body:**
  ```json
  {
    "action": "accepted"
  }
  ```
- **Response 200 OK:**
  ```json
  {
    "status": "ok",
    "id": 1,
    "action": "accepted"
  }
  ```

## Mock dataset provenance

The repository example names nishtha911/RepoScope and pins the verified historical commit
`d631c3f98581ab3ebdb0c8daa28cc8bf122f749a` from that repository. This is not a live HEAD lookup.
The counts, snapshot/file/symbol/chunk IDs, symbol paths, source snippets, graph relationships,
recommendations and PR risk values are synthetic mock examples, not extracted facts about
that commit. Do not treat the 142/3412 counters as measured repository statistics.
Registration returns an acknowledgment only: no actual ingestion job is queued.
Search/Q&A/PR-impact/recommendation responses do not execute retrieval, an LLM, diff analysis,
or persistence. This contract mock is for interface development, not real code intelligence.
The symbol-impact endpoint remains planned; its shown future shape is not currently returned.
A request to it currently receives the ordinary 404 NOT_FOUND envelope, not fabricated analysis.
NOT_IMPLEMENTED is mapped for future explicit HTTP 501 stubs; adding the mapping does not
create an impact route or change the planned endpoint from 404 to 501.
