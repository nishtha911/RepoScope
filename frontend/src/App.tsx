import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import SymbolSearch from './components/SymbolSearch';

type Tab = 'OVERVIEW' | 'GRAPH' | 'PR_IMPACT' | 'RAG' | 'RECOMMENDATIONS';

const API_BASE = 'http://localhost:8000/api';

async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}


async function registerRepo(url: string) {
  const res = await fetch(`${API_BASE}/repos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error('Failed to register repo');
  return res.json();
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('OVERVIEW');  const [selectedRepoId, setSelectedRepoId] = useState(1);
  const mockRepos = [{ id: 1, name: 'nishtha911/RepoScope' }];
  const selectedRepo = mockRepos.find(repo => repo.id === selectedRepoId)!;
  const [searchQuery, setSearchQuery] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [newRepoUrl, setNewRepoUrl] = useState('');

  // Live queries via React Query
  const { data: healthData, isError: isHealthError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10000,
  });


  const registerMutation = useMutation({
    mutationFn: registerRepo,
    onSuccess: () => {

      setIsRegistering(false);
      setNewRepoUrl('');
    },
  });

  const recentPRImpacts = [
    { pr: '#42 Refactor resolver.py AST pass', risk: 'LOW (0.04)', blastCount: 14, filesChanged: 3 },
    { pr: '#41 Upgrade pgvector HNSW index params', risk: 'MED (0.18)', blastCount: 42, filesChanged: 7 },
    { pr: '#40 Add evidence pack validator', risk: 'LOW (0.01)', blastCount: 6, filesChanged: 2 },
  ];

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff', color: '#000000' }}>
      
      {/* TOP HEADER */}
      <header className="bauhaus-border-b" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'stretch', backgroundColor: '#ffffff' }}>
        <div className="bauhaus-border-r" style={{ padding: '16px 32px', backgroundColor: '#000000', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '18px' }}>
          <img src="/image.png" alt="RepoScope Logo" style={{ width: '54px', height: '54px', objectFit: 'contain', border: '2px solid #ffffff', backgroundColor: '#ffffff', padding: '2px' }} />
          <span style={{ fontSize: '1.6rem', fontWeight: 800, letterSpacing: '0.14em' }}>REPOSCOPE</span>
        </div>

        <div className="bauhaus-border-r" style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase' }}>SYSTEM STATUS</span>
          <span style={{ fontSize: '0.95rem', fontWeight: 700, fontFamily: 'var(--font-mono)', marginTop: '2px', color: isHealthError ? '#e53e3e' : '#000000' }}>
            {isHealthError ? '[ SERVER OFFLINE ]' : healthData?.status ? `[ READY // v${healthData.v || '1.0'} ]` : '[ CONNECTING... ]'}
          </span>
        </div>

        <div className="bauhaus-border-r" style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'center', flexGrow: 1 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase' }}>TARGET REPOSITORY</span>
          <select 
            value={selectedRepoId}
            onChange={(e) => { setSelectedRepoId(Number(e.target.value)); setSearchQuery(''); }}
            style={{
              border: 'none',
              background: 'transparent',
              fontSize: '1rem',
              fontWeight: 700,
              fontFamily: 'var(--font-sans)',
              outline: 'none',
              cursor: 'pointer',
              marginTop: '2px'
            }}
          >
            {mockRepos.map(repo => (
              <option key={repo.id} value={repo.id}>{repo.name} (mock)</option>
            ))}
          </select>
        </div>

        <div style={{ padding: '16px 24px', display: 'flex', alignItems: 'center' }}>
          <button 
            className="bauhaus-btn-invert"
            onClick={() => setIsRegistering(!isRegistering)}
          >
            {isRegistering ? 'CLOSE FORM' : '+ REGISTER REPO'}
          </button>
        </div>
      </header>

      {/* REGISTER REPO EXPANDABLE PANEL WITH CLONE SPINNER & INDEXING BADGES */}
      {isRegistering && (
        <div className="bauhaus-border-b" style={{ padding: '24px 32px', backgroundColor: '#f5f5f5' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 800, letterSpacing: '0.1em' }}>REGISTER NEW REPOSITORY</h3>
            <span style={{ 
              fontSize: '0.75rem', 
              fontWeight: 800, 
              padding: '4px 12px', 
              backgroundColor: registerMutation.isPending ? '#000000' : '#e2e8f0', 
              color: registerMutation.isPending ? '#ffffff' : '#000000',
              fontFamily: 'var(--font-mono)'
            }}>
              {registerMutation.isPending ? '[ STATUS: INDEXING IN PROGRESS ]' : '[ STATUS: READY FOR INGESTION ]'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '12px', maxWidth: '800px' }}>
            <input 
              className="bauhaus-input"
              placeholder="e.g. https://github.com/owner/repository.git"
              value={newRepoUrl}
              onChange={(e) => setNewRepoUrl(e.target.value)}
              disabled={registerMutation.isPending}
            />
            <button 
              className="bauhaus-btn-invert" 
              onClick={() => newRepoUrl && registerMutation.mutate(newRepoUrl)}
              disabled={registerMutation.isPending}
            >
              {registerMutation.isPending ? 'PROCESSING...' : 'INGEST & SCAN'}
            </button>
          </div>

          {/* CLONE & INDEXING PROGRESS SPINNER & STEP INDICATOR */}
          {registerMutation.isPending && (
            <div style={{ marginTop: '16px', padding: '16px', backgroundColor: '#ffffff', border: '2px solid #000000' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
                <div style={{ 
                  width: '18px', 
                  height: '18px', 
                  border: '3px solid #000000', 
                  borderTopColor: 'transparent', 
                  borderRadius: '50%', 
                  animation: 'spin 0.8s linear infinite' 
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '0.9rem' }}>
                  INGESTING REPOSITORY ... (PLEASE WAIT)
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                <div style={{ padding: '8px', border: '1px solid #000000', backgroundColor: '#000000', color: '#ffffff' }}>
                  ✓ [1] SHALLOW CLONE (depth=1)
                </div>
                <div style={{ padding: '8px', border: '1px solid #000000', backgroundColor: '#f0f0f0' }}>
                  ⏳ [2] TREE-SITTER AST PARSER
                </div>
                <div style={{ padding: '8px', border: '1px solid #000000', backgroundColor: '#ffffff' }}>
                  [3] GRAPH EDGE BUILD
                </div>
              </div>
            </div>
          )}

          {registerMutation.isError && (
            <p style={{ color: 'red', marginTop: '8px', fontSize: '0.85rem' }}>Failed to register repository. Check server connection.</p>
          )}
        </div>
      )}

      <div className="bauhaus-border-b" style={{ padding: '12px 24px', fontSize: '0.8rem' }}>
        MOCK SYMBOL SEARCH — use the search panel in Overview. No live indexing or semantic search is claimed.
      </div>

      {/* NAVIGATION TABS */}
      <nav className="bauhaus-border-b" style={{ display: 'flex', backgroundColor: '#ffffff', overflowX: 'auto' }}>
        {(['OVERVIEW', 'GRAPH', 'PR_IMPACT', 'RAG', 'RECOMMENDATIONS'] as Tab[]).map((tab) => {
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
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
                transition: 'none',
                borderRadius: 0,
                whiteSpace: 'nowrap'
              }}
            >
              [ {tab.replace('_', ' ')} ]
            </button>
          );
        })}
      </nav>

      {/* METRICS SUMMARY GRID */}
      <div className="bauhaus-border-b" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        <div className="bauhaus-border-r" style={{ padding: '24px' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em', display: 'block', marginBottom: '8px' }}>INGESTED SYMBOLS</span>
          <span style={{ fontSize: '2.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>3,412</span>
        </div>
        <div className="bauhaus-border-r" style={{ padding: '24px' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em', display: 'block', marginBottom: '8px' }}>AST GRAPH EDGES</span>
          <span style={{ fontSize: '2.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>14,890</span>
        </div>
        <div className="bauhaus-border-r" style={{ padding: '24px' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em', display: 'block', marginBottom: '8px' }}>SEARCH LATENCY</span>
          <span style={{ fontSize: '2.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>18ms</span>
        </div>
        <div style={{ padding: '24px' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em', display: 'block', marginBottom: '8px' }}>AVG PR BLAST RADIUS</span>
          <span style={{ fontSize: '2.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>0.04</span>
        </div>
      </div>

      {/* MAIN DASHBOARD CONTENT AREA */}
      <main style={{ flex: 1, padding: '0px', backgroundColor: '#ffffff' }}>
        
        {/* OVERVIEW TAB */}
        {activeTab === 'OVERVIEW' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', alignItems: 'stretch' }}>
            
            {/* LEFT COLUMN: REPO STRUCTURE & SYMBOLS */}
            <div className="bauhaus-border-r" style={{ padding: '32px' }}>
              <SymbolSearch
                key={selectedRepoId}
                repoId={selectedRepoId}
                repoName={selectedRepo.name}
                query={searchQuery}
                onQueryChange={setSearchQuery}
                apiBase={API_BASE}
              />

              {/* REPOSITORY FILE TREE HIERARCHY COMPONENT */}
              <div style={{ marginTop: '36px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }} className="bauhaus-border-b">
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.1em', paddingBottom: '8px' }}>REPOSITORY FILE HIERARCHY TREE</h2>
                  <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>TREE-SITTER INDEXED</span>
                </div>

                <div className="bauhaus-border-all" style={{ padding: '16px', backgroundColor: '#fafafa', fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ fontWeight: 800, color: '#000000', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      📁 <strong>backend/</strong> <span style={{ fontSize: '0.7rem', color: '#666' }}>(14 files)</span>
                    </div>
                    <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <div>📁 <strong>reposcope/</strong></div>
                      <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div>📁 <strong>ingestion/</strong></div>
                        <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>📄 clone.py</span>
                            <span style={{ color: '#666' }}>357 lines • 12.4 KB</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>📄 scanner.py</span>
                            <span style={{ color: '#666' }}>97 lines • 2.5 KB</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>📄 pipeline.py</span>
                            <span style={{ color: '#666' }}>73 lines • 2.1 KB</span>
                          </div>
                        </div>
                        <div>📁 <strong>parsing/</strong></div>
                        <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>📄 resolver.py</span>
                            <span style={{ color: '#666' }}>142 lines • 4.8 KB</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>📄 python_parser.py</span>
                            <span style={{ color: '#666' }}>0 lines</span>
                          </div>
                        </div>
                      </div>
                      <div>📁 <strong>tests/</strong></div>
                      <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>📄 test_clone.py</span>
                          <span style={{ color: '#666' }}>473 lines • 14.2 KB</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>📄 test_scanner.py</span>
                          <span style={{ color: '#666' }}>35 lines • 1.2 KB</span>
                        </div>
                      </div>
                    </div>

                    <div style={{ fontWeight: 800, color: '#000000', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px' }}>
                      📁 <strong>frontend/</strong> <span style={{ fontSize: '0.7rem', color: '#666' }}>(4 files)</span>
                    </div>
                    <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>📄 src/App.tsx</span>
                        <span style={{ color: '#666' }}>482 lines • 25.3 KB</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>📄 src/main.tsx</span>
                        <span style={{ color: '#666' }}>24 lines • 0.8 KB</span>
                      </div>
                    </div>

                    <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>📄 README.md</span>
                        <span style={{ color: '#666' }}>7 lines • 375 B</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>📄 plan.md</span>
                        <span style={{ color: '#666' }}>422 lines • 43.2 KB</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* ARCHITECTURE BLOCK DIAGRAM */}
              <div style={{ marginTop: '36px' }}>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
                  PIPELINE ARCHITECTURE
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="bauhaus-border-all" style={{ padding: '16px', backgroundColor: '#000000', color: '#ffffff' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em' }}>PASS 1</span>
                    <p style={{ fontSize: '0.9rem', fontWeight: 700, marginTop: '4px' }}>Tree-sitter AST Symbol Table</p>
                  </div>
                  <div className="bauhaus-border-all" style={{ padding: '16px' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em' }}>PASS 2</span>
                    <p style={{ fontSize: '0.9rem', fontWeight: 700, marginTop: '4px' }}>Scoped Call & Import Resolver</p>
                  </div>
                  <div className="bauhaus-border-all" style={{ padding: '16px' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em' }}>RETRIEVAL</span>
                    <p style={{ fontSize: '0.9rem', fontWeight: 700, marginTop: '4px' }}>RRF Vector + Lexical Search</p>
                  </div>
                  <div className="bauhaus-border-all" style={{ padding: '16px', backgroundColor: '#000000', color: '#ffffff' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.15em' }}>EVALUATION</span>
                    <p style={{ fontSize: '0.9rem', fontWeight: 700, marginTop: '4px' }}>Evidence Cited GraphRAG</p>
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: PR IMPACT & DIAGNOSTICS */}
            <div style={{ padding: '32px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }} className="bauhaus-border-b">
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.1em', paddingBottom: '12px' }}>PR BLAST RADIUS RECENT SCANS</h2>
                <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>3 PULL REQUESTS</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {recentPRImpacts.map((item, idx) => (
                  <div key={idx} className="bauhaus-border-all" style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <span style={{ fontWeight: 800, fontSize: '0.95rem' }}>{item.pr}</span>
                      <span style={{ 
                        fontSize: '0.7rem', 
                        fontWeight: 800, 
                        padding: '4px 10px', 
                        border: '2px solid #000000',
                        backgroundColor: '#ffffff'
                      }}>
                        RISK: {item.risk}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '24px', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                      <span>AFFECTED SYMBOLS: <strong>{item.blastCount}</strong></span>
                      <span>FILES: <strong>{item.filesChanged}</strong></span>
                    </div>
                  </div>
                ))}
              </div>

              {/* SYSTEM DIAGNOSTICS LOG */}
              <div style={{ marginTop: '36px' }}>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
                  SYSTEM LOGS // STDIN
                </h2>
                <div className="bauhaus-border-all" style={{ padding: '16px', backgroundColor: '#000000', color: '#ffffff', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', lineHeight: '1.6' }}>
                  <div>[13:18:02] INFO: Ingested repository nishtha911/RepoScope</div>
                  <div>[13:18:03] INFO: Built HNSW vector index (dim=384, m=16)</div>
                  <div>[13:18:04] INFO: Scope resolution completed with 99.4% precision</div>
                  <div>[13:18:05] SUCCESS: Server listening on http://127.0.0.1:8000</div>
                </div>
              </div>
            </div>

          </div>
        )}

        {/* GRAPH TAB */}
        {activeTab === 'GRAPH' && (
          <div style={{ padding: '32px' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
              CODE GRAPH EXPLORER
            </h2>
            <div className="bauhaus-border-all" style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f9f9f9' }}>
              <div style={{ display: 'inline-block', border: '3px solid #000000', padding: '24px 40px', backgroundColor: '#ffffff', marginBottom: '20px' }}>
                <span style={{ fontSize: '1.2rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>[ AST NEIGHBORHOOD GRAPH VISUALIZER ]</span>
              </div>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', maxWidth: '600px', margin: '0 auto 24px' }}>
                Interactive NetworkX node traversal ready. Type any symbol name above to render 2-hop reverse reachability.
              </p>
              <button className="bauhaus-btn-invert" onClick={() => setActiveTab('OVERVIEW')}>
                RETURN TO OVERVIEW
              </button>
            </div>
          </div>
        )}

        {/* PR IMPACT TAB */}
        {activeTab === 'PR_IMPACT' && (
          <div style={{ padding: '32px' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
              DETERMINISTIC PR IMPACT ANALYSIS
            </h2>
            <div className="bauhaus-border-all" style={{ padding: '28px', backgroundColor: '#ffffff' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 800, letterSpacing: '0.15em', display: 'block', marginBottom: '12px' }}>
                SELECT GIT DIFF OR PR BRANCH
              </span>
              <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
                <input className="bauhaus-input" placeholder="e.g. main...feature/ast-resolver" />
                <button className="bauhaus-btn-invert">CALCULATE BLAST RADIUS</button>
              </div>
            </div>
          </div>
        )}

        {/* RAG TAB */}
        {activeTab === 'RAG' && (
          <div style={{ padding: '32px' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
              EVIDENCE-CITED GraphRAG ASSISTANT
            </h2>
            <div className="bauhaus-border-all" style={{ padding: '24px' }}>
              <textarea 
                className="bauhaus-input" 
                rows={4} 
                placeholder="Ask a question about the repository architecture or call flow..."
                style={{ resize: 'vertical', marginBottom: '16px' }}
              />
              <button className="bauhaus-btn-invert">GENERATE RESPONSE & CITATIONS</button>
            </div>
          </div>
        )}

        {/* RECOMMENDATIONS TAB */}
        {activeTab === 'RECOMMENDATIONS' && (
          <div style={{ padding: '32px' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '16px' }} className="bauhaus-border-b">
              RANKED ACTION RECOMMENDATIONS
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="bauhaus-border-all" style={{ padding: '20px' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', display: 'block', marginBottom: '6px' }}>PRIORITY #1 // LIGHTGBM SCORE: 0.94</span>
                <h3 style={{ fontSize: '1rem', fontWeight: 800 }}>Add test coverage for <code>SymbolResolver.resolve_calls()</code> pass</h3>
              </div>
              <div className="bauhaus-border-all" style={{ padding: '20px' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', display: 'block', marginBottom: '6px' }}>PRIORITY #2 // LIGHTGBM SCORE: 0.88</span>
                <h3 style={{ fontSize: '1rem', fontWeight: 800 }}>Optimize pgvector HNSW index parameters for large repositories</h3>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* FOOTER */}
      <footer className="bauhaus-border-t" style={{ padding: '20px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#000000', color: '#ffffff', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
        <div>REPOSCOPE // BAUHAUS DESIGN EDITION</div>
        <div>AST GRAPH &amp; GraphRAG POWERED</div>
      </footer>

    </div>
  );
}

