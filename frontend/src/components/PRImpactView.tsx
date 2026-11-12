import React, { useState } from 'react';
import type {
  PRImpactReport,
  PRAnalysisHistoryItem,
  PRImpactRequestPayload,
  PRFeedbackStatus,
} from '../types/prImpact';
import {
  samplePRUrls,
  sampleGitPatch,
  initialAnalysisHistory,
} from '../fixtures/prImpact';
import { PROverviewCard } from './PROverviewCard';
import { getRiskBadgeClass } from '../utils/prImpact';
import './PRImpactView.css';

interface Props {
  repoId: number;
  repoName: string;
  apiBase?: string;
  offlinePreview?: boolean;
}

const GITHUB_PR_REGEX = /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/;

function validatePRUrl(url: string): boolean {
  return GITHUB_PR_REGEX.test(url.trim());
}

export const PRImpactView: React.FC<Props> = ({
  repoId,
  repoName,
  apiBase = 'http://localhost:8000/api',
  offlinePreview = true,
}) => {
  const [activeInputTab, setActiveInputTab] = useState<'pr_url' | 'patch'>('pr_url');
  const [prUrl, setPrUrl] = useState('');
  const [rawPatch, setRawPatch] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeReport, setActiveReport] = useState<PRImpactReport | null>(
    initialAnalysisHistory[0] || null,
  );
  const [history, setHistory] = useState<PRAnalysisHistoryItem[]>(
    initialAnalysisHistory,
  );
  const [feedbackMap, setFeedbackMap] = useState<Record<string, PRFeedbackStatus>>({});

  const activeReportKey =
    activeReport?.pr_url || activeReport?.patch_name || 'active-report';
  const currentFeedback = feedbackMap[activeReportKey] || 'pending';

  const handleFeedback = (status: PRFeedbackStatus) => {
    setFeedbackMap((prev) => ({
      ...prev,
      [activeReportKey]: status,
    }));
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setValidationError(null);

    let payload: PRImpactRequestPayload = {};

    if (activeInputTab === 'pr_url') {
      const trimmed = prUrl.trim();
      if (!trimmed) {
        setValidationError('Please enter a GitHub Pull Request URL.');
        return;
      }
      if (!validatePRUrl(trimmed)) {
        setValidationError(
          'Invalid GitHub Pull Request URL. Format: https://github.com/owner/repo/pull/123',
        );
        return;
      }
      payload = { pr_url: trimmed };
    } else {
      const trimmed = rawPatch.trim();
      if (!trimmed) {
        setValidationError('Please paste a raw git patch or unified diff.');
        return;
      }
      payload = { patch: trimmed };
    }

    setIsSubmitting(true);

    if (offlinePreview) {
      // Deterministic fixture analysis simulation
      setTimeout(() => {
        let newReport: PRImpactReport;
        let title: string;

        if (activeInputTab === 'pr_url') {
          const prNumMatch = payload.pr_url?.match(/\/pull\/(\d+)/);
          const prNum = prNumMatch ? prNumMatch[1] : '99';
          title = `PR #${prNum} (${repoName})`;
          const isEven = Number(prNum) % 2 === 0;
          newReport = {
            pr_url: payload.pr_url,
            patch_name: null,
            risk_level: isEven ? 'LOW' : 'MEDIUM',
            risk_score: isEven ? 0.04 : 0.22,
            files_changed_count: 3,
            impacted_symbols_count: 14,
            affected_endpoints_count: isEven ? 0 : 2,
            impacted_tests_count: 2,
            summary: `Automated impact analysis for PR #${prNum}: verified AST modified symbol boundaries against PostgreSQL call graph.`,
            impacted_endpoints: isEven
              ? []
              : [
                  {
                    method: 'POST',
                    route: `/api/repos/${repoId}/search`,
                    handler_name: 'search_repository',
                    confidence: 0.94,
                  },
                  {
                    method: 'POST',
                    route: `/api/repos/${repoId}/ask`,
                    handler_name: 'ask_codebase',
                    confidence: 0.88,
                  },
                ],
            impacted_tests: [
              {
                id: `t-${prNum}-1`,
                test_name: `test_pr_${prNum}_behavior`,
                file_path: 'backend/tests/unit/test_resolver.py',
                confidence: 0.95,
              },
              {
                id: `t-${prNum}-2`,
                test_name: 'test_regression_suite',
                file_path: 'backend/tests/unit/test_regression.py',
                confidence: 0.82,
              },
            ],
            missing_tests: isEven
              ? []
              : [
                  {
                    symbol_name: 'compute_priority_score',
                    file_path: 'backend/reposcope/impact/risk_score.py',
                    reason: 'Modified AST callable lacks direct static test association',
                  },
                ],
          };
        } else {
          const lineCount = payload.patch?.split('\n').length || 10;
          title = `Raw Patch (${lineCount} lines)`;
          const hasEndpoints =
            payload.patch?.includes('@router') || payload.patch?.includes('@app');
          const hasTests = payload.patch?.toLowerCase().includes('test');
          newReport = {
            pr_url: null,
            patch_name: 'Pasted Unified Diff',
            risk_level: lineCount > 40 ? 'MEDIUM' : 'LOW',
            risk_score: Math.min(
              Number((0.02 + lineCount * 0.004).toFixed(2)),
              0.8,
            ),
            files_changed_count: Math.max(
              (payload.patch?.match(/diff --git/g) || []).length,
              1,
            ),
            impacted_symbols_count: Math.max(
              (payload.patch?.match(/def |class /g) || []).length,
              3,
            ),
            affected_endpoints_count: hasEndpoints ? 1 : 0,
            impacted_tests_count: hasTests ? 2 : 0,
            summary: `Evaluated pasted unified diff containing ${lineCount} lines across repository symbol boundaries.`,
            impacted_endpoints: hasEndpoints
              ? [
                  {
                    method: 'POST',
                    route: '/api/v1/resource',
                    handler_name: 'handle_resource',
                    confidence: 0.91,
                  },
                ]
              : [],
            impacted_tests: hasTests
              ? [
                  {
                    id: 'patch-t1',
                    test_name: 'test_patch_behavior',
                    file_path: 'backend/tests/unit/test_patch.py',
                    confidence: 1.0,
                  },
                ]
              : [],
            missing_tests: [
              {
                symbol_name: 'patch_target_symbol',
                file_path: 'backend/reposcope/impact/diff_parser.py',
                reason: 'Raw patch modifies core logic without verified test links',
              },
            ],
          };
        }

        const historyEntry: PRAnalysisHistoryItem = {
          ...newReport,
          id: `analysis-${Date.now()}`,
          title,
          analyzed_at: Date.now(),
          input_type: activeInputTab,
        };

        setActiveReport(newReport);
        setHistory((prev) => [historyEntry, ...prev]);
        setIsSubmitting(false);
      }, 300);
      return;
    }

    // Live API mode
    try {
      const response = await fetch(`${apiBase}/repos/${repoId}/pr-impact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(
          `Analysis API returned HTTP ${response.status}: ${response.statusText}`,
        );
      }

      const data = (await response.json()) as PRImpactReport;
      const title =
        data.pr_url ||
        data.patch_name ||
        `PR #${(data.pr_url || '').split('/').pop() || 'Analysis'}`;

      const historyEntry: PRAnalysisHistoryItem = {
        ...data,
        id: `analysis-${Date.now()}`,
        title,
        analyzed_at: Date.now(),
        input_type: activeInputTab,
      };

      setActiveReport(data);
      setHistory((prev) => [historyEntry, ...prev]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown server error';
      setValidationError(`Failed to calculate PR impact: ${msg}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="pr-impact-view" role="region" aria-label="PR Impact Analysis">
      {/* HEADER SECTION */}
      <header className="pr-impact-view__header bauhaus-border-b">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h2 className="pr-impact-view__title">PR IMPACT ANALYSIS // BLAST RADIUS ENGINE</h2>
            <span
              className={`pr-impact-view__mode-badge ${
                offlinePreview ? 'pr-impact-view__mode-badge--offline' : ''
              }`}
            >
              {offlinePreview ? 'OFFLINE FIXTURE MODE' : 'LIVE API POST /api/repos/{id}/pr-impact'}
            </span>
          </div>
          <p className="pr-impact-view__desc">
            Submit a GitHub Pull Request URL or paste raw unified git patch diffs to analyze downstream
            reverse-BFS ripple effects, affected AST symbols, and exposed API routes.
          </p>
        </div>

        <div className="pr-impact-view__repo-info">
          REPO: <strong>{repoName}</strong> (#{repoId})
        </div>
      </header>

      {/* SUBMISSION FORM SECTION */}
      <section className="pr-impact-view__submit-card bauhaus-border-b">
        <div className="pr-impact-view__tab-bar" role="tablist" aria-label="Input submission mode">
          <button
            type="button"
            role="tab"
            aria-selected={activeInputTab === 'pr_url'}
            className={`pr-impact-view__tab-btn ${
              activeInputTab === 'pr_url' ? 'pr-impact-view__tab-btn--active' : ''
            }`}
            onClick={() => {
              setActiveInputTab('pr_url');
              setValidationError(null);
            }}
          >
            01 // GITHUB PULL REQUEST URL
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeInputTab === 'patch'}
            className={`pr-impact-view__tab-btn ${
              activeInputTab === 'patch' ? 'pr-impact-view__tab-btn--active' : ''
            }`}
            onClick={() => {
              setActiveInputTab('patch');
              setValidationError(null);
            }}
          >
            02 // RAW GIT PATCH / UNIFIED DIFF
          </button>
        </div>

        <form onSubmit={handleSubmit} className="pr-impact-view__form">
          {activeInputTab === 'pr_url' ? (
            <div className="pr-impact-view__input-group">
              <label htmlFor="pr-url-input" className="pr-impact-view__label">
                GITHUB PULL REQUEST URL
              </label>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <input
                  id="pr-url-input"
                  type="url"
                  className="bauhaus-input pr-impact-view__text-input"
                  placeholder="https://github.com/owner/repository/pull/123"
                  value={prUrl}
                  onChange={(e) => setPrUrl(e.target.value)}
                  disabled={isSubmitting}
                  aria-invalid={!!validationError}
                  aria-describedby={validationError ? 'pr-url-error' : undefined}
                />
                <button
                  type="submit"
                  className="bauhaus-btn-invert pr-impact-view__submit-btn"
                  disabled={isSubmitting || !prUrl.trim()}
                >
                  {isSubmitting ? 'CALCULATING BLAST RADIUS…' : 'ANALYZE PR IMPACT →'}
                </button>
              </div>

              {/* Quick sample PR chips */}
              <div className="pr-impact-view__samples">
                <span className="pr-impact-view__samples-label">SAMPLE PRS:</span>
                {samplePRUrls.map((sample) => (
                  <button
                    key={sample.url}
                    type="button"
                    className="pr-impact-view__sample-chip"
                    onClick={() => {
                      setPrUrl(sample.url);
                      setValidationError(null);
                    }}
                    disabled={isSubmitting}
                  >
                    {sample.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="pr-impact-view__input-group">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label htmlFor="raw-patch-input" className="pr-impact-view__label">
                  PASTE UNIFIED GIT PATCH (DIFF)
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="bauhaus-btn"
                    style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                    onClick={() => {
                      setRawPatch(sampleGitPatch);
                      setValidationError(null);
                    }}
                    disabled={isSubmitting}
                  >
                    LOAD SAMPLE PATCH
                  </button>
                  <button
                    type="button"
                    className="bauhaus-btn"
                    style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                    onClick={() => setRawPatch('')}
                    disabled={isSubmitting || !rawPatch}
                  >
                    CLEAR
                  </button>
                </div>
              </div>

              <textarea
                id="raw-patch-input"
                className="bauhaus-input pr-impact-view__textarea"
                rows={8}
                placeholder="diff --git a/backend/reposcope/parsing/resolver.py b/backend/reposcope/parsing/resolver.py&#10;--- a/backend/reposcope/parsing/resolver.py&#10;+++ b/backend/reposcope/parsing/resolver.py&#10;@@ -142,6 +142,8 @@ def resolve_calls(self):..."
                value={rawPatch}
                onChange={(e) => setRawPatch(e.target.value)}
                disabled={isSubmitting}
              />

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
                <button
                  type="submit"
                  className="bauhaus-btn-invert pr-impact-view__submit-btn"
                  disabled={isSubmitting || !rawPatch.trim()}
                >
                  {isSubmitting ? 'CALCULATING BLAST RADIUS…' : 'ANALYZE RAW PATCH →'}
                </button>
              </div>
            </div>
          )}

          {validationError && (
            <div id="pr-url-error" className="pr-impact-view__error" role="alert">
              ⚠️ {validationError}
            </div>
          )}
        </form>
      </section>

      {/* ACTIVE REPORT CARD */}
      {activeReport && (
        <section className="pr-impact-view__report-container bauhaus-border-b" aria-label="PR Impact Assessment Result">
          <PROverviewCard
            report={activeReport}
            kicker="ACTIVE ASSESSMENT REPORT"
            title={activeReport.pr_url || activeReport.patch_name || 'Pull Request Analysis'}
          />
        </section>
      )}

      {/* DOWNSTREAM TARGETS: IMPACTED TESTS & ENDPOINTS DETAILS */}
      {activeReport && (
        <section
          className="pr-impact-view__details-section bauhaus-border-b"
          aria-label="Impacted Tests and Endpoints Analysis"
        >
          <div className="pr-impact-view__details-header">
            <div>
              <span className="pr-impact-view__details-kicker">DOWNSTREAM DEPENDENCY RIPPLE</span>
              <h3 className="pr-impact-view__details-title">
                IMPACTED TESTS & EXPOSED ENDPOINTS
              </h3>
            </div>

            {/* FEEDBACK ACTION BAR */}
            <div className="pr-impact-view__feedback-bar" role="group" aria-label="Review Actions">
              <span
                className={`pr-impact-view__feedback-status pr-impact-view__feedback-status--${currentFeedback}`}
                role="status"
              >
                {currentFeedback === 'accepted'
                  ? '✓ RECOMMENDATIONS ACCEPTED'
                  : currentFeedback === 'dismissed'
                  ? '✕ ANALYSIS DISMISSED'
                  : 'STATUS: PENDING REVIEW'}
              </span>
              <div className="pr-impact-view__feedback-actions">
                <button
                  type="button"
                  className={`bauhaus-btn-invert pr-impact-view__feedback-btn ${
                    currentFeedback === 'accepted' ? 'pr-impact-view__feedback-btn--active' : ''
                  }`}
                  onClick={() => handleFeedback('accepted')}
                  aria-label="Accept recommendations"
                >
                  ✓ ACCEPT RECOMMENDATIONS
                </button>
                <button
                  type="button"
                  className={`bauhaus-btn pr-impact-view__feedback-btn ${
                    currentFeedback === 'dismissed' ? 'pr-impact-view__feedback-btn--dismissed' : ''
                  }`}
                  onClick={() => handleFeedback('dismissed')}
                  aria-label="Dismiss analysis"
                >
                  ✕ DISMISS
                </button>
              </div>
            </div>
          </div>

          <div className="pr-impact-view__details-grid">
            {/* 01 // AFFECTED API ENDPOINTS */}
            <div className="pr-impact-view__details-card" data-testid="affected-endpoints-panel">
              <div className="pr-impact-view__card-heading">
                <h4 className="pr-impact-view__card-title">01 // AFFECTED API ROUTES</h4>
                <span className="pr-impact-view__card-count">
                  {(activeReport.impacted_endpoints || []).length}
                </span>
              </div>
              <p className="pr-impact-view__card-sub">
                Public API routes reachable downstream via BFS traversal from PR seed symbols.
              </p>
              {(!activeReport.impacted_endpoints || activeReport.impacted_endpoints.length === 0) ? (
                <div className="pr-impact-view__empty-box">
                  No public API routes reachable downstream from modified symbols.
                </div>
              ) : (
                <div className="pr-impact-view__items-list">
                  {activeReport.impacted_endpoints.map((ep, idx) => (
                    <div key={`${ep.method}-${ep.route}-${idx}`} className="pr-impact-view__endpoint-row">
                      <div className="pr-impact-view__endpoint-main">
                        <span className={`pr-impact-view__method-badge pr-impact-view__method-badge--${ep.method.toLowerCase()}`}>
                          {ep.method}
                        </span>
                        <code className="pr-impact-view__route-code">{ep.route}</code>
                      </div>
                      <div className="pr-impact-view__endpoint-meta">
                        <span className="pr-impact-view__handler-name">{ep.handler_name}</span>
                        <span className="pr-impact-view__confidence-tag">
                          {(ep.confidence * 100).toFixed(0)}% CONFIDENCE
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 02 // RELEVANT TESTS TO RUN */}
            <div className="pr-impact-view__details-card" data-testid="impacted-tests-panel">
              <div className="pr-impact-view__card-heading">
                <h4 className="pr-impact-view__card-title">02 // RELEVANT TESTS TO RUN</h4>
                <span className="pr-impact-view__card-count">
                  {(activeReport.impacted_tests || []).length}
                </span>
              </div>
              <p className="pr-impact-view__card-sub">
                Static test suites linked to modified callables that should be executed before merge.
              </p>
              {(!activeReport.impacted_tests || activeReport.impacted_tests.length === 0) ? (
                <div className="pr-impact-view__empty-box">
                  No existing tests directly cover the modified production callables.
                </div>
              ) : (
                <div className="pr-impact-view__items-list">
                  {activeReport.impacted_tests.map((test) => (
                    <div key={test.id} className="pr-impact-view__test-row">
                      <div className="pr-impact-view__test-main">
                        <span className="pr-impact-view__test-icon">⚡</span>
                        <code className="pr-impact-view__test-name">{test.test_name}</code>
                      </div>
                      <div className="pr-impact-view__test-meta">
                        <span className="pr-impact-view__file-path">{test.file_path}</span>
                        <span className="pr-impact-view__confidence-tag">
                          {(test.confidence * 100).toFixed(0)}% PATH
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 03 // TEST GAPS / UNTESTED CALLABLES */}
            <div className="pr-impact-view__details-card" data-testid="missing-tests-panel">
              <div className="pr-impact-view__card-heading">
                <h4 className="pr-impact-view__card-title">03 // MISSING TESTS (TEST GAPS)</h4>
                <span className="pr-impact-view__card-count pr-impact-view__card-count--warning">
                  {(activeReport.missing_tests || []).length}
                </span>
              </div>
              <p className="pr-impact-view__card-sub">
                Modified production symbols lacking static test coverage. Risk factor in assessment.
              </p>
              {(!activeReport.missing_tests || activeReport.missing_tests.length === 0) ? (
                <div className="pr-impact-view__empty-box pr-impact-view__empty-box--ok">
                  ✓ All modified production symbols have linked test coverage.
                </div>
              ) : (
                <div className="pr-impact-view__items-list">
                  {activeReport.missing_tests.map((mg, idx) => (
                    <div key={`${mg.symbol_name}-${idx}`} className="pr-impact-view__missing-row">
                      <div className="pr-impact-view__missing-main">
                        <span className="pr-impact-view__gap-badge">TEST GAP</span>
                        <code className="pr-impact-view__symbol-name">{mg.symbol_name}</code>
                      </div>
                      <p className="pr-impact-view__missing-reason">{mg.reason}</p>
                      <span className="pr-impact-view__file-path">{mg.file_path}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* RECENT ANALYSIS HISTORY TABLE */}
      <section className="pr-impact-view__history-section">
        <div className="pr-impact-view__history-header">
          <h3 className="pr-impact-view__history-title">RECENT PR IMPACT ANALYSES</h3>
          <span className="pr-impact-view__history-count">
            {history.length} {history.length === 1 ? 'RECORD' : 'RECORDS'}
          </span>
        </div>

        <div className="pr-impact-view__table-wrap">
          <table className="pr-impact-view__table" aria-label="PR Analysis History">
            <thead>
              <tr>
                <th>TARGET / PR REF</th>
                <th>TYPE</th>
                <th>RISK LEVEL</th>
                <th>RISK SCORE</th>
                <th>SYMBOLS</th>
                <th>FILES</th>
                <th>ENDPOINTS</th>
                <th>ANALYZED</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => {
                const isSelected = activeReport?.pr_url === item.pr_url &&
                  activeReport?.summary === item.summary;

                return (
                  <tr
                    key={item.id}
                    className={isSelected ? 'pr-impact-view__row--selected' : ''}
                  >
                    <td>
                      <strong className="pr-impact-view__table-title">{item.title}</strong>
                      {item.pr_url && (
                        <span className="pr-impact-view__table-url">{item.pr_url}</span>
                      )}
                    </td>
                    <td>
                      <span className="pr-impact-view__type-tag">
                        {item.input_type === 'pr_url' ? 'PR URL' : 'PATCH'}
                      </span>
                    </td>
                    <td>
                      <span className={`pr-risk-badge ${getRiskBadgeClass(item.risk_level)}`}>
                        {item.risk_level}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                      {item.risk_score.toFixed(2)}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{item.impacted_symbols_count}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{item.files_changed_count}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{item.affected_endpoints_count}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: '#64748b' }}>
                      {new Date(item.analyzed_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="bauhaus-btn-invert"
                        style={{ padding: '3px 8px', fontSize: '0.68rem' }}
                        onClick={() => setActiveReport(item)}
                        aria-label={`View report for ${item.title}`}
                      >
                        VIEW REPORT
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default PRImpactView;
