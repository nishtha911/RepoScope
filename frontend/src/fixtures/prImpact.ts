import type { PRAnalysisHistoryItem } from '../types/prImpact';

export const samplePRUrls = [
  {
    label: '#42 Refactor resolver.py AST pass',
    url: 'https://github.com/nishtha911/RepoScope/pull/42',
  },
  {
    label: '#41 Upgrade pgvector HNSW index params',
    url: 'https://github.com/nishtha911/RepoScope/pull/41',
  },
  {
    label: '#40 Add evidence pack validator',
    url: 'https://github.com/nishtha911/RepoScope/pull/40',
  },
  {
    label: '#39 Add Git churn statistics extraction',
    url: 'https://github.com/nishtha911/RepoScope/pull/39',
  },
  {
    label: '#38 Breaking auth middleware & routes',
    url: 'https://github.com/nishtha911/RepoScope/pull/38',
  },
  {
    label: '#37 Drop legacy PostgreSQL tables',
    url: 'https://github.com/nishtha911/RepoScope/pull/37',
  },
];

export const sampleGitPatch = `diff --git a/backend/reposcope/parsing/resolver.py b/backend/reposcope/parsing/resolver.py
--- a/backend/reposcope/parsing/resolver.py
+++ b/backend/reposcope/parsing/resolver.py
@@ -142,8 +142,12 @@ class SymbolResolver:
-    def resolve_calls(self, ast_tree):
-        return []
+    def resolve_calls(self, ast_tree: ast.AST) -> list[Edge]:
+        """Resolve call expressions to target symbols using two-pass table."""
+        calls: list[Edge] = []
+        for node in ast.walk(ast_tree):
+            if isinstance(node, ast.Call):
+                resolved = self._lookup_scope(node)
+                if resolved:
+                    calls.append(Edge(src=self.current_symbol_id, dst=resolved.id, type="CALLS"))
+        return calls
diff --git a/backend/tests/unit/test_resolver.py b/backend/tests/unit/test_resolver.py
new file mode 100644
--- /dev/null
+++ b/backend/tests/unit/test_resolver.py
@@ -0,0 +1,15 @@
+def test_resolve_calls_exact_match():
+    resolver = SymbolResolver()
+    assert resolver is not None`;

export const initialAnalysisHistory: PRAnalysisHistoryItem[] = [
  {
    id: 'pr-42',
    title: '#42 Refactor resolver.py AST pass',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/42',
    input_type: 'pr_url',
    risk_level: 'LOW',
    risk_score: 0.04,
    files_changed_count: 3,
    impacted_symbols_count: 14,
    affected_endpoints_count: 0,
    impacted_tests_count: 2,
    summary: 'Modifies internal helper methods in resolver.py without API signature breaking changes.',
    analyzed_at: Date.now() - 3600_000 * 2,
    impacted_endpoints: [],
    impacted_tests: [
      {
        id: 't-42-1',
        test_name: 'test_resolve_calls_exact_match',
        file_path: 'backend/tests/unit/test_resolver.py',
        confidence: 1.0,
      },
      {
        id: 't-42-2',
        test_name: 'test_scope_lookup_fallback',
        file_path: 'backend/tests/unit/test_resolver.py',
        confidence: 0.88,
      },
    ],
    missing_tests: [],
  },
  {
    id: 'pr-41',
    title: '#41 Upgrade pgvector HNSW index params',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/41',
    input_type: 'pr_url',
    risk_level: 'MEDIUM',
    risk_score: 0.18,
    files_changed_count: 7,
    impacted_symbols_count: 42,
    affected_endpoints_count: 2,
    impacted_tests_count: 5,
    summary: 'Modifies pgvector index creation SQL and alters retrieval query plans across hybrid search endpoints.',
    analyzed_at: Date.now() - 3600_000 * 6,
    impacted_endpoints: [
      {
        method: 'POST',
        route: '/api/repos/{id}/search',
        handler_name: 'search_repository',
        confidence: 0.94,
      },
      {
        method: 'POST',
        route: '/api/repos/{id}/ask',
        handler_name: 'ask_codebase',
        confidence: 0.87,
      },
    ],
    impacted_tests: [
      {
        id: 't-41-1',
        test_name: 'test_vector_similarity_search',
        file_path: 'backend/tests/unit/test_vector.py',
        confidence: 0.96,
      },
      {
        id: 't-41-2',
        test_name: 'test_hybrid_rrf_fusion',
        file_path: 'backend/tests/unit/test_fusion.py',
        confidence: 0.91,
      },
      {
        id: 't-41-3',
        test_name: 'test_evidence_pack_retrieval',
        file_path: 'backend/tests/unit/test_pipeline.py',
        confidence: 0.85,
      },
    ],
    missing_tests: [
      {
        symbol_name: 'tune_ef_search_param',
        file_path: 'backend/reposcope/retrieval/vector.py',
        reason: 'Modified performance tuning callable lacks direct test coverage in test suite',
      },
    ],
  },
  {
    id: 'pr-40',
    title: '#40 Add evidence pack validator',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/40',
    input_type: 'pr_url',
    risk_level: 'LOW',
    risk_score: 0.01,
    files_changed_count: 2,
    impacted_symbols_count: 6,
    affected_endpoints_count: 0,
    impacted_tests_count: 4,
    summary: 'Adds validator model logic for contiguous evidence chunk IDs [E1, E2]. No breaking modifications.',
    analyzed_at: Date.now() - 3600_000 * 18,
    impacted_endpoints: [],
    impacted_tests: [
      {
        id: 't-40-1',
        test_name: 'test_evidence_pack_valid_ids',
        file_path: 'backend/tests/unit/test_evidence_pack.py',
        confidence: 1.0,
      },
    ],
    missing_tests: [],
  },
  {
    id: 'pr-39',
    title: '#39 Git churn statistics pipeline',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/39',
    input_type: 'pr_url',
    risk_level: 'LOW',
    risk_score: 0.03,
    files_changed_count: 4,
    impacted_symbols_count: 11,
    affected_endpoints_count: 1,
    impacted_tests_count: 3,
    summary: 'Extracts 90-day git churn statistics into git_stats table. Schema addition is backwards-compatible.',
    analyzed_at: Date.now() - 3600_000 * 24,
  },
  {
    id: 'pr-38',
    title: '#38 Breaking auth middleware & routes',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/38',
    input_type: 'pr_url',
    risk_level: 'HIGH',
    risk_score: 0.68,
    files_changed_count: 14,
    impacted_symbols_count: 65,
    affected_endpoints_count: 6,
    impacted_tests_count: 8,
    summary: 'Refactors API request authorization headers and session dependency injection across primary routes.',
    analyzed_at: Date.now() - 3600_000 * 36,
    impacted_endpoints: [
      {
        method: 'POST',
        route: '/api/auth/login',
        handler_name: 'login_endpoint',
        confidence: 0.98,
      },
      {
        method: 'GET',
        route: '/api/auth/session',
        handler_name: 'get_session_user',
        confidence: 0.95,
      },
      {
        method: 'DELETE',
        route: '/api/auth/logout',
        handler_name: 'logout_endpoint',
        confidence: 0.93,
      },
    ],
    impacted_tests: [
      {
        id: 't-38-1',
        test_name: 'test_session_header_verification',
        file_path: 'backend/tests/unit/test_auth.py',
        confidence: 0.99,
      },
    ],
    missing_tests: [
      {
        symbol_name: 'verify_bearer_token',
        file_path: 'backend/reposcope/api/auth.py',
        reason: 'Modified authentication callable lacks linked unit tests in test suite',
      },
      {
        symbol_name: 'refresh_cookie_token',
        file_path: 'backend/reposcope/api/auth.py',
        reason: 'Altered session cookie helper has 0 static test associations',
      },
    ],
  },
  {
    id: 'pr-37',
    title: '#37 Drop legacy PostgreSQL tables',
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/37',
    input_type: 'pr_url',
    risk_level: 'CRITICAL',
    risk_score: 0.92,
    files_changed_count: 22,
    impacted_symbols_count: 128,
    affected_endpoints_count: 12,
    impacted_tests_count: 15,
    summary: 'Drops v0 schema tables and removes backward-compatible ORM models without fallback migrations.',
    analyzed_at: Date.now() - 3600_000 * 48,
    impacted_endpoints: [
      {
        method: 'GET',
        route: '/api/repos/{id}/legacy-symbols',
        handler_name: 'get_legacy_symbols',
        confidence: 1.0,
      },
    ],
    impacted_tests: [],
    missing_tests: [
      {
        symbol_name: 'migrate_legacy_records',
        file_path: 'backend/reposcope/models/legacy.py',
        reason: 'Critical migration dropped without backward-compatibility test suite',
      },
    ],
  },
];
