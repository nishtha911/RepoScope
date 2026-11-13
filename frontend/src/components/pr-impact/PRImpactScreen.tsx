import React, { useState } from 'react';
import {
  ExternalLink,
  RotateCw,
  ArrowRight,
} from 'lucide-react';

interface PRImpactScreenProps {
  onExploreGraph?: (symbolName?: string) => void;
}

interface SymbolItem {
  id: string;
  name: string;
  signature: string;
  path: string;
  lines: string;
  impact: 'Direct' | 'Transitive';
  depth: number;
  testStatus: 'Missing' | 'Covered';
  kind: string;
  isDirectChange: boolean;
  upstreamCallers: number;
  downstreamCallees: number;
  complexity: string;
}

export const PRImpactScreen: React.FC<PRImpactScreenProps> = ({
  onExploreGraph,
}) => {
  const [activeTab, setActiveTab] = useState<'symbols' | 'files' | 'routes'>('symbols');
  const [isReanalyzing, setIsReanalyzing] = useState(false);

  const symbolList: SymbolItem[] = [
    {
      id: 'authorizePayment',
      name: 'authorizePayment',
      signature: 'authorizePayment()',
      path: 'src/billing/authorize.ts',
      lines: 'L42-78',
      impact: 'Direct',
      depth: 0,
      testStatus: 'Missing',
      kind: 'Function',
      isDirectChange: true,
      upstreamCallers: 12,
      downstreamCallees: 5,
      complexity: '8 / moderate',
    },
    {
      id: 'createCheckout',
      name: 'createCheckout',
      signature: 'createCheckout()',
      path: 'src/api/checkout.ts',
      lines: 'L18-56',
      impact: 'Transitive',
      depth: 1,
      testStatus: 'Covered',
      kind: 'Function',
      isDirectChange: false,
      upstreamCallers: 4,
      downstreamCallees: 9,
      complexity: '12 / high',
    },
    {
      id: 'issueRefund',
      name: 'issueRefund',
      signature: 'issueRefund()',
      path: 'src/billing/refunds.ts',
      lines: 'L61-94',
      impact: 'Transitive',
      depth: 1,
      testStatus: 'Missing',
      kind: 'Function',
      isDirectChange: false,
      upstreamCallers: 3,
      downstreamCallees: 2,
      complexity: '4 / low',
    },
  ];

  const [selectedSymbol, setSelectedSymbol] = useState<SymbolItem>(symbolList[0]);

  const handleReanalyze = () => {
    setIsReanalyzing(true);
    setTimeout(() => {
      setIsReanalyzing(false);
    }, 800);
  };

  return (
    <div className="reposcope-pr-screen">
      {/* Page Header */}
      <div className="reposcope-page-header">
        <div>
          <h1 className="reposcope-page-title">Change with confidence.</h1>
          <p className="reposcope-page-subtitle">
            Understand every downstream consequence before you merge.
          </p>
        </div>
        <a
          href="https://github.com/nishtha911/RepoScope/pull/284"
          target="_blank"
          rel="noopener noreferrer"
          className="reposcope-primary-action-btn"
        >
          <ExternalLink size={15} strokeWidth={2.2} />
          <span>Open pull request</span>
        </a>
      </div>

      {/* PR Summary Card */}
      <div className="reposcope-pr-summary-card">
        <div className="reposcope-pr-summary-card__top">
          <div className="reposcope-pr-summary-card__title-group">
            <span className="reposcope-pr-summary-card__badge">PR #284</span>
            <h2 className="reposcope-pr-summary-card__title">
              Refactor payment authorization
            </h2>
          </div>

          <div className="reposcope-pr-summary-card__actions">
            <div className="reposcope-pr-summary-card__status-pill">
              <span className="reposcope-pr-summary-card__status-dot" />
              <span>{isReanalyzing ? 'Analyzing diff...' : 'Analysis complete'}</span>
            </div>

            <button
              type="button"
              className="reposcope-pr-summary-card__reanalyze-btn"
              onClick={handleReanalyze}
              disabled={isReanalyzing}
            >
              <RotateCw
                size={13}
                strokeWidth={2}
                className={isReanalyzing ? 'reposcope-spin' : ''}
              />
              <span>Re-analyze</span>
            </button>
          </div>
        </div>

        <div className="reposcope-pr-summary-card__meta-line">
          <span>
            acme/platform · feat/payment-auth → main · Updated 4 minutes ago
          </span>
          <span className="reposcope-pr-summary-card__diff-stat">
            <span style={{ color: '#2E7D32' }}>+186</span>{' '}
            <span style={{ color: '#C62828' }}>-94</span>
          </span>
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="reposcope-telemetry-grid reposcope-pr-metrics-grid">
        {/* Card 1: Risk score (Dark) */}
        <div className="reposcope-telemetry-card reposcope-telemetry-card--dark">
          <span className="reposcope-telemetry-card__label reposcope-telemetry-card__label--light">
            Risk score
          </span>
          <div className="reposcope-risk-card-body">
            <div className="reposcope-telemetry-card__value reposcope-telemetry-card__value--light">
              72 <span className="reposcope-risk-denominator">/ 100</span>
            </div>
            {/* Circular Progress Gauge */}
            <div className="reposcope-circular-gauge" aria-hidden="true">
              <svg viewBox="0 0 44 44" width="44" height="44">
                <circle
                  cx="22"
                  cy="22"
                  r="18"
                  fill="none"
                  stroke="#383936"
                  strokeWidth="3.5"
                />
                <circle
                  cx="22"
                  cy="22"
                  r="18"
                  fill="none"
                  stroke="var(--pastel-pink)"
                  strokeWidth="3.5"
                  strokeDasharray="113"
                  strokeDashoffset="31.6"
                  strokeLinecap="round"
                  transform="rotate(-90 22 22)"
                />
              </svg>
            </div>
          </div>
          <div className="reposcope-telemetry-card__sub reposcope-telemetry-card__sub--light">
            High risk · review recommended
          </div>
        </div>

        {/* Card 2: Modified files (Beige) */}
        <div className="reposcope-telemetry-card reposcope-telemetry-card--beige">
          <span className="reposcope-telemetry-card__label">Modified files</span>
          <div className="reposcope-telemetry-card__value">
            8 <span className="reposcope-unit">files</span>
          </div>
          <div className="reposcope-telemetry-card__sub">186 additions · 94 deletions</div>
        </div>

        {/* Card 3: Affected symbols (Blue) */}
        <div className="reposcope-telemetry-card reposcope-telemetry-card--blue">
          <span className="reposcope-telemetry-card__label">Affected symbols</span>
          <div className="reposcope-telemetry-card__value">
            47 <span className="reposcope-unit">symbols</span>
          </div>
          <div className="reposcope-telemetry-card__sub">8 direct · 39 transitive</div>
        </div>

        {/* Card 4: Impacted routes (Green) */}
        <div className="reposcope-telemetry-card reposcope-telemetry-card--green">
          <span className="reposcope-telemetry-card__label">Impacted routes</span>
          <div className="reposcope-telemetry-card__value">
            6 <span className="reposcope-unit">routes</span>
          </div>
          <div className="reposcope-telemetry-card__sub">3 routes have test gaps</div>
        </div>
      </div>

      {/* Middle Row: Impact Explorer & Symbol Inspector */}
      <div className="reposcope-pr-middle-row">
        {/* Left: Impact Explorer */}
        <div className="reposcope-impact-explorer-card">
          <div className="reposcope-impact-explorer-card__header">
            <h2 className="reposcope-impact-explorer-card__title">
              Impact explorer
            </h2>
            <span className="reposcope-impact-explorer-card__count">
              47 symbols
            </span>
          </div>

          {/* Tabs */}
          <div className="reposcope-impact-tabs">
            <button
              type="button"
              className={`reposcope-impact-tab ${
                activeTab === 'symbols' ? 'reposcope-impact-tab--active' : ''
              }`}
              onClick={() => setActiveTab('symbols')}
            >
              Affected symbols
            </button>
            <button
              type="button"
              className={`reposcope-impact-tab ${
                activeTab === 'files' ? 'reposcope-impact-tab--active' : ''
              }`}
              onClick={() => setActiveTab('files')}
            >
              Modified files <span className="reposcope-tab-count">8</span>
            </button>
            <button
              type="button"
              className={`reposcope-impact-tab ${
                activeTab === 'routes' ? 'reposcope-impact-tab--active' : ''
              }`}
              onClick={() => setActiveTab('routes')}
            >
              API routes <span className="reposcope-tab-count">6</span>
            </button>
          </div>

          {/* Table */}
          <div className="reposcope-impact-table-wrap">
            <table className="reposcope-impact-table">
              <thead>
                <tr>
                  <th style={{ width: '45%' }}>SYMBOL / SOURCE</th>
                  <th style={{ width: '20%' }}>IMPACT</th>
                  <th style={{ width: '15%' }}>DEPTH</th>
                  <th style={{ width: '20%' }}>TESTS</th>
                </tr>
              </thead>
              <tbody>
                {symbolList.map((item) => {
                  const isSelected = selectedSymbol.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      className={`reposcope-impact-table__row ${
                        isSelected ? 'reposcope-impact-table__row--selected' : ''
                      }`}
                      onClick={() => setSelectedSymbol(item)}
                    >
                      <td>
                        <div className="reposcope-impact-table__symbol-name">
                          {item.name}
                        </div>
                        <div className="reposcope-impact-table__symbol-path">
                          {item.path}:{item.lines.replace('L', '')}
                        </div>
                      </td>
                      <td>
                        <span className="reposcope-impact-table__impact-badge">
                          {item.impact}
                        </span>
                      </td>
                      <td>
                        <span className="reposcope-impact-table__depth">
                          {item.depth}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`reposcope-test-badge ${
                            item.testStatus === 'Covered'
                              ? 'reposcope-test-badge--covered'
                              : 'reposcope-test-badge--missing'
                          }`}
                        >
                          {item.testStatus}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          <div className="reposcope-impact-explorer-card__footer">
            <span>Showing 3 of 47 affected symbols</span>
            <button
              type="button"
              className="reposcope-inline-link-btn"
              onClick={() => onExploreGraph?.()}
            >
              <span>View all symbols</span>
              <ExternalLink size={13} strokeWidth={1.75} />
            </button>
          </div>
        </div>

        {/* Right: Selected Symbol Inspector */}
        <div className="reposcope-symbol-inspector-card">
          <div>
            <div className="reposcope-symbol-inspector-card__top">
              <span className="reposcope-symbol-inspector-card__label">
                SYMBOL INSPECTOR
              </span>
              <button
                type="button"
                className="reposcope-symbol-inspector-card__icon-btn"
                onClick={() => onExploreGraph?.(selectedSymbol.name)}
                aria-label="Inspect symbol"
              >
                <ExternalLink size={14} strokeWidth={1.75} />
              </button>
            </div>

            <h3 className="reposcope-symbol-inspector-card__title">
              {selectedSymbol.signature}
            </h3>
            <p className="reposcope-symbol-inspector-card__sub">
              {selectedSymbol.path} · {selectedSymbol.lines}
            </p>

            <div className="reposcope-symbol-inspector-card__badges">
              <span className="reposcope-badge reposcope-badge--neutral">
                {selectedSymbol.kind}
              </span>
              {selectedSymbol.isDirectChange && (
                <span className="reposcope-badge reposcope-badge--beige">
                  Direct change
                </span>
              )}
            </div>

            <div className="reposcope-symbol-inspector-card__list">
              <div className="reposcope-symbol-inspector-card__row">
                <span className="reposcope-symbol-inspector-card__key">
                  Upstream callers
                </span>
                <span className="reposcope-symbol-inspector-card__val">
                  {selectedSymbol.upstreamCallers}
                </span>
              </div>
              <div className="reposcope-symbol-inspector-card__row">
                <span className="reposcope-symbol-inspector-card__key">
                  Downstream callees
                </span>
                <span className="reposcope-symbol-inspector-card__val">
                  {selectedSymbol.downstreamCallees}
                </span>
              </div>
              <div className="reposcope-symbol-inspector-card__row">
                <span className="reposcope-symbol-inspector-card__key">
                  Cyclomatic complexity
                </span>
                <span className="reposcope-symbol-inspector-card__val">
                  {selectedSymbol.complexity}
                </span>
              </div>
            </div>
          </div>

          <button
            type="button"
            className="reposcope-full-action-btn"
            onClick={() => onExploreGraph?.(selectedSymbol.name)}
          >
            <span>Explore full dependency graph</span>
            <ExternalLink size={13} strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* Bottom Row: Follow the impact & Before you merge */}
      <div className="reposcope-pr-bottom-row">
        {/* Left: Follow the Impact Call Chain */}
        <div className="reposcope-impact-chain-card">
          <div className="reposcope-impact-chain-card__header">
            <div>
              <div className="reposcope-impact-chain-card__top-line">
                <h2 className="reposcope-impact-chain-card__title">
                  Follow the impact
                </h2>
                <span className="reposcope-impact-chain-card__hops-badge">
                  2 hops
                </span>
              </div>
              <p className="reposcope-impact-chain-card__subtitle">
                One changed function. Multiple downstream paths.
              </p>
            </div>
          </div>

          {/* Chain Nodes Flow */}
          <div className="reposcope-chain-flow">
            <div className="reposcope-chain-node reposcope-chain-node--green">
              <div className="reposcope-chain-node__name">POST /checkout</div>
              <div className="reposcope-chain-node__sub">API route</div>
            </div>

            <ArrowRight size={18} strokeWidth={1.75} className="reposcope-chain-arrow" />

            <div className="reposcope-chain-node reposcope-chain-node--blue">
              <div className="reposcope-chain-node__name">createCheckout()</div>
              <div className="reposcope-chain-node__sub">Caller · L18-56</div>
            </div>

            <ArrowRight size={18} strokeWidth={1.75} className="reposcope-chain-arrow" />

            <div className="reposcope-chain-node reposcope-chain-node--pink">
              <div className="reposcope-chain-node__name">authorizePayment()</div>
              <div className="reposcope-chain-node__sub">Changed · L42-78</div>
            </div>
          </div>

          <div className="reposcope-impact-chain-card__footer">
            <span className="reposcope-evidence-line">
              Evidence: src/api/checkout.ts:31 → src/billing/authorize.ts:42
            </span>
            <span className="reposcope-confidence-label">100% confidence</span>
          </div>
        </div>

        {/* Right: Before You Merge (Yellow Panel) */}
        <div className="reposcope-before-merge-card">
          <div>
            <div className="reposcope-before-merge-card__top">
              <h2 className="reposcope-before-merge-card__title">
                Before you merge
              </h2>
              <span className="reposcope-before-merge-card__badge">
                3 gaps
              </span>
            </div>

            <p className="reposcope-before-merge-card__sub">
              9 of 12 impacted tests cover this change.
            </p>

            {/* Progress Bar */}
            <div className="reposcope-progress-track">
              <div
                className="reposcope-progress-fill"
                style={{ width: `${(9 / 12) * 100}%` }}
              />
            </div>

            {/* Missing Coverage */}
            <div className="reposcope-missing-coverage-section">
              <span className="reposcope-missing-coverage-title">
                Missing coverage
              </span>
              <ul className="reposcope-missing-coverage-list">
                <li>
                  <span className="reposcope-list-idx">01</span>
                  <span className="reposcope-list-route">POST /api/refunds</span>
                </li>
                <li>
                  <span className="reposcope-list-idx">02</span>
                  <span className="reposcope-list-route">POST /api/payments/retry</span>
                </li>
                <li>
                  <span className="reposcope-list-idx">03</span>
                  <span className="reposcope-list-route">GET /api/payments/:id/status</span>
                </li>
              </ul>
            </div>
          </div>

          <button
            type="button"
            className="reposcope-inline-link-btn reposcope-before-merge-link"
            onClick={() => onExploreGraph?.('authorizePayment')}
          >
            <span>Review suggested tests</span>
            <ExternalLink size={13} strokeWidth={1.75} />
          </button>
        </div>
      </div>
    </div>
  );
};
export default PRImpactScreen;
