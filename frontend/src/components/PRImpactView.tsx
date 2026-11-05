import React, { useState } from 'react';
import type {
  PRImpactReport,
  PRAnalysisHistoryItem,
  PRImpactRequestPayload,
} from '../types/prImpact';
import {
  samplePRUrls,
  sampleGitPatch,
  initialAnalysisHistory,
} from '../fixtures/prImpact';
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
          newReport = {
            pr_url: payload.pr_url,
            patch_name: null,
            risk_level: Number(prNum) % 2 === 0 ? 'LOW' : 'MEDIUM',
            risk_score: Number(prNum) % 2 === 0 ? 0.04 : 0.22,
            files_changed_count: 3,
            impacted_symbols_count: 14,
            affected_endpoints_count: Number(prNum) % 2 === 0 ? 0 : 2,
            impacted_tests_count: 2,
            summary: `Automated impact analysis for PR #${prNum}: verified AST modified symbol boundaries against PostgreSQL call graph.`,
          };
        } else {
          const lineCount = payload.patch?.split('\n').length || 10;
          title = `Raw Patch (${lineCount} lines)`;
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
            affected_endpoints_count:
              payload.patch?.includes('@router') ||
              payload.patch?.includes('@app')
                ? 1
                : 0,
            impacted_tests_count: payload.patch?.toLowerCase().includes('test')
              ? 2
              : 0,
            summary: `Evaluated pasted unified diff containing ${lineCount} lines across repository symbol boundaries.`,
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

  const getRiskBadgeClass = (riskLevel: string) => {
    switch (riskLevel) {
      case 'CRITICAL':
        return 'pr-risk-badge--critical';
      case 'HIGH':
        return 'pr-risk-badge--high';
      case 'MEDIUM':
        return 'pr-risk-badge--medium';
      case 'LOW':
      default:
        return 'pr-risk-badge--low';
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
        <section className="pr-impact-view__report-card bauhaus-border-b" aria-label="PR Impact Assessment Result">
          <div className="pr-impact-view__report-header">
            <div>
              <span className="pr-impact-view__report-tag">ACTIVE ASSESSMENT REPORT</span>
              <h3 className="pr-impact-view__report-title">
                {activeReport.pr_url || activeReport.patch_name || 'Pull Request Analysis'}
              </h3>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div className="pr-impact-view__risk-score-wrap">
                <span className="pr-impact-view__risk-score-label">RISK SCORE</span>
                <span className="pr-impact-view__risk-score-val">
                  {activeReport.risk_score.toFixed(2)}
                </span>
              </div>

              <span className={`pr-risk-badge ${getRiskBadgeClass(activeReport.risk_level)}`}>
                {activeReport.risk_level} RISK
              </span>
            </div>
          </div>

          {/* METRICS GRID */}
          <div className="pr-impact-view__metrics-grid">
            <div className="pr-impact-view__metric-box">
              <span className="pr-impact-view__metric-label">FILES CHANGED</span>
              <span className="pr-impact-view__metric-val">{activeReport.files_changed_count}</span>
            </div>
            <div className="pr-impact-view__metric-box">
              <span className="pr-impact-view__metric-label">IMPACTED SYMBOLS</span>
              <span className="pr-impact-view__metric-val">{activeReport.impacted_symbols_count}</span>
            </div>
            <div className="pr-impact-view__metric-box">
              <span className="pr-impact-view__metric-label">AFFECTED ENDPOINTS</span>
              <span className="pr-impact-view__metric-val">{activeReport.affected_endpoints_count}</span>
            </div>
            <div className="pr-impact-view__metric-box">
              <span className="pr-impact-view__metric-label">IMPACTED TESTS</span>
              <span className="pr-impact-view__metric-val">{activeReport.impacted_tests_count}</span>
            </div>
          </div>

          {/* SUMMARY RATIONALE */}
          <div className="pr-impact-view__summary-box">
            <strong>IMPACT SUMMARY: </strong>
            <span>{activeReport.summary}</span>
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
