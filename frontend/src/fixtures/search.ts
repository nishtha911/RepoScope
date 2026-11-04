import type { SearchHit } from '../api/search';

export const fixtureSearchHits: SearchHit[] = [
  {
    symbol_id: 101,
    name: 'SymbolResolver.resolve_calls',
    score: 0.092,
    file_path: 'backend/reposcope/parsing/resolver.py',
    snippet:
      'def resolve_calls(self, ast_tree) -> list[Edge]:\n    # Resolves call expressions to candidate symbol IDs',
    category: 'symbol',
  },
  {
    symbol_id: 204,
    name: 'SymbolScanner.scan',
    score: 0.078,
    file_path: 'backend/reposcope/ingestion/scanner.py',
    snippet:
      'def scan(self, directory: Path) -> ScanResult:\n    # Scans directory and collects source files',
    category: 'symbol',
  },
  {
    symbol_id: 301,
    name: 'POST /api/repos/{id}/search',
    score: 0.065,
    file_path: 'backend/reposcope/api/repos.py',
    snippet:
      '@router.post("/repos/{repo_id}/search", response_model=SearchResponse)\ndef search_repo(repo_id: PathID, payload: SearchRequest):',
    category: 'endpoint',
  },
  {
    symbol_id: 302,
    name: 'GET /api/symbols/{id}/neighbors',
    score: 0.054,
    file_path: 'backend/reposcope/api/repos.py',
    snippet:
      '@router.get("/symbols/{symbol_id}/neighbors", response_model=NeighborsResponse)\ndef get_symbol_neighbors(symbol_id: PathID):',
    category: 'endpoint',
  },
  {
    symbol_id: 401,
    name: 'Hybrid Search & Graph Traversal Architecture',
    score: 0.049,
    file_path: 'docs/architecture.md',
    snippet:
      '# Architecture Overview: Hybrid RRF Search with Reciprocal Rank Fusion',
    category: 'documentation',
  },
  {
    symbol_id: 402,
    name: 'API Contract & Endpoints Specification',
    score: 0.038,
    file_path: 'docs/api-contract.md',
    snippet:
      '### 4. Search & GraphRAG Q&A: POST /api/repos/{id}/search',
    category: 'documentation',
  },
];
