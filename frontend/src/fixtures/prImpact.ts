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
  },
];
