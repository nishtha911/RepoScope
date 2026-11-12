import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

import GlobalSearch from './components/GlobalSearch';
import CodeViewerDemo from './components/CodeViewerDemo';
import SymbolDetail from './components/SymbolDetail';
import CodebaseChat from './components/CodebaseChat';
import PRImpactView from './components/PRImpactView';
import PROverviewCard from './components/PROverviewCard';
import RecommendationsBoard from './components/RecommendationsBoard';
import Footer from './components/Footer';
import { initialAnalysisHistory } from './fixtures/prImpact';
import './App.css';

type Tab =
  | 'OVERVIEW'
  | 'GRAPH'
  | 'PR_IMPACT'
  | 'RAG'
  | 'RECOMMENDATIONS';

const API_BASE = 'http://localhost:8000/api';

const mockRepos = [
  {
    id: 1,
    name: 'nishtha911/RepoScope',
  },
];

const mockFileTree = [
  'backend/',
  '  reposcope/',
  '    ingestion/',
  '      clone.py',
  '      scanner.py',
  '      pipeline.py',
  '    parsing/',
  '      resolver.py',
  '      python_parser.py',
  '  tests/',
  '    test_clone.py',
  '    test_scanner.py',
  'frontend/',
  '  src/',
  '    App.tsx',
  '    components/',
  '      CodeViewer.tsx',
  '      CodeViewerDemo.tsx',
  'README.md',
  'plan.md',
].join('\n');

async function fetchHealth() {
  const response = await fetch(`${API_BASE}/health`);

  if (!response.ok) {
    throw new Error('Health check failed');
  }

  return response.json();
}

async function registerRepo(url: string) {
  const response = await fetch(`${API_BASE}/repos`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    throw new Error('Failed to register repo');
  }

  return response.json();
}

export default function App() {
  const [offlinePreview, setOfflinePreview] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('OVERVIEW');
  const [selectedRepoId, setSelectedRepoId] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLatencyMs, setSearchLatencyMs] = useState<number | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [newRepoUrl, setNewRepoUrl] = useState('');
  const [inspectedSymbolId, setInspectedSymbolId] = useState<number>(101);

  // Keyboard navigation: ⌘K or / to search, 1-5 for tab jumping
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (!e.metaKey && !e.ctrlKey && !e.altKey && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        if (e.key === '1') setActiveTab('OVERVIEW');
        if (e.key === '2') setActiveTab('GRAPH');
        if (e.key === '3') setActiveTab('PR_IMPACT');
        if (e.key === '4') setActiveTab('RAG');
        if (e.key === '5') setActiveTab('RECOMMENDATIONS');
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const selectedRepo =
    mockRepos.find((repo) => repo.id === selectedRepoId) ??
    mockRepos[0]!;

  const {
    data: healthData,
    isError: isHealthError,
  } = useQuery({
    queryKey: ['health', API_BASE],
    queryFn: fetchHealth,
    enabled: !offlinePreview,
    retry: false,
    refetchInterval: offlinePreview ? false : 10000,
    refetchOnWindowFocus: false,
  });

  const registerMutation = useMutation({
    mutationFn: registerRepo,
    onSuccess: () => {
      setIsRegistering(false);
      setNewRepoUrl('');
    },
  });

  const systemStatus = offlinePreview
    ? '[ OFFLINE FIXTURE PREVIEW ]'
    : isHealthError
      ? '[ SERVER UNREACHABLE ]'
      : healthData?.status
        ? `[ API RESPONDING // v${healthData.v || '1.0'} ]`
        : '[ CONNECTING... ]';

  function togglePreviewMode() {
    setOfflinePreview((previous) => !previous);
    setIsRegistering(false);
    setSearchQuery('');
    setSearchLatencyMs(null);
    registerMutation.reset();
  }

  function submitRepository() {
    const url = newRepoUrl.trim();

    if (offlinePreview || !url || registerMutation.isPending) {
      return;
    }

    registerMutation.mutate(url);
  }

  return (
    <div className="bauhaus-shell">
      {/* TOP HEADER */}
      <header className="bauhaus-header">
        {/* Brand Block */}
        <div className="bauhaus-brand">
          <img
            src="/image.png"
            alt="RepoScope Logo"
            className="bauhaus-logo"
          />
          <span className="bauhaus-brand__title">REPOSCOPE</span>
        </div>

        {/* System Status */}
        <div className="bauhaus-cell">
          <span className="bauhaus-cell__label">SYSTEM STATUS</span>
          <span
            className="bauhaus-cell__value"
            style={{
              color: !offlinePreview && isHealthError
                ? 'var(--bauhaus-red)'
                : '#000000',
            }}
          >
            {systemStatus}
          </span>
        </div>

        {/* Target Repository */}
        <div className="bauhaus-cell" style={{ minWidth: '220px' }}>
          <label htmlFor="target-repository" className="bauhaus-cell__label">
            TARGET REPOSITORY
          </label>

          <select
            id="target-repository"
            className="bauhaus-select"
            value={selectedRepoId}
            onChange={(event) => {
              setSelectedRepoId(Number(event.target.value));
              setSearchQuery('');
              setSearchLatencyMs(null);
            }}
          >
            {mockRepos.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.name} (mock)
              </option>
            ))}
          </select>
        </div>

        {/* Global Search */}
        <div className="bauhaus-search-cell">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <label
              htmlFor="header-global-search"
              className="bauhaus-cell__label"
            >
              GLOBAL SEARCH
            </label>

            {searchLatencyMs !== null && (
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 800,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--bauhaus-blue)',
                }}
              >
                ⚡ {searchLatencyMs}ms
              </span>
            )}
          </div>

          <input
            id="header-global-search"
            className="bauhaus-input bauhaus-search-input"
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setActiveTab('OVERVIEW');
              }
            }}
            placeholder="Search symbols, routes, docs…"
          />
        </div>

        {/* Actions */}
        <div className="bauhaus-actions-cell">
          <button
            type="button"
            className="bauhaus-btn-invert"
            onClick={togglePreviewMode}
            disabled={registerMutation.isPending}
          >
            {offlinePreview
              ? 'CONNECT TO API'
              : 'USE OFFLINE PREVIEW'}
          </button>

          <button
            type="button"
            className="bauhaus-btn-invert"
            onClick={() => {
              setIsRegistering((previous) => !previous);
            }}
            disabled={offlinePreview || registerMutation.isPending}
            title={
              offlinePreview
                ? 'Repository registration requires the API.'
                : undefined
            }
          >
            {isRegistering ? 'CLOSE FORM' : '+ REGISTER REPO'}
          </button>
        </div>
      </header>

      {/* REPOSITORY REGISTRATION FORM: API MODE ONLY */}
      {!offlinePreview && isRegistering && (
        <section
          className="bauhaus-border-b"
          aria-labelledby="register-repository-heading"
          style={{
            padding: '24px 32px',
            backgroundColor: 'var(--bg-subtle)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              marginBottom: '12px',
            }}
          >
            <h3
              id="register-repository-heading"
              style={{
                fontSize: '1rem',
                fontWeight: 800,
                letterSpacing: '0.08em',
              }}
            >
              REGISTER NEW REPOSITORY
            </h3>

            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                padding: '4px 12px',
                backgroundColor: registerMutation.isPending
                  ? '#000000'
                  : '#e5e5e5',
                color: registerMutation.isPending
                  ? '#ffffff'
                  : '#000000',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {registerMutation.isPending
                ? '[ SENDING REGISTRATION REQUEST ]'
                : '[ READY TO SUBMIT ]'}
            </span>
          </div>

          <p
            style={{
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              marginBottom: '12px',
            }}
          >
            This sends a request to the configured API. A successful
            registration response does not prove that cloning or indexing
            has completed.
          </p>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              submitRepository();
            }}
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '12px',
              maxWidth: '800px',
            }}
          >
            <input
              className="bauhaus-input"
              aria-label="GitHub repository URL"
              placeholder="https://github.com/owner/repository.git"
              value={newRepoUrl}
              onChange={(event) => {
                setNewRepoUrl(event.target.value);
              }}
              disabled={registerMutation.isPending}
              style={{ flex: '1 1 280px' }}
            />

            <button
              type="submit"
              className="bauhaus-btn-invert"
              disabled={
                registerMutation.isPending || !newRepoUrl.trim()
              }
            >
              {registerMutation.isPending
                ? 'SUBMITTING...'
                : 'REGISTER REPOSITORY'}
            </button>
          </form>

          {registerMutation.isPending && (
            <p
              role="status"
              style={{
                marginTop: '12px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.82rem',
              }}
            >
              Waiting for the registration response...
            </p>
          )}

          {registerMutation.isError && (
            <p
              role="alert"
              style={{
                color: 'var(--bauhaus-red)',
                marginTop: '12px',
                fontSize: '0.85rem',
              }}
            >
              {registerMutation.error.message}
            </p>
          )}
        </section>
      )}

      {/* MODE NOTICE BANNER */}
      <div
        className={`bauhaus-notice-banner ${
          offlinePreview
            ? 'bauhaus-notice-banner--offline'
            : 'bauhaus-notice-banner--api'
        }`}
      >
        <div>
          <strong>
            {offlinePreview ? 'OFFLINE PREVIEW — ' : 'API MODE — '}
          </strong>
          {offlinePreview
            ? 'the CodeViewer uses local fixture data. API health polling and symbol search are disabled. Registration is unavailable.'
            : 'health, registration, and symbol search use HTTP requests. The current repository endpoints may still return mock responses.'}
        </div>
        <div style={{ fontSize: '0.72rem', opacity: 0.85 }}>
          Dashboard metrics, repository tree, PR cards, and recommendations
          below are illustrative fixtures, not measured repository results.
        </div>
      </div>

      {/* NAVIGATION TABS */}
      <nav
        className="bauhaus-nav"
        aria-label="Dashboard sections"
      >
        {(
          [
            'OVERVIEW',
            'GRAPH',
            'PR_IMPACT',
            'RAG',
            'RECOMMENDATIONS',
          ] as Tab[]
        ).map((tab) => {
          const isActive = activeTab === tab;

          return (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              aria-pressed={isActive}
              className={`bauhaus-tab-btn ${
                isActive ? 'bauhaus-tab-btn--active' : ''
              }`}
            >
              [ {tab.replaceAll('_', ' ')} ]
            </button>
          );
        })}
      </nav>

      {/* METRICS STRIP */}
      <div className="bauhaus-metrics-grid">
        {[
          ['INGESTED SYMBOLS — EXAMPLE', '3,412'],
          ['AST GRAPH EDGES — EXAMPLE', '14,890'],
          [
            searchLatencyMs !== null
              ? 'SEARCH LATENCY — MEASURED'
              : 'SEARCH LATENCY — BASELINE',
            searchLatencyMs !== null ? `${searchLatencyMs}ms` : '18ms',
          ],
          ['AVG PR BLAST RADIUS — EXAMPLE', '0.04'],
        ].map(([label, value]) => (
          <div key={label} className="bauhaus-metric-cell">
            <span className="bauhaus-metric-label">{label}</span>
            <span className="bauhaus-metric-value">{value}</span>
          </div>
        ))}
      </div>

      {/* MAIN DASHBOARD */}
      <main className="bauhaus-main">
        {activeTab === 'OVERVIEW' && (
          <>
            {/* Independent of symbol search and backend availability. */}
            <CodeViewerDemo />

            <div className="bauhaus-overview-layout">
              {/* LEFT COLUMN */}
              <div
                className="bauhaus-panel-col"
                style={{ borderRight: 'var(--border-thin)' }}
              >
                <GlobalSearch
                  key={`${selectedRepoId}-${offlinePreview}`}
                  repoId={selectedRepoId}
                  repoName={selectedRepo.name}
                  query={searchQuery}
                  onQueryChange={setSearchQuery}
                  apiBase={API_BASE}
                  offlinePreview={offlinePreview}
                  onSelectSymbol={(symbolId) => {
                    setInspectedSymbolId(symbolId);
                    setActiveTab('GRAPH');
                  }}
                  onLatencyChange={setSearchLatencyMs}
                />

                {/* ILLUSTRATIVE FILE TREE */}
                <section style={{ marginTop: '36px' }}>
                  <div className="bauhaus-section-header">
                    <h2 className="bauhaus-section-title">
                      REPOSITORY FILE TREE
                    </h2>

                    <span className="bauhaus-badge">STATIC EXAMPLE</span>
                  </div>

                  <pre className="bauhaus-code-box">
                    {mockFileTree}
                  </pre>
                </section>

                {/* PLANNED ARCHITECTURE */}
                <section style={{ marginTop: '36px' }}>
                  <div className="bauhaus-section-header">
                    <h2 className="bauhaus-section-title">
                      PLANNED PIPELINE ARCHITECTURE
                    </h2>
                  </div>

                  <div className="bauhaus-pipeline-grid">
                    {[
                      ['PASS 1', 'Tree-sitter AST Symbol Table'],
                      ['PASS 2', 'Scoped Call & Import Resolver'],
                      ['RETRIEVAL', 'RRF Vector + Lexical Search'],
                      ['ANSWERING', 'Evidence-Cited GraphRAG'],
                    ].map(([label, description], index) => {
                      const isDark = index === 0 || index === 3;
                      return (
                        <div
                          key={label}
                          className={`bauhaus-pipeline-card ${
                            isDark
                              ? 'bauhaus-pipeline-card--dark'
                              : 'bauhaus-pipeline-card--light'
                          }`}
                        >
                          <span className="bauhaus-pipeline-phase">
                            {label}
                          </span>
                          <p className="bauhaus-pipeline-desc">
                            {description}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </section>
              </div>

              {/* RIGHT COLUMN */}
              <div className="bauhaus-panel-col">
                <div className="bauhaus-section-header">
                  <h2 className="bauhaus-section-title">
                    PR IMPACT — EXAMPLE REPORTS
                  </h2>

                  <span className="bauhaus-badge">3 SYNTHETIC EXAMPLES</span>
                </div>

                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px',
                  }}
                >
                  {initialAnalysisHistory.slice(0, 3).map((item) => (
                    <PROverviewCard
                      key={item.id}
                      report={item}
                      title={item.title}
                      compact
                      onViewDetails={() => setActiveTab('PR_IMPACT')}
                    />
                  ))}
                </div>

                {/* Honest local preview status */}
                <section style={{ marginTop: '36px' }}>
                  <div className="bauhaus-section-header">
                    <h2 className="bauhaus-section-title">
                      PREVIEW STATUS
                    </h2>
                  </div>

                  <div className="bauhaus-status-console">
                    <div>
                      MODE: {offlinePreview ? 'OFFLINE FIXTURE' : 'API'}
                    </div>
                    <div>CODE PREVIEW: local synthetic fixture</div>
                    <div>
                      HEALTH POLLING:{' '}
                      {offlinePreview ? 'disabled' : 'enabled'}
                    </div>
                    <div>
                      GLOBAL SEARCH:{' '}
                      {offlinePreview
                        ? 'offline fixture preview mode'
                        : 'live POST /api/repos/{id}/search'}
                    </div>
                    <div>REPOSITORY INGESTION: not verified</div>
                    <div style={{ marginTop: '8px', opacity: 0.75 }}>
                      Dashboard fixtures are not backend telemetry.
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </>
        )}

        {/* SYMBOL DETAIL & NEIGHBORHOOD VIEWER */}
        {activeTab === 'GRAPH' && (
          <SymbolDetail
            symbolId={inspectedSymbolId}
            repoId={selectedRepoId}
            repoName={selectedRepo.name}
            offlinePreview={offlinePreview}
            apiBase={API_BASE}
            onSelectSymbol={(id) => setInspectedSymbolId(id)}
            onBackToOverview={() => setActiveTab('OVERVIEW')}
          />
        )}

        {/* PR IMPACT SUBMISSION & BLAST RADIUS VIEW */}
        {activeTab === 'PR_IMPACT' && (
          <PRImpactView
            repoId={selectedRepoId}
            repoName={selectedRepo.name}
            apiBase={API_BASE}
            offlinePreview={offlinePreview}
          />
        )}

        {/* RAG CODEBASE CHAT */}
        {activeTab === 'RAG' && (
          <CodebaseChat
            repoId={selectedRepoId}
            repoName={selectedRepo.name}
            apiBase={API_BASE}
            offlinePreview={offlinePreview}
            onSelectSymbol={(symbolId) => {
              setInspectedSymbolId(symbolId);
              setActiveTab('OVERVIEW');
            }}
          />
        )}

        {/* WHAT TO WORK ON NEXT RECOMMENDATIONS BOARD */}
        {activeTab === 'RECOMMENDATIONS' && (
          <RecommendationsBoard
            repoId={selectedRepoId}
            repoName={selectedRepo.name}
            apiBase={API_BASE}
            offlinePreview={offlinePreview}
            onInspectSymbol={(symbolId) => {
              setInspectedSymbolId(symbolId);
              setActiveTab('GRAPH');
            }}
          />
        )}
      </main>

      {/* FOOTER */}
      <Footer
        offlinePreview={offlinePreview}
        apiHealth={healthData}
        isHealthError={isHealthError}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
    </div>
  );
}
