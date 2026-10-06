import { useState } from 'react';

type Tab = 'OVERVIEW' | 'GRAPH' | 'PR_IMPACT' | 'RAG' | 'RECOMMENDATIONS';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('OVERVIEW');
  const [selectedRepo, setSelectedRepo] = useState('nishtha911/RepoScope');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [newRepoUrl, setNewRepoUrl] = useState('');

  // Sample data for Bauhaus Dashboard
  const repos = [
    'nishtha911/RepoScope',
    'fastapi/fastapi',
    'pallets/flask',
    'psf/requests'
  ];

  const recentSymbols = [
    { name: 'SymbolResolver.resolve_calls()', type: 'METHOD', confidence: 'EXACT', file: 'backend/repolens/parsing/resolver.py', line: 142 },
    { name: 'GraphRAGPipeline.build_evidence_pack()', type: 'METHOD', confidence: 'EXACT', file: 'backend/repolens/rag/pipeline.py', line: 88 },
    { name: 'GitScanner.scan_repository()', type: 'FUNCTION', confidence: 'EXACT', file: 'backend/repolens/ingestion/scanner.py', line: 53 },
    { name: 'SymbolChunker.chunk_symbols()', type: 'FUNCTION', confidence: 'INFERRED', file: 'backend/repolens/retrieval/chunker.py', line: 29 },
    { name: 'PRImpactAnalyzer.calculate_blast_radius()', type: 'METHOD', confidence: 'EXACT', file: 'backend/repolens/recommendations/scorer.py', line: 110 }
  ];

  const recentPRImpacts = [
    { pr: '#42 Refactor resolver.py AST pass', risk: 'LOW (0.04)', blastCount: 14, filesChanged: 3 },
    { pr: '#41 Upgrade pgvector HNSW index params', risk: 'MED (0.18)', blastCount: 42, filesChanged: 7 },
    { pr: '#40 Add evidence pack validator', risk: 'LOW (0.01)', blastCount: 6, filesChanged: 2 },
  ];

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff', color: '#000000' }}>
      
      {/* TOP HEADER */}
      <header className="bauhaus-border-b" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'stretch', backgroundColor: '#ffffff' }}>
        <div className="bauhaus-border-r" style={{ padding: '20px 28px', backgroundColor: '#000000', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '24px', height: '24px', backgroundColor: '#ffffff' }}></div>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, letterSpacing: '0.12em' }}>REPOSCOPE</span>
        </div>

        <div className="bauhaus-border-r" style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase' }}>SYSTEM STATUS</span>
          <span style={{ fontSize: '0.95rem', fontWeight: 700, fontFamily: 'var(--font-mono)', marginTop: '2px' }}>[ READY // ONLINE ]</span>
        </div>

        <div className="bauhaus-border-r" style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'center', flexGrow: 1 }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase' }}>TARGET REPOSITORY</span>
          <select 
            value={selectedRepo}
            onChange={(e) => setSelectedRepo(e.target.value)}
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
            {repos.map(r => (
              <option key={r} value={r}>{r}</option>
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

      {/* REGISTER REPO EXPANDABLE PANEL */}
      {isRegistering && (
        <div className="bauhaus-border-b" style={{ padding: '24px 32px', backgroundColor: '#f5f5f5' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, letterSpacing: '0.1em', marginBottom: '12px' }}>REGISTER NEW REPOSITORY</h3>
          <div style={{ display: 'flex', gap: '12px', maxWidth: '800px' }}>
            <input 
              className="bauhaus-input"
              placeholder="e.g. https://github.com/owner/repository.git"
              value={newRepoUrl}
              onChange={(e) => setNewRepoUrl(e.target.value)}
            />
            <button className="bauhaus-btn-invert" onClick={() => setIsRegistering(false)}>
              INGEST & SCAN
            </button>
          </div>
        </div>
      )}

      {/* SEARCH AND CONTROL BAR */}
      <div className="bauhaus-border-b" style={{ display: 'flex', flexWrap: 'wrap', backgroundColor: '#ffffff' }}>
        <div style={{ flex: 1, minWidth: '300px', display: 'flex', alignItems: 'center' }} className="bauhaus-border-r">
          <span style={{ padding: '0 20px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>SEARCH:</span>
          <input 
            className="bauhaus-input"
            style={{ border: 'none', height: '100%', padding: '18px 20px' }}
            placeholder="TYPE SYMBOL, FILE PATH, OR NATURAL LANGUAGE QUERY..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div style={{ padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, letterSpacing: '0.1em' }}>AST ENGINE: TREE-SITTER // PYTHON 3.11</span>
        </div>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }} className="bauhaus-border-b">
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.1em', paddingBottom: '12px' }}>RECENT INGESTED SYMBOLS</h2>
                <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>5 SHOWN</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0px' }} className="bauhaus-border-all">
                {recentSymbols.map((s, idx) => (
                  <div 
                    key={idx} 
                    style={{ 
                      padding: '16px', 
                      backgroundColor: idx % 2 === 0 ? '#ffffff' : '#f9f9f9',
                      borderBottom: idx === recentSymbols.length - 1 ? 'none' : '1.5px solid #000000',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.9rem' }}>{s.name}</span>
                      <span style={{ 
                        fontSize: '0.65rem', 
                        fontWeight: 800, 
                        letterSpacing: '0.1em', 
                        padding: '2px 8px', 
                        backgroundColor: '#000000', 
                        color: '#ffffff' 
                      }}>
                        {s.type}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                      <span>{s.file}:{s.line}</span>
                      <span>CONFIDENCE: {s.confidence}</span>
                    </div>
                  </div>
                ))}
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

