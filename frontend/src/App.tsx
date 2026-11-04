import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

import GlobalSearch from './components/GlobalSearch';
import CodeViewerDemo from './components/CodeViewerDemo';
import SymbolDetail from './components/SymbolDetail';

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

const recentPRImpacts = [
  {
    pr: '#42 Refactor resolver.py AST pass',
    risk: 'LOW (0.04)',
    blastCount: 14,
    filesChanged: 3,
  },
  {
    pr: '#41 Upgrade pgvector HNSW index params',
    risk: 'MED (0.18)',
    blastCount: 42,
    filesChanged: 7,
  },
  {
    pr: '#40 Add evidence pack validator',
    risk: 'LOW (0.01)',
    blastCount: 6,
    filesChanged: 2,
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
        className="bauhaus-border-b"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'stretch',
          backgroundColor: '#ffffff',
        }}
      >
        <div
          className="bauhaus-border-r"
          style={{
            padding: '16px 32px',
            backgroundColor: '#000000',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            gap: '18px',
          }}
        >
          <img
            src="/image.png"
            alt="RepoScope Logo"
            style={{
              width: '54px',
              height: '54px',
              objectFit: 'contain',
              border: '2px solid #ffffff',
              backgroundColor: '#ffffff',
              padding: '2px',
            }}
          />

          <span
            style={{
              fontSize: '1.6rem',
              fontWeight: 800,
              letterSpacing: '0.14em',
            }}
          >
            REPOSCOPE
          </span>
        </div>

        <div
          className="bauhaus-border-r"
          style={{
            padding: '16px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          <span
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
            }}
          >
            SYSTEM STATUS
          </span>

          <span
            style={{
              fontSize: '0.9rem',
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              marginTop: '4px',
              color:
                !offlinePreview && isHealthError
                  ? '#b91c1c'
                  : '#000000',
            }}
          >
            {systemStatus}
          </span>
        </div>

        <div
          className="bauhaus-border-r"
          style={{
            padding: '16px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            minWidth: '220px',
          }}
        >
          <label
            htmlFor="target-repository"
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              letterSpacing: '0.15em',
            }}
          >
            TARGET REPOSITORY
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
              fontSize: '1rem',
              fontWeight: 700,
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
              marginTop: '4px',
            }}
          >
            {mockRepos.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.name} (mock)
              </option>
            ))}
          </select>
        </div>

        <div
          className="bauhaus-border-r"
          style={{
            padding: '12px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            flexGrow: 1,
            minWidth: '260px',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <label
              htmlFor="header-global-search"
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                letterSpacing: '0.15em',
              }}
            >
              GLOBAL SEARCH
            </label>

            {searchLatencyMs !== null && (
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 800,
                  fontFamily: 'var(--font-mono)',
                  color: '#2563eb',
                }}
              >
                ⚡ {searchLatencyMs}ms
              </span>
            )}
          </div>

          <input
            id="header-global-search"
            className="bauhaus-input"
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
              marginTop: '4px',
              padding: '6px 10px',
              fontSize: '0.85rem',
            }}
          />
        </div>

        <div
          style={{
            padding: '16px 24px',
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
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
        className="bauhaus-border-b"
        style={{
          padding: '12px 24px',
          fontSize: '0.8rem',
          lineHeight: 1.6,
          backgroundColor: offlinePreview ? '#fff4ce' : '#f5f5f5',
        }}
      >
        {offlinePreview
          ? 'OFFLINE PREVIEW — the CodeViewer uses local fixture data. API health polling and symbol search are disabled. Registration is unavailable.'
          : 'API MODE — health, registration, and symbol search use HTTP requests. The current repository endpoints may still return mock responses.'}

        <br />

        Dashboard metrics, repository tree, PR cards, and recommendations
        below are illustrative fixtures, not measured repository results.
      </div>

      {/* NAVIGATION TABS */}
      <nav
        className="bauhaus-border-b"
        aria-label="Dashboard sections"
        style={{
          display: 'flex',
          backgroundColor: '#ffffff',
          overflowX: 'auto',
        }}
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
              className="bauhaus-border-r"
              style={{
                padding: '16px 28px',
                borderTop: 'none',
                borderBottom: 'none',
                borderLeft: 'none',
                backgroundColor: isActive ? '#000000' : '#ffffff',
                color: isActive ? '#ffffff' : '#000000',
                fontFamily: 'var(--font-sans)',
                fontWeight: 800,
                fontSize: '0.85rem',
                letterSpacing: '0.12em',
                cursor: 'pointer',
                borderRadius: 0,
                whiteSpace: 'nowrap',
              }}
            >
              [ {tab.replaceAll('_', ' ')} ]
            </button>
          );
        })}
      </nav>

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
                fontSize: '0.7rem',
                fontWeight: 800,
                letterSpacing: '0.12em',
                display: 'block',
                marginBottom: '8px',
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
                  {recentPRImpacts.map((item) => (
                    <div
                      key={item.pr}
                      className="bauhaus-border-all"
                      style={{ padding: '20px' }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          flexWrap: 'wrap',
                          gap: '12px',
                          marginBottom: '12px',
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 800,
                            fontSize: '0.95rem',
                          }}
                        >
                          {item.pr}
                        </span>

                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 800,
                            padding: '4px 10px',
                            border: '2px solid #000000',
                          }}
                        >
                          EXAMPLE RISK: {item.risk}
                        </span>
                      </div>

                      <div
                        style={{
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: '24px',
                          fontSize: '0.8rem',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        <span>
                          AFFECTED SYMBOLS: {item.blastCount}
                        </span>

                        <span>FILES: {item.filesChanged}</span>
                      </div>
                    </div>
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

        {/* PR IMPACT PLACEHOLDER */}
        {activeTab === 'PR_IMPACT' && (
          <section style={{ padding: '32px' }}>
            <h2
              className="bauhaus-border-b"
              style={{
                fontSize: '1.2rem',
                fontWeight: 800,
                letterSpacing: '0.1em',
                marginBottom: '16px',
                paddingBottom: '8px',
              }}
            >
              PR IMPACT ANALYSIS — UI PREVIEW
            </h2>

            <div
              className="bauhaus-border-all"
              style={{ padding: '28px' }}
            >
              <p style={{ marginBottom: '16px' }}>
                This form is a placeholder. No analysis handler is
                connected.
              </p>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '16px',
                }}
              >
                <input
                  className="bauhaus-input"
                  aria-label="Git diff or PR branch"
                  placeholder="e.g. main...feature/ast-resolver"
                  style={{ flex: '1 1 260px' }}
                />

                <button
                  type="button"
                  className="bauhaus-btn-invert"
                  disabled
                >
                  CALCULATE BLAST RADIUS — NOT CONNECTED
                </button>
              </div>
            </div>
          </section>
        )}

        {/* RAG PLACEHOLDER */}
        {activeTab === 'RAG' && (
          <section style={{ padding: '32px' }}>
            <h2
              className="bauhaus-border-b"
              style={{
                fontSize: '1.2rem',
                fontWeight: 800,
                letterSpacing: '0.1em',
                marginBottom: '16px',
                paddingBottom: '8px',
              }}
            >
              EVIDENCE-CITED GraphRAG — UI PREVIEW
            </h2>

            <div
              className="bauhaus-border-all"
              style={{ padding: '24px' }}
            >
              <p style={{ marginBottom: '16px' }}>
                This interface is not connected to retrieval or an LLM.
              </p>

              <textarea
                className="bauhaus-input"
                aria-label="Question about the repository"
                rows={4}
                placeholder="Ask a question about the repository..."
                style={{
                  boxSizing: 'border-box',
                  width: '100%',
                  resize: 'vertical',
                  marginBottom: '16px',
                }}
              />

              <button
                type="button"
                className="bauhaus-btn-invert"
                disabled
              >
                GENERATE RESPONSE — NOT CONNECTED
              </button>
            </div>
          </section>
        )}

        {/* SYNTHETIC RECOMMENDATIONS */}
        {activeTab === 'RECOMMENDATIONS' && (
          <section style={{ padding: '32px' }}>
            <h2
              className="bauhaus-border-b"
              style={{
                fontSize: '1.2rem',
                fontWeight: 800,
                letterSpacing: '0.1em',
                marginBottom: '16px',
                paddingBottom: '8px',
              }}
            >
              RECOMMENDATIONS — SYNTHETIC EXAMPLES
            </h2>

            <p style={{ marginBottom: '16px' }}>
              These cards are static examples, not outputs from a trained
              ranker or a repository analysis.
            </p>

            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
              }}
            >
              <div
                className="bauhaus-border-all"
                style={{ padding: '20px' }}
              >
                <span
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 800,
                    letterSpacing: '0.1em',
                    display: 'block',
                    marginBottom: '6px',
                  }}
                >
                  EXAMPLE PRIORITY #1 // FIXTURE SCORE: 0.94
                </span>

                <h3 style={{ fontSize: '1rem', fontWeight: 800 }}>
                  Add test coverage for{' '}
                  <code>SymbolResolver.resolve_calls()</code>
                </h3>
              </div>

              <div
                className="bauhaus-border-all"
                style={{ padding: '20px' }}
              >
                <span
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 800,
                    letterSpacing: '0.1em',
                    display: 'block',
                    marginBottom: '6px',
                  }}
                >
                  EXAMPLE PRIORITY #2 // FIXTURE SCORE: 0.88
                </span>

                <h3 style={{ fontSize: '1rem', fontWeight: 800 }}>
                  Optimize pgvector HNSW index parameters for large
                  repositories
                </h3>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* FOOTER */}
      <footer
        className="bauhaus-border-t"
        style={{
          padding: '20px 32px',
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          backgroundColor: '#000000',
          color: '#ffffff',
          fontSize: '0.8rem',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <div>REPOSCOPE // BAUHAUS DESIGN EDITION</div>

        <div>
          {offlinePreview
            ? 'LOCAL FIXTURE PREVIEW // NO BACKEND REQUIRED'
            : 'API MODE // DATA SOURCES REQUIRE VERIFICATION'}
        </div>
      </footer>
    </div>
  );
}