import type { CitationEvidence, ChatMessage } from '../types/chat';

export const fixtureEvidence: Record<string, CitationEvidence> = {
  E1: {
    evidence_id: 'E1',
    symbol_id: 101,
    name: 'SymbolResolver.resolve_calls',
    file_path: 'backend/reposcope/parsing/resolver.py',
    start_line: 45,
    end_line: 68,
    kind: 'function',
    signature: 'def resolve_calls(self, ast_tree: ast.AST) -> list[Edge]:',
    origin: 'seed',
    fused_score: 0.092,
    snippet: `def resolve_calls(self, ast_tree: ast.AST) -> list[Edge]:
    """Resolve calls in AST to target symbols using two-pass scope map."""
    calls: list[Edge] = []
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.Call):
            resolved = self._lookup_scope(node)
            if resolved:
                calls.append(Edge(src=self.current_symbol_id, dst=resolved.id, type="CALLS"))
    return calls`,
  },
  E2: {
    evidence_id: 'E2',
    symbol_id: 301,
    name: 'POST /api/repos/{id}/search',
    file_path: 'backend/reposcope/api/repos.py',
    start_line: 112,
    end_line: 140,
    kind: 'endpoint',
    signature: '@router.post("/repos/{repo_id}/search", response_model=SearchResponse)',
    origin: 'seed',
    fused_score: 0.081,
    snippet: `@router.post("/repos/{repo_id}/search", response_model=SearchResponse)
async def search_repo(repo_id: int, request: SearchRequest, db: Session = Depends(get_db)):
    """Execute hybrid reciprocal rank fusion search combining symbols, lexical BM25, and vector ANN."""
    results = await run_rrf_fusion(db=db, repo_id=repo_id, query=request.q, mode=request.mode)
    return SearchResponse(query=request.q, hits=results)`,
  },
  E3: {
    evidence_id: 'E3',
    symbol_id: 204,
    name: 'EvidencePack.coherent',
    file_path: 'backend/reposcope/rag/evidence_pack.py',
    start_line: 134,
    end_line: 151,
    kind: 'function',
    signature: 'def coherent(self) -> Self:',
    origin: 'expanded',
    fused_score: 0.065,
    snippet: `@model_validator(mode="after")
def coherent(self) -> Self:
    ids = [entry.source.evidence_id for entry in self.entries]
    if ids != [f"E{i}" for i in range(1, len(ids) + 1)]:
        raise ValueError("Evidence IDs must be contiguous in pack order")
    chunks = [entry.source.chunk_id for entry in self.entries]
    if None in chunks or len(set(chunks)) != len(chunks):
        raise ValueError("Each entry must identify a unique stored chunk")
    return self`,
  },
  E4: {
    evidence_id: 'E4',
    symbol_id: 405,
    name: 'reciprocal_rank_fusion',
    file_path: 'backend/reposcope/search/rrf.py',
    start_line: 18,
    end_line: 35,
    kind: 'function',
    signature: 'def reciprocal_rank_fusion(ranked_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:',
    origin: 'seed',
    fused_score: 0.088,
    snippet: `def reciprocal_rank_fusion(ranked_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Compute RRF score: RRF(d) = sum(1 / (k + rank)) across ranked retriever candidate lists."""
    scores: dict[int, float] = {}
    for rlist in ranked_lists:
        for rank, item_id in enumerate(rlist):
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank + 1))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)`,
  },
};

export const sampleStarterPrompts = [
  'How does the two-pass AST reference resolver work?',
  'Explain the hybrid RRF search fusion algorithm with formula.',
  'How does the evidence pack enforce contiguous citations [E1], [E2]?',
  'Where is the repository search endpoint implemented?',
];

export const initialChatMessages: ChatMessage[] = [
  {
    id: 'msg-welcome',
    role: 'assistant',
    content: `Hello! I am the **RepoScope Codebase Intelligence** assistant.

You can ask me questions about architecture, call graphs, search pipelines, or specific functions. Every claim I make is grounded directly in verified source chunks with expandable citation pills like [E1] or [E2].

Try asking:
- *"How does the two-pass AST reference resolver work?"*
- *"Explain the hybrid RRF search fusion algorithm with formula."*
- *"How does the evidence pack enforce contiguous citations?"*`,
    timestamp: Date.now() - 60_000,
    citations: {
      E1: fixtureEvidence.E1,
      E2: fixtureEvidence.E2,
    },
  },
];

export const fixturePromptResponses: Record<
  string,
  {
    content: string;
    citations: Record<string, CitationEvidence>;
    latencyMs: number;
  }
> = {
  default: {
    content: `### Architecture Analysis

RepoScope executes a multi-stage code intelligence workflow:

1. **Two-Pass AST Scope Mapping**:
   The AST scanner traverses Python syntax trees using Tree-sitter to build module-level and function-level symbol tables. The scoped resolver [E1] maps call sites to target definitions with verified confidence.

2. **Multi-Retriever Hybrid Search**:
   Requests dispatched to the search router [E2] execute Reciprocal Rank Fusion (RRF) with constant $k=60$ [E4], combining symbol exact matches, lexical BM25, and dense vector embeddings.

3. **Deterministic Evidence Packs**:
   Responses are synthesized with strict citation grounding [E3], preventing hallucination by guaranteeing that all cited IDs $[E1], [E2]$ reference real stored chunks.`,
    citations: fixtureEvidence,
    latencyMs: 142,
  },
  resolver: {
    content: `### Two-Pass Reference Resolver

In RepoScope, reference resolution operates in two distinct passes:

- **Pass 1 (Module Map & Local Symbols)**: Traverses each file to catalog top-level classes, functions, and import statements.
- **Pass 2 (Reference Resolution)**: As implemented in \`SymbolResolver.resolve_calls\` [E1], the resolver walks call expressions in the AST and performs hierarchical scope lookups:

\`\`\`python
def resolve_calls(self, ast_tree: ast.AST) -> list[Edge]:
    """Resolve calls in AST to target symbols using two-pass scope map."""
    calls: list[Edge] = []
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.Call):
            resolved = self._lookup_scope(node)
            if resolved:
                calls.append(Edge(src=self.current_symbol_id, dst=resolved.id, type="CALLS"))
    return calls
\`\`\`

Edges are classified into:
- **EXACT**: Unambiguous local or imported symbol match (confidence $1.0$).
- **INFERRED**: Matched via heuristic attribute or type propagation ($0.8$).
- **AMBIGUOUS**: Multiple potential targets matching the identifier ($0.5$).
- **UNRESOLVED**: External library or dynamic dispatch ($0.0$).`,
    citations: {
      E1: fixtureEvidence.E1,
    },
    latencyMs: 118,
  },
  search: {
    content: `### Reciprocal Rank Fusion (RRF) Search

The hybrid search endpoint [E2] fuses multiple retrieval channels without requiring arbitrary score normalization:

$$RRF(d) = \\sum_{m \\in M} \\frac{1}{k + r_m(d)}$$

Where:
- $M$ is the set of retrievers: **Exact Symbol**, **Lexical BM25**, and **Vector ANN**.
- $r_m(d)$ is the 1-based rank position of document $d$ in retriever $m$.
- $k = 60$ is the smoothing constant that prevents top-ranked items from dominating disproportionately [E4].

\`\`\`python
def reciprocal_rank_fusion(ranked_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for rlist in ranked_lists:
        for rank, item_id in enumerate(rlist):
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank + 1))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
\`\`\`

This ensures robust ranking even when vector similarity scores and BM25 scores have incompatible scales.`,
    citations: {
      E2: fixtureEvidence.E2,
      E4: fixtureEvidence.E4,
    },
    latencyMs: 135,
  },
  evidence: {
    content: `### Evidence Pack Validation Contract

RepoScope guarantees that citations are strictly grounded and never hallucinated. In \`EvidencePack.coherent\` [E3]:

1. **Contiguous Citation IDs**: Evidence identifiers must follow the strict contiguous sequence \`[E1], [E2], ... [En]\`. Any missing or out-of-order ID triggers immediate validation rejection.
2. **Unique Chunk Mapping**: Each cited evidence item must map to a unique physical chunk in PostgreSQL.
3. **Snapshot Consistency**: All evidence items and graph context must share the identical commit snapshot ID.

Whenever a claim cannot be verified against retrieved chunks, the serializer emits an explicit \`[GAP]\` tag rather than guessing.`,
    citations: {
      E3: fixtureEvidence.E3,
    },
    latencyMs: 98,
  },
};
