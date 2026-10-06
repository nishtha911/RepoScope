# RepoScope â€” Codebase Intelligence Assistant

**Project Build Plan v2.0**  
Repository: `github.com/your-org/RepoScope`

---

## 1. Project Snapshot

### Core Specifications

| Category | Specification |
| :--- | :--- |
| **Core Architecture** | Typed AST Code Graph, Hybrid Retrieval (Vector + BM25/FTS), GraphRAG, Deterministic PR Blast Radius |
| **Backend & Data** | Python 3.11+, FastAPI, Neon PostgreSQL 16+ (`pgvector` + `pg_trgm`), Tree-sitter, NetworkX, SQLAlchemy 2.0, Alembic |
| **AI & Orchestration** | LangGraph (thin orchestration), Google Gemini 1.5 Flash (Synthesis), Groq (Routing / Intent), `BAAI/bge-small-en-v1.5` |
| **Frontend** | React 18 / Next.js 14 (TypeScript), Tailwind CSS, React Flow / Cytoscape.js, Lucide Icons, Radix UI |
| **Deployment** | Neon (PostgreSQL + `pgvector`), Render / Fly.io (FastAPI & background workers), Vercel (Frontend SPA) |
| **Commitment** | Maximum 2 hours per day per contributor (~10â€“12 hours/week) |
| **Deadlines** | Iterative, quality-first delivery: **Phase 1 MVP live by Day 18**; **Phase 2 live by Day 30** |

### Track Responsibilities

* **Track 1: Code Intelligence (Backend & Graph Store)**  
  AST Parsers, Name & Scope Resolver, Graph Store, Ingestion Pipeline, Incremental Updates, PR Impact Core.
* **Track 2: Retrieval, Ranking & Eval (ML & Context Engine)**  
  Symbol Chunking, `pgvector` indexing, Lexical Search, Reciprocal Rank Fusion (RRF), GraphRAG, Citation Validator, LightGBM Recommender, Evaluation Harness.
* **Track 3: Agents, Product & Web (Full-Stack & Orchestration)**  
  FastAPI Endpoints, LangGraph Multi-Agent Workflows, UI Components, Interactive Visualizations, GitHub Client, Staging/Production Deployment.

---

## 2. Build Structure & Scope Overview

The project is executed in two sequential phases with a strict two-hour daily budget per contributor:

* **Phase 1 (Days 1â€“18) â€” V1 MVP:** Ingestion, typed AST graph, hybrid retrieval, GraphRAG Q&A with verified citations, deterministic PR impact, heuristic action recommendations, and staging/production launch.
* **Phase 2 (Days 19â€“30) â€” V2 Extensions:** LangGraph multi-agent orchestration, LightGBM LambdaRank recommender, interactive graph visualizer, fault-injection resilience, automated CI evaluation gates, and portfolio-ready v2.0 release.

### Feature Scope Comparison

| V1 Features (MVP) | V2 Extensions |
| :--- | :--- |
| â€¢ Safe shallow Git ingestion & secret redaction<br>â€¢ Tree-sitter Python symbol extraction<br>â€¢ 2-pass call/import resolver<br>â€¢ PostgreSQL + `pgvector` hybrid search<br>â€¢ Graph-expanded RAG with Evidence Pack<br>â€¢ Hallucination & citation validation<br>â€¢ Deterministic PR impact & blast radius<br>â€¢ Heuristic action recommender<br>â€¢ Minimal web workspace (Search, Chat, PR View) | â€¢ LangGraph multi-agent orchestrator (Analyst, Impact, Test Agents)<br>â€¢ LightGBM LambdaRank action recommender<br>â€¢ Interactive graph visualizer (React Flow / Cytoscape.js)<br>â€¢ Category multiplier feedback priors<br>â€¢ Automated CI evaluation suite (`make eval`)<br>â€¢ Fault injection & provider fallback (Gemini $\leftrightarrow$ Groq)<br>â€¢ Production hardening, keyboard shortcuts & dark mode |

---

## 3. Phase 1 â€” V1 Product (Days 1 â€“ 18)

> **Objective:** Deploy a publicly accessible, feature-complete MVP with core code intelligence, GraphRAG, and deterministic PR impact analysis operational.

### Week 1: Foundation, Contracts, Ingestion & Parsing (Days 1â€“5)

#### Day 1: Repository Setup, Contracts & Core Environment
* **Track 1 (Code Intelligence):** Setup repo layout (`src/RepoScope`, `web/`, `evaluation/`, `tests/`). Provision Neon PostgreSQL 16 project (`pgvector`, `pg_trgm`). Write initial SQLAlchemy models and Alembic migration for repositories, files, symbols, and edges.
* **Track 2 (Retrieval & ML):** Initialize embedding runtime spike (`sentence-transformers` with `bge-small-en-v1.5`). Define shared Pydantic data schemas in `contracts/` (`Symbol`, `Edge`, `Chunk`, `Evidence`, `Finding`). Pin 5 evaluation repos in `repos.lock`.
* **Track 3 (Agents & Web):** Initialize React 18 project with Vite, Tailwind CSS, Lucide icons, and React Query. Setup FastAPI project with CORS, error envelope, and `/api/health`. Create OpenAPI mock server and document schemas in `/docs/api-contract.md`.
* **Day Milestone:** [âœ”] Neon Postgres + `pgvector` provisioned; shared Pydantic contracts frozen; React + Vite app and mock API active.

#### Day 2: Fixtures, Ingestion Pipeline & UI Shell
* **Track 1 (Code Intelligence):** Build shallow git clone service with depth $= 1$, hook suppression (`core.hooksPath=/dev/null`), and symlink guards. Implement file scanner, extension detector, and SHA-256 content hasher.
* **Track 2 (Retrieval & ML):** Hand-curate `tests/fixtures/mini_repo/` (15 Python files with known classes, imports, functions, decorators, tests). Build hand-verified `golden_graph.json` fixture to unblock Tracks 2 & 3.
* **Track 3 (Agents & Web):** Build global layout: `AppSidebar`, `RepoSelector`, `NavigationTabs` (Explorer, Chat, PR Review, Actions). Connect dashboard to mock endpoints using React Query and mock data fixtures.
* **Day Milestone:** [âœ”] Safe clone & ingestion engine operational; `mini_repo` fixture and `golden_graph.json` committed.

#### Day 3: AST Extraction, Symbol Chunking & Repository Dashboard
* **Track 1 (Code Intelligence):** Setup Tree-sitter with `tree-sitter-python`. Build AST walker extracting symbols: modules, classes, functions, methods, parameters, signatures, docstrings, and cyclomatic complexity.
* **Track 2 (Retrieval & ML):** Implement symbol-based chunker (`chunker.py`): create one chunk per symbol with qualified name, signature, docstring, and body; guarantee no function is split across chunks.
* **Track 3 (Agents & Web):** Build Repository Registration modal (`POST /api/repos`) with clone progress spinner and indexing status badge. Build File Tree component displaying repository hierarchy.
* **Day Milestone:** [âœ”] Tree-sitter extracts all symbols from `mini_repo`; chunker produces symbol chunks with header context.

#### Day 4: Name & Scope Resolver, Vector Indexing & Symbol Search UI
* **Track 1 (Code Intelligence):** Implement Pass 1 (repo module map + local symbol table) and Pass 2 (reference resolver) resolving calls, imports, and base classes to `EXACT`, `INFERRED`, `AMBIGUOUS`, or `UNRESOLVED`.
* **Track 2 (Retrieval & ML):** Implement batched embedding pipeline with `bge-small-en-v1.5` writing to `chunks` table. Setup pgvector HNSW index ($m=16$, $ef=64$). Write similarity search query filtered by `repo_id`.
* **Track 3 (Agents & Web):** Build Symbol Search component with debounce, kind badges (Function, Class, Endpoint), and line-number links. Connect to `GET /api/repos/{id}/symbols?q=` mock endpoint.
* **Day Milestone:** [âœ”] Name resolver produces typed edges with confidence scores; symbol embeddings stored and queried via pgvector.

#### Day 5: Graph Storage, Lexical Search & Code Viewer
* **Track 1 (Code Intelligence):** Implement `GraphStore` in PostgreSQL: bulk insert symbols and edges. Validate extraction and edge generation against `golden_graph.json` with an exact match test.
* **Track 2 (Retrieval & ML):** Build identifier-splitting lexical search: split `camelCase` and `snake_case` tokens into `tsvector`; write PostgreSQL `ts_rank_cd` search queries over symbol names and bodies.
* **Track 3 (Agents & Web):** Build syntax-highlighted `CodeViewer` component with line highlighting and breadcrumb path display. Add empty-state and error-boundary components.
* **Day Milestone:** [âœ”] Code graph stored in PostgreSQL matching golden test; lexical identifier search active.

---

### Week 2: Graph Traversal, Hybrid Search & GraphRAG (Days 6â€“10)

#### Day 6: Graph Traversal Engine, RRF Hybrid Fusion & Neighborhood Viewer
* **Track 1 (Code Intelligence):** Implement recursive CTE query and NetworkX loader for bounded reverse reachability (depth $\le 4$) with confidence decay:
  $$\text{score} = \prod e.\text{confidence} \times 0.8^{\text{depth}-1}$$
* **Track 2 (Retrieval & ML):** Implement Reciprocal Rank Fusion (RRF) combining symbol exact match, lexical search, and vector ANN hits:
  $$\text{RRF}(d) = \sum_{m \in M} \frac{1}{60 + r_m(d)}$$
* **Track 3 (Agents & Web):** Build Symbol Detail page: metadata panel (lines, complexity, signature) and 1-hop upstream/downstream callers list. Wire to `GET /api/symbols/{id}/neighbors`.
* **Day Milestone:** [âœ”] Reverse graph traversal executes in SQL; RRF hybrid search fuses lexical and vector rankings.

#### Day 7: Derived Edges, Graph Expansion & Search Integration
* **Track 1 (Code Intelligence):** Implement specialized detectors for web frameworks and databases: FastAPI/Flask route decorators (`EXPOSES` edges) and SQLAlchemy/SQLModel models (`USES` edges).
* **Track 2 (Retrieval & ML):** Implement intent-based graph expansion (`graph_expand.py`): take top 8 fused seeds and expand along relevant typed edges (callers, callees, parent classes, endpoints) up to depth 2.
* **Track 3 (Agents & Web):** Wire global search bar to live `POST /api/repos/{id}/search` endpoint. Support tab filters: All, Symbols, Documentation, Endpoints. Display latency metrics in UI.
* **Day Milestone:** [âœ”] API routes and database models linked in graph; hybrid search expanded with structural neighbors.

#### Day 8: Test Linking, Context Pack & Prompts, Chat Interface
* **Track 1 (Code Intelligence):** Implement static test detector: map `test_*.py` functions to code symbols using 2-hop call paths and naming heuristics, creating `TESTED_BY` edges.
* **Track 2 (Retrieval & ML):** Build Evidence Pack serializer: assign stable IDs (`E1`, `E2`), assemble metadata, format code signatures/bodies, and append `[GAP]` records. Construct spotlighted prompt template.
* **Track 3 (Agents & Web):** Build Codebase Chat interface with streaming message bubbles, Markdown parsing, and expandable citation pill badges (`[E1]`, `[E2]`).
* **Day Milestone:** [âœ”] Test files linked to implementation symbols; evidence pack serializer formats structured context.

#### Day 9: Incremental Indexer, Citation & Symbol Validator, Citation Drawer
* **Track 1 (Code Intelligence):** Implement incremental graph updater: on file changes, identify dirty files, drop old cascading symbols/edges, re-parse and re-resolve affected edges without full rebuild.
* **Track 2 (Retrieval & ML):** Build post-generation Validator: verify every cited `evidence_id` exists; verify all mentioned symbols exist in `symbols` table; gate negative claims against unresolved edge count.
* **Track 3 (Agents & Web):** Implement interactive Citation Drawer: clicking citation pills (`[E1]`) slides open the exact file, lines, relationship type, and confidence score.
* **Day Milestone:** [âœ”] Incremental graph updates verified; hallucination & citation validator enforces groundedness.

#### Day 10: Git Churn Stats, LLM Client & Fallback, Ask API Integration
* **Track 1 (Code Intelligence):** Implement `gitstats.py`: extract 90-day commit count, distinct authors, last modified date, and bugfix commit frequency per file into `git_stats` table.
* **Track 2 (Retrieval & ML):** Build unified `LLMClient` with Gemini (long context, JSON schema) and Groq (fast classification), response caching by hash (`prompt + evidence`), and retry backoff.
* **Track 3 (Agents & Web):** Connect Chat UI to live `POST /api/repos/{id}/ask` endpoint. Add timing break-down footer (retrieval ms, expansion ms, LLM synthesis ms).
* **Day Milestone:** [âœ”] Git churn history extracted; GraphRAG `/ask` pipeline fully connected end-to-end with citation checking.

---

### Week 3: PR Impact Engine, Action Recommender & QA (Days 11â€“15)

#### Day 11: Diff Parser & Symbol Mapper, Candidate Detectors, PR Submission UI
* **Track 1 (Code Intelligence):** Build unified diff parser using `unidiff`. Map changed line ranges to base and head symbols. Classify modifications: `ADDED`, `REMOVED`, `SIGNATURE_CHANGED`, `BODY_CHANGED`.
* **Track 2 (Retrieval & ML):** Implement recommender candidate detectors: Untested High Fan-in Symbols, Cyclomatic Complexity Hotspots, and API Endpoint Documentation Gaps.
* **Track 3 (Agents & Web):** Build PR Impact submission interface: input GitHub PR URL or paste raw git patch. Add recent analysis history table.
* **Day Milestone:** [âœ”] Git diffs parsed and classified at symbol level; initial candidate detectors emitting findings.

#### Day 12: PR Blast Radius Traversal, Heuristic Scorer, Blast Radius UI
* **Track 1 (Code Intelligence):** Build multi-source reverse BFS over modified symbols through `CALLS`, `INHERITS`, and `USES` edges. Traverse affected endpoints (`EXPOSES`) and database models with weight decay.
* **Track 2 (Retrieval & ML):** Build heuristic feature scorer: compute impact, likelihood, and effort features per finding. Calculate priority score:
  $$\text{score} = \frac{\text{impact} \times \text{likelihood}}{\text{effort}} \times \text{confidence}$$
* **Track 3 (Agents & Web):** Build PR Overview UI: display risk level badge (Low, Medium, High, Critical), impacted files count, impacted symbols count, and affected endpoints count.
* **Day Milestone:** [âœ”] Multi-source blast radius engine maps change ripple effects; heuristic scorer ranks codebase findings.

#### Day 13: Risk Score & Test Gap Engine, Recommender API, Recommendations UI
* **Track 1 (Code Intelligence):** Compute deterministic risk score: combine blast radius (30%), sensitivity (20%), test gap (20%), contract changes (15%), complexity delta (10%), and size (5%). Identify untested modified symbols.
* **Track 2 (Retrieval & ML):** Build LLM rationale generator: create concise explanation per finding strictly citing computed feature values. Expose `GET /api/repos/{id}/recommendations`.
* **Track 3 (Agents & Web):** Build "What to Work on Next" recommendations board: list top 10 ranked findings with category tags, impact badges, and rationale dropdowns.
* **Day Milestone:** [âœ”] Deterministic risk score and test gap analyzer complete; recommendations board renders ranked findings.

#### Day 14: PR Report Serialization, Eval Dataset D, Feedback & Test View
* **Track 1 (Code Intelligence):** Generate structured `pr_analyses` JSON report. Wire LLM summarizer to generate executive review summary strictly grounded in report evidence.
* **Track 2 (Retrieval & ML):** Assemble evaluation dataset $\mathcal{D}$ (30 historical PRs with known impacted files and test runs). Write offline benchmark runner for PR impact accuracy.
* **Track 3 (Agents & Web):** Build Impacted Tests & Endpoints view in PR page: show relevant tests, missing tests, and affected routes with confidence scores. Add Feedback buttons (Accept / Dismiss).
* **Day Milestone:** [âœ”] Full PR analysis pipeline complete from URL to risk report; recommender feedback buttons active.

#### Day 15: Ingestion Hardening, Ablation Baseline B0, UI Responsiveness
* **Track 1 (Code Intelligence):** Security pass: test `malicious_repo` fixture (symlinks, path traversal, decompression bombs, 10MB+ files). Ensure secret redaction cleans API keys and credentials before storage.
* **Track 2 (Retrieval & ML):** Implement Baseline B0 (naive fixed-size chunking + vector search only) in evaluation harness to benchmark against RepoScope hybrid GraphRAG.
* **Track 3 (Agents & Web):** Mobile responsiveness pass: verify all screens at 375px breakpoint (collapsible sidebar, responsive data tables, touch-friendly citation drawer). Add toast notifications for errors.
* **Day Milestone:** [âœ”] Security hardening verified against malicious repo; baseline B0 running in eval harness; mobile UI responsive.

---

### Week 4: Staging, Testing & Launch (Days 16â€“18)

#### Day 16: Staging Deployment & End-to-End Verification
* **Track 1 (Code Intelligence):** Connect to Neon staging database branch. Run Alembic migrations. Deploy worker service on Render staging and confirm background job queue processes repos properly.
* **Track 2 (Retrieval & ML):** Run full evaluation harness on staging database: record baseline Recall@10, Groundedness, and PR Impact recall. Verify caching works across repeated queries.
* **Track 3 (Agents & Web):** Deploy FastAPI backend to Render staging and React SPA to Vercel staging. Execute complete manual E2E test across all 4 workflows; log bugs as GitHub Issues.
* **Day Milestone:** [âœ”] All services deployed to staging; end-to-end user workflows verified against staging database.

#### Day 17: Staging Bug Fixes, Rate Limiting & API Hardening
* **Track 1 (Code Intelligence):** Fix P0/P1 bugs in graph builder and AST resolver identified during staging tests. Add memory limits and execution timeouts to ingestion workers.
* **Track 2 (Retrieval & ML):** Optimize database queries: review slow query logs, tune pgvector `ef_search`, add composite indexes on `edges (repo_id, dst_id, type)`.
* **Track 3 (Agents & Web):** Implement IP-based rate limiting on API (`slowapi`). Add friendly error states for rate-limited users and long-running ingest jobs. Resolve frontend display glitches.
* **Day Milestone:** [âœ”] Critical staging bugs resolved; database indexes tuned; rate limiters and error handlers active.

#### Day 18: Production Launch (V1 Feature Complete)
* **Track 1 (Code Intelligence):** Promote worker and Neon production database branch. Configure automated database backups and logging alerts.
* **Track 2 (Retrieval & ML):** Publish Phase 1 evaluation report: document Recall@10, citation accuracy, and baseline comparison table in `docs/eval-report.md`.
* **Track 3 (Agents & Web):** Promote React build to production domain on Vercel. Update repository README with architecture diagram, feature overview, setup instructions, and demo screenshots. Tag `v1.0.0`.
* **Day Milestone:** [âœ”] V1 live in production â€” Ingestion, Hybrid GraphRAG, and Deterministic PR Impact operational!

---

## 4. Phase 2 â€” V2 Extensions (Days 19 â€“ 30)

> **Objective:** Layer LangGraph multi-agent orchestration, LightGBM learning-to-rank recommendations, interactive graph visualizations, and automated CI evaluation gates.

### Days 19â€“20: LangGraph Multi-Agent Orchestrator

#### Day 19: Agent State & Tool Registry
* **Track 1 (Code Intelligence):** Implement read-only tool access layer for agents: `symbol_lookup`, `graph_impact`, `find_tests`, `get_code`, and `get_diff` with strict argument validation.
* **Track 2 (Retrieval & ML):** Build Agent intent router (using Groq for low latency): classify queries into `where_is`, `explain_arch`, `impact`, `tests`, `pr_review`, or `other`.
* **Track 3 (Agents & Web):** Define `AgentState` schema in LangGraph: typed state containing question, plan, entities, evidence store, tool call history, and step budget counters.
* **Day Milestone:** [âœ”] Tool interfaces secured; LangGraph typed state and fast Groq intent classifier operational.

#### Day 20: Specialized Agents & SSE Streaming
* **Track 1 (Code Intelligence):** Build Repository Analyst agent node (module-level architecture summarisation) and Impact Analysis agent node (iterative blast radius exploration).
* **Track 2 (Retrieval & ML):** Wire Test Analysis agent node (gap identification) and implement evidence pack synthesis node with hallucination validation retry loops.
* **Track 3 (Agents & Web):** Expose `POST /api/repos/{id}/agent/run` with Server-Sent Events (`GET /runs/{id}/events`). Build UI Agent Activity panel streaming tool execution steps.
* **Day Milestone:** [âœ”] Multi-agent workflows functional; live agent reasoning and tool executions stream to UI over SSE.

---

### Days 21â€“23: LightGBM Recommender, Graph Explorer & Fault Injection

#### Day 21: Historical Label Mining, LambdaRank Training & Graph Canvas Spike
* **Track 1 (Code Intelligence):** Mine historical training labels from git log: identify past bug-fix commits touching functions within 90 days after commit $T$, creating graded labels ($0, 1, 2$).
* **Track 2 (Retrieval & ML):** Train LightGBM LambdaRank model on mined historical features (churn, complexity, fan-in, test links). Measure NDCG@10 on temporal holdout split.
* **Track 3 (Agents & Web):** Spike React Flow / Cytoscape.js interactive graph canvas: render symbol nodes and directed relationship edges with layout physics.
* **Day Milestone:** [âœ”] Historical training labels mined without time leakage; LightGBM LambdaRank trained; graph canvas spiked.

#### Day 22: Feedback Personalization & Interactive Graph Explorer
* **Track 1 (Code Intelligence):** Implement user feedback persistence in `feedback` table (`accepted`, `dismissed`, `not_useful`). Calculate category multiplier priors: $\text{prior} \in [0.5, 1.5]$.
* **Track 2 (Retrieval & ML):** Integrate trained LightGBM ranker into recommendations pipeline with heuristic cold-start fallback. Validate that rationales strictly reference real feature numbers.
* **Track 3 (Agents & Web):** Build Interactive Graph Explorer page: visual graph exploration with zoom, pan, node expansion on click, and edge filters (Calls, Inherits, Exposes).
* **Day Milestone:** [âœ”] Learning-to-rank recommender live with feedback adaptation; interactive Graph Explorer functional.

#### Day 23: Fault Injection, Degraded States & Resilience Testing
* **Track 1 (Code Intelligence):** Build resilience test suite: inject simulated tool timeouts, empty graph returns, and database query latency; verify orchestrator degrades gracefully.
* **Track 2 (Retrieval & ML):** Implement LLM provider fallback: automatically switch from Gemini to Groq or cached responses on HTTP 429 rate limit. Output structured degraded responses.
* **Track 3 (Agents & Web):** Build Degraded State UI indicators: show warning banners when viewing cached results or incomplete graph traversals due to step budget exhaustion.
* **Day Milestone:** [âœ”] Fault-injection suite verifies graceful degradation; automated LLM provider fallback active.

---

### Days 24â€“27: Automated Evaluation, Security Audit & Polish

#### Day 24: Automated CI Eval Gate & Ablation Matrix
* **Track 1 (Code Intelligence):** Build oracle comparison script (`graph_oracle.py`): evaluate extracted code graph against Jedi/ast ground truth on 2 repos, measuring edge precision and recall.
* **Track 2 (Retrieval & ML):** Build complete ablation suite in `evaluation/runners/`: benchmark B0 (Naive RAG) vs B1 (Lexical) vs B2 (Vector) vs B3 (Hybrid) vs B4 (GraphRAG) vs B5 (Agent).
* **Track 3 (Agents & Web):** Add GitHub Actions CI workflow: run linter (`ruff`), type checker (`mypy`), boundary check (`import-linter`), and `make eval-fast`.
* **Day Milestone:** [âœ”] Automated CI evaluation gate active; full retrieval and extraction ablation matrix generated.

#### Day 25: Prompt Injection Hardening & Security Audit
* **Track 1 (Code Intelligence):** Execute security test suite against `injection_repo` fixture: verify that prompt injections in comments or READMEs cannot hijack tool execution or leak system prompts.
* **Track 2 (Retrieval & ML):** Audit and verify citation validator: run test suite ensuring answers with hallucinated symbol names or invalid evidence IDs are rejected and regenerated.
* **Track 3 (Agents & Web):** Audit frontend security: verify Markdown renderer sanitizes HTML to prevent XSS. Enforce strict Content Security Policy (CSP) headers in hosting configuration.
* **Day Milestone:** [âœ”] Security test suite passes; prompt injection resistance confirmed; frontend XSS protections active.

#### Day 26: Dark Mode, Keyboard Shortcuts & Performance Audit
* **Track 1 (Code Intelligence):** Audit and tune backend API latency: ensure hybrid retrieval completes in $< 200\text{ ms}$ and reverse graph traversals complete in $< 100\text{ ms}$.
* **Track 2 (Retrieval & ML):** Run offline evaluation on held-out repositories (never used during prompt or feature tuning). Generate final metric tables for the project documentation.
* **Track 3 (Agents & Web):** Implement dark mode with Tailwind `dark:` classes and persistent state. Add global keyboard shortcuts (`Cmd/Ctrl + K` for search, `/` for chat).
* **Day Milestone:** [âœ”] Backend latency optimized; final held-out evaluation numbers recorded; dark mode and shortcuts live.

#### Day 27: Full System Regression & E2E Bug Sweep
* **Track 1 (Code Intelligence):** Run full pytest suite across ingestion, parsing, graph, and PR impact modules. Confirm 100% test pass rate across all unit and integration tests.
* **Track 2 (Retrieval & ML):** Run full `make eval` harness: produce final `docs/eval-report.md` with Groundedness, Recall@10, NDCG@10, and Citation Accuracy scores.
* **Track 3 (Agents & Web):** Conduct complete cross-browser and device testing across all features (Graph, PR Impact, Chat, Recommendations). Resolve all open minor issues.
* **Day Milestone:** [âœ”] Full regression suite passes; evaluation report committed with verified numbers; zero open P0/P1 bugs.

---

### Days 28â€“30: V2 Launch, Demo & Showcase

#### Day 28: V2 Production Deployment
* **Track 1 (Code Intelligence):** Deploy updated production backend services. Verify database connection pools, background worker processes, and healthcheck alerts on Render/Fly.io.
* **Track 2 (Retrieval & ML):** Confirm production LLM caching and rate limiting are operating smoothly with telemetry monitoring.
* **Track 3 (Agents & Web):** Deploy production React / Next.js build on Vercel. Verify live domain SSL, OpenGraph meta tags, and error monitoring. Tag release `v2.0.0`.
* **Day Milestone:** [âœ”] RepoScope v2.0 live in production â€” Multi-Agent Codebase Intelligence accessible on the public web!

#### Day 29: Demo Recording & Seed Repositories
* **Track 1 (Code Intelligence):** Pre-index 3 popular open-source repositories (e.g. FastAPI, Requests, Flask) on production database so live visitors experience instant search and analysis.
* **Track 2 (Retrieval & ML):** Validate that pre-indexed demo repositories return pre-warmed, instantaneous responses across sample questions and PR impact queries.
* **Track 3 (Agents & Web):** Record high-definition 60-second walkthrough video. Create animated showcase GIF for the GitHub README header.
* **Day Milestone:** [âœ”] Demo repositories pre-indexed and pre-warmed; 60-second showcase video and demo GIF recorded.

#### Day 30: Documentation, Showcase Launch & Retrospective
* **Track 1 (Code Intelligence):** Complete `docs/architecture.md` and document AST resolution edge-cases and future TypeScript roadmap. Archive completed feature branches.
* **Track 2 (Retrieval & ML):** Finalize `docs/eval-report.md` with baseline comparison charts and error analysis. Document reproduction steps for `make eval`.
* **Track 3 (Agents & Web):** Finalize repository README: architecture diagram, verified metric badges, live demo URL, quickstart instructions, and LinkedIn launch post.
* **Day Milestone:** [âœ”] Project completed as a portfolio-grade open-source system; all documentation published.

---

## 5. Technology Stack Reference

```
                             â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                             â”‚       React 18 / Next.js        â”‚
                             â”‚  Tailwind CSS Â· React Flow UI   â”‚
                             â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                              â”‚ HTTP / SSE
                                              â–¼
                             â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                             â”‚      FastAPI Gateway (v2)       â”‚
                             â”‚   slowapi Â· Pydantic Schemas    â”‚
                             â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
                                     â”‚                 â”‚
            â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
            â–¼                                                                   â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                                           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  Track 1: Intelligenceâ”‚                                           â”‚ Track 2: RAG & Eval   â”‚
â”‚ â€¢ Tree-sitter AST     â”‚                                           â”‚ â€¢ BAAI/bge-small-en   â”‚
â”‚ â€¢ 2-Pass Scope Map    â”‚                                           â”‚ â€¢ RRF Fusion (k=60)   â”‚
â”‚ â€¢ NetworkX Multi-BFS  â”‚                                           â”‚ â€¢ Gemini & Groq APIs  â”‚
â”‚ â€¢ Git Diff / unidiff  â”‚                                           â”‚ â€¢ LightGBM LambdaRank â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                           â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
            â”‚                                                                   â”‚
            â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                     â–¼                 â–¼
                             â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                             â”‚       Neon PostgreSQL 16+       â”‚
                             â”‚  pgvector Â· pg_trgm Â· Alembic   â”‚
                             â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Stack Breakdown by Track

| Component | Track 1: Code Intelligence | Track 2: Retrieval, Ranking & Eval | Track 3: Agents, Product & Web |
| :--- | :--- | :--- | :--- |
| **Language & Runtime** | Python 3.11+ | Python 3.11+ | TypeScript, Node 18+ / Python 3.11+ |
| **Libraries / Frameworks** | Tree-sitter (`tree-sitter-python`), NetworkX, `unidiff`, Git CLI (`--depth=1`) | `sentence-transformers`, `scikit-learn`, `lightgbm`, PostgreSQL `ts_rank_cd` | React 18 / Next.js 14, Tailwind CSS, Lucide Icons, Radix UI, React Flow / Cytoscape.js |
| **Data & Storage** | Neon PostgreSQL 16, SQLAlchemy 2.0, Alembic, PostgreSQL Recursive CTEs | Neon `pgvector` (HNSW cosine index, $m=16, ef=64$), PostgreSQL FTS (`tsvector`) | TanStack React Query v5, Zustand, Redis / in-memory cache |
| **AI / Orchestration** | AST traversal & heuristics | Gemini 1.5 Flash (synthesis), Groq (classification/routing), `bge-small-en-v1.5` (384-d) | LangGraph (thin typed state machine), Server-Sent Events (SSE) |
| **Testing & CI** | `pytest`, `pytest-mock`, `ruff`, `mypy`, `import-linter` | Custom harness (`evaluation/`), Recall@K, MRR, NDCG@10, Groundedness Judge | Playwright / Vitest, GitHub Actions CI |
| **Hosting & Deploy** | Render / Fly.io (Worker loop with `FOR UPDATE SKIP LOCKED`) | Local embedding execution / Model APIs | Vercel (Frontend SPA), Render / Fly.io (FastAPI) |

---

## 6. API Contract

Agreed upon on Day 1 and documented in `/docs/api-contract.md`.  
All responses use **JSON**.

### Standard Failure Response Envelope
```json
{
  "error": {
    "code": "<ERROR_CODE>",
    "message": "<Human-readable message>",
    "details": {},
    "status": 400
  }
}
```

### Endpoints Specification

| Endpoint | Method | Request / Query | Response / Returns |
| :--- | :--- | :--- | :--- |
| `/api/health` | `GET` | â€” | `{"status": "ok", "v": "1.0"}` |
| `/api/repos` | `POST` | `{"url": string}` | Enqueues clone job; returns `{"repo_id": int, "status": "pending"}` |
| `/api/repos/{id}` | `GET` | â€” | Repository status, default branch, SHA, symbol and file counts |
| `/api/repos/{id}/symbols` | `GET` | `?q=str&kind=str&limit=20` | Matching symbols with `name`, `qualname`, `kind`, `file`, and `line_range` |
| `/api/symbols/{id}` | `GET` | â€” | Detailed symbol info: signature, docstring, source, cyclomatic complexity |
| `/api/symbols/{id}/neighbors`| `GET` | `?dir=in\|out&types=str` | Directed neighbors (callers, callees, base classes, endpoints) |
| `/api/symbols/{id}/impact` | `GET` | `?depth=3` | Reverse blast radius reachability tree with confidence scores |
| `/api/repos/{id}/search` | `POST` | `{"q": string, "mode": "hybrid"}` | Ranked hits from RRF fusion across symbol exact match, lexical, and vector |
| `/api/repos/{id}/ask` | `POST` | `{"question": string}` | Answer with verified claims, citations (`[E1]`), and identified gaps (`[GAP]`) |
| `/api/repos/{id}/agent/run`| `POST` | `{"question": string}` | Starts LangGraph workflow; returns `{"run_id": "uuid"}` |
| `/api/runs/{id}/events` | `GET` | â€” | Server-Sent Events (SSE) stream of plan steps, tool calls, and thoughts |
| `/api/repos/{id}/pr-impact`| `POST` | `{"pr_url": string}` | PR impact report: risk score, blast radius, affected routes, impacted tests |
| `/api/repos/{id}/recommendations` | `GET` | `?k=10` | Top $K$ ranked developer actions with category, score, and feature-based rationale |
| `/api/recs/{id}/feedback` | `POST` | `{"action": "accepted"\|"dismissed"}` | Records user feedback to update category prior weights ($\text{prior} \in [0.5, 1.5]$) |

---

## 7. Git & Collaboration Workflow

### Branch Strategy

```
  main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â— [Production Release]
   â–²                                                                â”‚
   â”‚ (Sunday release gate after full CI regression)                 â”‚
   â”‚                                                                â–¼
   dev â”€â”€â”€â”€â”€â”€â”€â—â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â—â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â—â”€â”€â”€â”€â”€â”´â”€ [Integration]
              â–²                       â–²                       â–²
              â”‚ (PR approved)         â”‚ (PR approved)         â”‚ (PR approved)
     feature/t1-*            feature/t2-*            feature/t3-*
     (Track 1: Parser)       (Track 2: Search)       (Track 3: UI)
```

* `main`: Production branch. Protected. Direct pushes strictly prohibited. Deploys to production automatically. Merged from `dev` only after passing full CI and regression tests.
* `dev`: Active integration branch. Protected. Contributors merge day-level feature branches here via approved Pull Requests.
* `feature/t1-*`: Track 1 daily working branches (e.g. `feature/t1-treesitter-extractor`).
* `feature/t2-*`: Track 2 daily working branches (e.g. `feature/t2-hybrid-rrf-search`).
* `feature/t3-*`: Track 3 daily working branches (e.g. `feature/t3-pr-impact-ui`).

### Daily Workflow

1. **Start of session:** Run `git pull origin dev` and rebase your active feature branch.
2. **End of session:** Push feature branch and open a Pull Request targeting `dev`.
3. **Review rule:** No contributor merges their own PR. Every PR requires at least one approval from a contributor on a different track.
4. **Integration Gate:** CI must pass `ruff` (linting), `mypy` (type checking), `import-linter` (architecture layering), and `pytest` on all PRs.
5. **Sunday Release:** Every Sunday, `dev` is merged into `main`, triggering staging/production promotion.

### Communication & Escalation Protocol

* **Daily 5-minute async check-in:** Post to team channel:
  1. What was completed in yesterday's 2-hour window?
  2. What is planned for today?
  3. Are there any blocking contract or schema dependencies?
* **Issue Tracking:** All bugs, schema updates, and enhancements are tracked as GitHub Issues with labels: `track-1`, `track-2`, `track-3`, `P0-blocker`, `P1-feature`, `P2-polish`.
* **Blocker Escalation:** If a contributor is blocked on an API or contract for $> 1$ session, halt work on dependent code and use the pre-agreed Mock Server or `Fake*` classes. **Do not absorb blockers silently.**

---

## 8. Practical Notes for a Two-Hour Daily Budget

### 1. Use Golden Fixtures & Fakes Before Services Are Ready
During Days 1 to 5, Track 1 develops the real AST parser and graph store. Tracks 2 and 3 must not wait for this. Instead:
* Track 2 builds chunking and search against `mini_repo/golden_graph.json`.
* Track 3 builds UI components against the OpenAPI Mock Server.  
Using frozen contract fixtures eliminates cross-track blocking entirely during early sprints.

### 2. Recommended Two-Hour Session Structure

```
 0:00        0:10                                1:40        1:55    2:00
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Sync &    â”‚ Focused Implementation            â”‚ Test &    â”‚ Reviewâ”‚
â”‚ Unblock   â”‚ (90 minutes uninterrupted)        â”‚ Push PR   â”‚ & Log â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”˜
```

* **0:00 â€“ 0:10 (Sync & Unblock):** Review the day's milestone; check PR comments and confirm clean branch rebase.
* **0:10 â€“ 1:40 (Focused Build Time):** 90 minutes of dedicated implementation on the day's single milestone.
* **1:40 â€“ 1:55 (Testing & Push):** Run local tests, push branch, open Pull Request with a clear description.
* **1:55 â€“ 2:00 (Review & Board Update):** Review a peer's PR or update the shared GitHub Project board status.

### 3. Scope Discipline
Each daily allocation is strictly calibrated to two hours. If a task overruns, document the remaining work, commit the clean intermediate progress, and carry the remaining portion into the next day rather than pulling late-night marathons. Consistent, predictable daily progress produces higher code quality and better design decisions.

### 4. The Contracts and Fixtures are the Foundation
The single most critical action in Phase 0 (Day 1) is freezing the shared Pydantic contracts in `contracts/` and the OpenAPI schema. All three contributors must agree on entity types, field names, and data structures. Any modification to a shared contract requires a dedicated PR approved by all three contributors before code changes can be merged.