import React from 'react';
import './Footer.css';

export type Tab =
  | 'OVERVIEW'
  | 'GRAPH'
  | 'PR_IMPACT'
  | 'RAG'
  | 'RECOMMENDATIONS';

interface Props {
  offlinePreview: boolean;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  apiHealth?: { status: string; v: string };
  isHealthError?: boolean;
}

const pipelineStages = [
  { id: 'ast', label: 'PASS 1: AST SCOPE MAP', status: 'READY' },
  { id: 'resolve', label: 'PASS 2: REF RESOLVER', status: 'ACTIVE' },
  { id: 'rrf', label: 'RETRIEVAL: RRF FUSION k=60', status: 'READY' },
  { id: 'rag', label: 'RAG: EVIDENCE PACK V1', status: 'VERIFIED' },
  { id: 'validator', label: 'EVAL: CITATION VALIDATOR', status: 'ACTIVE' },
];

const navigationTabs: { id: Tab; label: string; shortcut: string }[] = [
  { id: 'OVERVIEW', label: '01 // OVERVIEW & CODE', shortcut: '1' },
  { id: 'GRAPH', label: '02 // SYMBOL GRAPH', shortcut: '2' },
  { id: 'PR_IMPACT', label: '03 // PR IMPACT REVIEW', shortcut: '3' },
  { id: 'RAG', label: '04 // CODEBASE CHAT & RAG', shortcut: '4' },
  { id: 'RECOMMENDATIONS', label: '05 // ACTION RECOMMENDER', shortcut: '5' },
];

export const Footer: React.FC<Props> = ({
  offlinePreview,
  activeTab,
  onTabChange,
  apiHealth,
  isHealthError = false,
}) => {
  const beaconClass = offlinePreview
    ? 'bauhaus-beacon-dot--offline'
    : isHealthError
      ? 'bauhaus-beacon-dot--error'
      : 'bauhaus-beacon-dot';

  const statusLabel = offlinePreview
    ? 'OFFLINE FIXTURE PREVIEW · ZERO NETWORK'
    : isHealthError
      ? 'SERVER UNREACHABLE · RETRYING'
      : `ONLINE · FASTAPI GATEWAY v${apiHealth?.v || '1.0'}`;

  return (
    <footer className="bauhaus-footer" role="contentinfo" aria-label="System Footer">
      {/* Bauhaus Tricolor Stripe */}
      <div className="bauhaus-footer__stripe" aria-hidden="true">
        <div className="bauhaus-footer__stripe-blue" />
        <div className="bauhaus-footer__stripe-red" />
        <div className="bauhaus-footer__stripe-yellow" />
      </div>

      {/* Main 4-Column Grid */}
      <div className="bauhaus-footer__grid">
        {/* Column 1: Brand & Philosophy */}
        <div className="bauhaus-footer__col">
          <div className="bauhaus-footer__brand-wrap">
            <div className="bauhaus-footer__shapes" aria-hidden="true">
              <span className="bauhaus-shape-circle" />
              <span className="bauhaus-shape-square" />
              <span className="bauhaus-shape-triangle" />
            </div>
            <span className="bauhaus-footer__brand-title">REPOSCOPE</span>
          </div>

          <p className="bauhaus-footer__tagline">
            Multi-track Codebase Intelligence with Tree-sitter AST, PostgreSQL recursive CTEs,
            and deterministic GraphRAG.
          </p>

          <div style={{ fontSize: '0.72rem', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
            FORM FOLLOWS FUNCTION · ARCHITECTURE AS CODE
          </div>
        </div>

        {/* Column 2: System Pipelines */}
        <div className="bauhaus-footer__col">
          <h4 className="bauhaus-footer__col-heading">INTELLIGENCE PIPELINES</h4>

          <ul className="bauhaus-footer__pipeline-list">
            {pipelineStages.map((stage) => (
              <li key={stage.id} className="bauhaus-footer__pipeline-item">
                <span className="bauhaus-footer__pipeline-tag">{stage.label}</span>
                <span className="bauhaus-footer__pipeline-status">{stage.status}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Column 3: Navigation Views */}
        <div className="bauhaus-footer__col">
          <h4 className="bauhaus-footer__col-heading">WORKSPACE VIEWS</h4>

          <ul className="bauhaus-footer__nav-list">
            {navigationTabs.map((tab) => (
              <li key={tab.id}>
                <button
                  type="button"
                  className={`bauhaus-footer__nav-btn ${
                    activeTab === tab.id ? 'bauhaus-footer__nav-btn--active' : ''
                  }`}
                  onClick={() => onTabChange(tab.id)}
                  aria-pressed={activeTab === tab.id}
                >
                  <span>{activeTab === tab.id ? '▶' : '▷'}</span>
                  <span>{tab.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Column 4: System Specs & Telemetry */}
        <div className="bauhaus-footer__col">
          <h4 className="bauhaus-footer__col-heading">SYSTEM TELEMETRY</h4>

          <div className="bauhaus-footer__specs">
            <div className="bauhaus-footer__spec-row">
              <span className="bauhaus-footer__spec-label">PARSER:</span>
              <span className="bauhaus-footer__spec-val">Tree-sitter Python 3.11+</span>
            </div>

            <div className="bauhaus-footer__spec-row">
              <span className="bauhaus-footer__spec-label">STORE:</span>
              <span className="bauhaus-footer__spec-val">Neon PostgreSQL 16 + pgvector</span>
            </div>

            <div className="bauhaus-footer__spec-row">
              <span className="bauhaus-footer__spec-label">RANKER:</span>
              <span className="bauhaus-footer__spec-val">RRF Fusion (k=60) + BM25</span>
            </div>

            <div className="bauhaus-footer__spec-row">
              <span className="bauhaus-footer__spec-label">RELEASE:</span>
              <span className="bauhaus-footer__spec-val">v1.0.0-rc2 // Bauhaus Edition</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="bauhaus-footer__bottom">
        <div className="bauhaus-footer__status-beacon">
          <span className={`bauhaus-beacon-dot ${beaconClass}`} aria-hidden="true" />
          <span>STATUS: <strong>{statusLabel}</strong></span>
        </div>

        <div className="bauhaus-footer__shortcuts">
          <span>SHORTCUTS:</span>
          <span><kbd>⌘K</kbd> / <kbd>Ctrl+K</kbd> SEARCH</span>
          <span><kbd>/</kbd> CHAT</span>
          <span><kbd>ESC</kbd> CLOSE</span>
        </div>

        <div style={{ color: '#64748b' }}>
          REPOSCOPE © 2026 // MIT LICENSE
        </div>
      </div>
    </footer>
  );
};

export default Footer;
