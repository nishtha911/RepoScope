import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

import GlobalSearch from './components/GlobalSearch';
import CodeViewerDemo from './components/CodeViewerDemo';
import SymbolDetail from './components/SymbolDetail';
import CodebaseChat from './components/CodebaseChat';

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

  // Global Bauhaus keyboard shortcuts (Cmd/Ctrl + K for search, / for chat)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('header-global-search') as HTMLInputElement | null;
        searchInput?.focus();
        searchInput?.select();
      } else if (
        e.key === '/' &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        e.preventDefault();
        setActiveTab('RAG');
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
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#ffffff',
        color: '#000000',
      }}
    >
      {/* TOP HEADER */}
      <header
        style={{
          display: 'flex',
          alignItems: 'stretch',
          backgroundColor: '#000000',
          borderBottom: '3px solid #000000',
        }}
      >
        {/* Brand */}
        <div
          style={{
            padding: '0 32px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            borderRight: '3px solid #222222',
            flexShrink: 0,
          }}
        >
          <img
            src="/image.png"
            alt="RepoScope Logo"
            style={{
              width: '36px',
              height: '36px',
              objectFit: 'contain',
              backgroundColor: '#ffffff',
              padding: '2px',
              borderRadius: '2px',
            }}
          />
          <span
            style={{
              fontSize: '1.1rem',
              fontWeight: 800,
              letterSpacing: '0.16em',
              color: '#ffffff',
              fontFamily: 'var(--font-sans)',
            }}
          >
            REPOSCOPE
          </span>
        </div>

        {/* Repo selector */}
        <div
          style={{
            padding: '14px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            borderRight: '1px solid #333333',
            minWidth: '200px',
          }}
        >
          <label
            htmlFor="target-repository"
            style={{
              fontSize: '0.65rem',
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: '#888888',
              textTransform: 'uppercase',
              marginBottom: '4px',
            }}
          >
            Repository
          </label>
          <select
            id="target-repository"
            value={selectedRepoId}
            onChange={(event) => {
              setSelectedRepoId(Number(event.target.value));
              setSearchQuery('');
              setSearchLatencyMs(null);
            }}
            style={{
              border: 'none',
              background: 'transparent',
              fontSize: '0.9rem',
              fontWeight: 600,
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
              color: '#ffffff',
            }}
          >
            {mockRepos.map((repo) => (
              <option key={repo.id} value={repo.id} style={{ color: '#000000', background: '#ffffff' }}>
                {repo.name}
              </option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div
          style={{
            padding: '14px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            flexGrow: 1,
            borderRight: '1px solid #333333',
            minWidth: '240px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <label
              htmlFor="header-global-search"
              style={{
                fontSize: '0.65rem',
                fontWeight: 700,
                letterSpacing: '0.12em',
                color: '#888888',
                textTransform: 'uppercase',
              }}
            >
              Search
            </label>
            <kbd
              style={{
                fontSize: '0.6rem',
                fontFamily: 'var(--font-mono)',
                backgroundColor: '#333333',
                color: '#aaaaaa',
                padding: '1px 5px',
                borderRadius: '3px',
                border: '1px solid #444444',
              }}
              title="Press ⌘K or Ctrl+K to search"
            >
              ⌘K
            </kbd>
            {searchLatencyMs !== null && (
              <span
                style={{
                  fontSize: '0.7rem',
                  fontFamily: 'var(--font-mono)',
                  color: '#60a5fa',
                  marginLeft: 'auto',
                }}
              >
                ⚡ {searchLatencyMs}ms
              </span>
            )}
          </div>
          <input
            id="header-global-search"
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setActiveTab('OVERVIEW');
              }
            }}
            placeholder="Search symbols, routes, docs…"
            style={{
              background: '#1a1a1a',
              border: '1px solid #333333',
              borderRadius: '4px',
              padding: '6px 10px',
              fontSize: '0.875rem',
              color: '#ffffff',
              fontFamily: 'var(--font-sans)',
              outline: 'none',
              width: '100%',
            }}
          />
        </div>

        {/* Status + Actions */}
        <div
          style={{
            padding: '14px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: '0.75rem',
              fontFamily: 'var(--font-mono)',
              color: !offlinePreview && isHealthError ? '#f87171' : '#6ee7b7',
              marginRight: '8px',
            }}
          >
            {systemStatus}
          </span>

          <button
            type="button"
            onClick={togglePreviewMode}
            disabled={registerMutation.isPending}
            style={{
              padding: '7px 14px',
              fontSize: '0.75rem',
              fontWeight: 700,
              fontFamily: 'var(--font-sans)',
              letterSpacing: '0.06em',
              background: 'transparent',
              color: '#cccccc',
              border: '1px solid #444444',
              borderRadius: '4px',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {offlinePreview ? 'Connect API' : 'Go Offline'}
          </button>

          <button
            type="button"
            onClick={() => {
              setIsRegistering((previous) => !previous);
            }}
            disabled={offlinePreview || registerMutation.isPending}
            title={offlinePreview ? 'Repository registration requires the API.' : undefined}
            style={{
              padding: '7px 14px',
              fontSize: '0.75rem',
              fontWeight: 700,
              fontFamily: 'var(--font-sans)',
              letterSpacing: '0.06em',
              background: '#ffffff',
              color: '#000000',
              border: '1px solid #ffffff',
              borderRadius: '4px',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              opacity: offlinePreview ? 0.4 : 1,
            }}
          >
            {isRegistering ? 'Close Form' : '+ Register Repo'}
          </button>
        </div>
      </header>

      {/* REPOSITORY REGISTRATION: API MODE ONLY */}
      {!offlinePreview && isRegistering && (
        <section
          className="bauhaus-border-b"
          aria-labelledby="register-repository-heading"
          style={{
            padding: '24px 32px',
            backgroundColor: '#f5f5f5',
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
                letterSpacing: '0.1em',
              }}
            >
              REGISTER NEW REPOSITORY
            </h3>

            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 800,
                padding: '4px 12px',
                backgroundColor: registerMutation.isPending
                  ? '#000000'
                  : '#e2e8f0',
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

          <p style={{ fontSize: '0.85rem', marginBottom: '12px' }}>
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
            <p role="status" style={{ marginTop: '12px' }}>
              Waiting for the registration response...
            </p>
          )}

          {registerMutation.isError && (
            <p
              role="alert"
              style={{
                color: '#b91c1c',
                marginTop: '12px',
                fontSize: '0.85rem',
              }}
            >
              {registerMutation.error.message}
            </p>
          )}
        </section>
      )}

      {/* MODE NOTICE */}
      <div
        style={{
          padding: '8px 32px',
          fontSize: '0.78rem',
          color: '#666666',
          backgroundColor: offlinePreview ? '#fffbeb' : '#fafafa',
          borderBottom: '1px solid #e5e5e5',
        }}
      >
        {offlinePreview
          ? '⚠ Offline preview — fixture data only. API calls and registration are disabled.'
          : '◎ API mode — health, registration, and symbol search use live HTTP requests. Dashboard metrics are illustrative fixtures.'}
      </div>

      {/* NAVIGATION */}
      <AppNav activeTab={activeTab} onTabChange={setActiveTab} />

      {/* FIXTURE METRICS */}
      <div
        className="bauhaus-border-b"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        }}
      >
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
          <div
            key={label}
            className="bauhaus-border-r"
            style={{ padding: '24px' }}
          >
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                letterSpacing: '0.08em',
                display: 'block',
                marginBottom: '8px',
                color: '#555555',
                textTransform: 'uppercase',
              }}
            >
              {label}
            </span>

            <span
              style={{
                fontSize: '2.5rem',
                fontWeight: 800,
                fontFamily: 'var(--font-mono)',
              }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* MAIN DASHBOARD */}
      <main
        style={{
          flex: 1,
          padding: 0,
          backgroundColor: '#ffffff',
        }}
      >
        {activeTab === 'OVERVIEW' && (
          <>
            {/* Independent of symbol search and backend availability. */}
            <CodeViewerDemo />

            <div
              style={{
                display: 'grid',
                gridTemplateColumns:
                  'repeat(auto-fit, minmax(min(100%, 350px), 1fr))',
                alignItems: 'stretch',
              }}
            >
              {/* LEFT COLUMN */}
              <div
                className="bauhaus-border-r"
                style={{ padding: '32px', minWidth: 0 }}
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
                  <div
                    className="bauhaus-border-b"
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '12px',
                      marginBottom: '16px',
                    }}
                  >
                    <h2
                      style={{
                        fontSize: '1.1rem',
                        fontWeight: 800,
                        letterSpacing: '0.08em',
                        paddingBottom: '8px',
                      }}
                    >
                      REPOSITORY FILE TREE
                    </h2>

                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 700,
                      }}
                    >
                      STATIC EXAMPLE
                    </span>
                  </div>

                  <pre
                    className="bauhaus-border-all"
                    style={{
                      margin: 0,
                      padding: '16px',
                      backgroundColor: '#fafafa',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.85rem',
                      lineHeight: 1.7,
                      overflowX: 'auto',
                    }}
                  >
                    {mockFileTree}
                  </pre>
                </section>

                {/* PLANNED ARCHITECTURE */}
                <section style={{ marginTop: '36px' }}>
                  <h2
                    className="bauhaus-border-b"
                    style={{
                      fontSize: '1.1rem',
                      fontWeight: 800,
                      letterSpacing: '0.08em',
                      marginBottom: '16px',
                      paddingBottom: '8px',
                    }}
                  >
                    PLANNED PIPELINE ARCHITECTURE
                  </h2>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns:
                        'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: '12px',
                    }}
                  >
                    {[
                      ['PASS 1', 'Tree-sitter AST Symbol Table'],
                      ['PASS 2', 'Scoped Call & Import Resolver'],
                      ['RETRIEVAL', 'RRF Vector + Lexical Search'],
                      ['ANSWERING', 'Evidence-Cited GraphRAG'],
                    ].map(([label, description], index) => (
                      <div
                        key={label}
                        className="bauhaus-border-all"
                        style={{
                          padding: '16px',
                          backgroundColor:
                            index === 0 || index === 3
                              ? '#000000'
                              : '#ffffff',
                          color:
                            index === 0 || index === 3
                              ? '#ffffff'
                              : '#000000',
                        }}
                      >
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 800,
                            letterSpacing: '0.15em',
                          }}
                        >
                          {label}
                        </span>

                        <p
                          style={{
                            fontSize: '0.9rem',
                            fontWeight: 700,
                            marginTop: '4px',
                          }}
                        >
                          {description}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              {/* RIGHT COLUMN */}
              <div style={{ padding: '32px', minWidth: 0 }}>
                <div
                  className="bauhaus-border-b"
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '12px',
                    marginBottom: '20px',
                  }}
                >
                  <h2
                    style={{
                      fontSize: '1.1rem',
                      fontWeight: 800,
                      letterSpacing: '0.08em',
                      paddingBottom: '12px',
                    }}
                  >
                    PR IMPACT — EXAMPLE REPORTS
                  </h2>

                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                    }}
                  >
                    3 SYNTHETIC EXAMPLES
                  </span>
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

                {/* Honest local preview status, not simulated server logs. */}
                <section style={{ marginTop: '36px' }}>
                  <h2
                    className="bauhaus-border-b"
                    style={{
                      fontSize: '1.1rem',
                      fontWeight: 800,
                      letterSpacing: '0.1em',
                      marginBottom: '16px',
                      paddingBottom: '8px',
                    }}
                  >
                    PREVIEW STATUS
                  </h2>

                  <div
                    className="bauhaus-border-all"
                    style={{
                      padding: '16px',
                      backgroundColor: '#000000',
                      color: '#ffffff',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.8rem',
                      lineHeight: 1.8,
                      overflowWrap: 'anywhere',
                    }}
                  >
                    <div>
                      MODE: {offlinePreview ? 'OFFLINE FIXTURE' : 'API'}
                    </div>

                    <div>
                      CODE PREVIEW: local synthetic fixture
                    </div>

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

                    <div>
                      REPOSITORY INGESTION: not verified
                    </div>

                    <div>
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

      {/* UPGRADED ARCHITECTURAL BAUHAUS FOOTER */}
      <Footer
        offlinePreview={offlinePreview}
        apiHealth={healthData}
        isHealthError={isHealthError}
      />
    </div>
  );
}