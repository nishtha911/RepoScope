import { useState } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import './PRImpactScreen.css';

interface PRImpactScreenProps {
  apiBase?: string;
  repoId?: number;
  repoName?: string;
  onExploreGraph?: (symbolName?: string) => void;
  onReviewRecommendations?: () => void;
}

interface ImpactReport {
  pr_url: string | null;
  patch_name: string | null;
  risk_level: string;
  risk_score: number;
  files_changed_count: number;
  impacted_symbols_count: number;
  affected_endpoints_count: number;
  impacted_tests_count: number;
  summary: string;
  impacted_tests: ImpactedTest[];
  missing_tests: MissingTest[];
  impacted_endpoints: ImpactedEndpoint[];
  feedback: 'pending' | 'accepted' | 'dismissed';
}

interface ImpactedTest {
  id: string;
  test_name: string;
  file_path: string;
  confidence: number;
}

interface MissingTest {
  symbol_id: number;
  symbol_name: string;
  file_path: string;
  reason: string;
}

interface ImpactedEndpoint {
  method: string;
  route: string;
  handler_name: string;
  file_path: string;
  confidence: number;
}

export default function PRImpactScreen({
  apiBase = 'http://localhost:8000/api',
  repoId,
  repoName,
  onReviewRecommendations,
}: PRImpactScreenProps) {
  const [prUrl, setPrUrl] = useState('');
  const [patch, setPatch] = useState('');
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<ImpactReport['feedback']>('pending');

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!repoId || (!prUrl.trim() && !patch.trim())) return;
    setError(null);
    setReport(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBase}/repos/${repoId}/pr-impact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_url: prUrl.trim() || null,
          patch: patch.trim() || null,
        }),
      });
      const data = (await response.json().catch(() => null)) as
        | ImpactReport
        | { error?: { message?: string }; detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(
          data && 'error' in data && data.error?.message
            ? data.error.message
            : data && 'detail' in data && data.detail
              ? data.detail
              : `PR analysis failed (HTTP ${response.status}).`,
        );
      }
      setReport(data as ImpactReport);
      setFeedback((data as ImpactReport).feedback ?? 'pending');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'PR analysis failed.');
    } finally {
      setIsLoading(false);
    }

  }

  async function submitFeedback(action: 'accepted' | 'dismissed') {
    if (!repoId || !report) return;
    setError(null);
    try {
      const analysisKey = report.pr_url ?? report.patch_name ?? 'unknown';
      const response = await fetch(
        `${apiBase}/repos/${repoId}/pr-impact/feedback?analysis_key=${encodeURIComponent(analysisKey)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        },
      );
      const data = (await response.json().catch(() => null)) as
        | { error?: { message?: string }; detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(
          data?.error?.message ?? data?.detail ?? `Feedback failed (HTTP ${response.status}).`,
        );
      }
      setFeedback(action);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Feedback failed.');
    }
  }

  return (
    <section className="reposcope-pr-impact-screen" aria-labelledby="pr-impact-heading">
      <header className="reposcope-page-header">
        <div>
          <h1 id="pr-impact-heading" className="reposcope-page-title">PR impact analysis</h1>
          <p className="reposcope-page-subtitle">
            Analyze a patch against {repoName ?? 'the selected repository'}.
          </p>
        </div>
        <button type="button" className="reposcope-inline-link-btn" onClick={onReviewRecommendations}>
          Review recommendations <ExternalLink size={13} />
        </button>
      </header>

      <form className="reposcope-pr-analysis-form" onSubmit={submit}>
        <label>
          Pull request URL
          <input value={prUrl} onChange={(event) => setPrUrl(event.target.value)} placeholder="https://github.com/org/repo/pull/123" />
        </label>
        <label>
          Or paste the generated patch
          <textarea value={patch} onChange={(event) => setPatch(event.target.value)} rows={12} placeholder="diff --git ..." />
        </label>
        <button type="submit" className="reposcope-primary-action-btn" disabled={isLoading || (!prUrl.trim() && !patch.trim())}>
          {isLoading ? <Loader2 className="reposcope-spin" size={16} /> : null}
          {isLoading ? 'Analyzing…' : 'Analyze patch'}
        </button>
      </form>

      {error && <p role="alert" className="reposcope-content-state">{error}</p>}
      {report && (
        <div className="reposcope-pr-result" aria-live="polite">
          <h2>{report.risk_level} risk · {Math.round(report.risk_score * 100)}%</h2>
          <p>{report.summary}</p>
          <dl>
            <div><dt>Files changed</dt><dd>{report.files_changed_count}</dd></div>
            <div><dt>Impacted symbols</dt><dd>{report.impacted_symbols_count}</dd></div>
            <div><dt>Affected endpoints</dt><dd>{report.affected_endpoints_count}</dd></div>
            <div><dt>Impacted tests</dt><dd>{report.impacted_tests_count}</dd></div>
          </dl>
          <div className="pr-impact-review-actions" role="group" aria-label="PR review feedback">
            <span>Was this analysis useful?</span>
            <button type="button" className={feedback === 'accepted' ? 'is-selected' : ''} onClick={() => void submitFeedback('accepted')}>
              Accept
            </button>
            <button type="button" className={feedback === 'dismissed' ? 'is-selected is-dismissed' : ''} onClick={() => void submitFeedback('dismissed')}>
              Dismiss
            </button>
          </div>
          <div className="pr-impact-detail-grid">
            <section aria-labelledby="impacted-tests-heading">
              <h3 id="impacted-tests-heading">Relevant tests ({report.impacted_tests.length})</h3>
              {report.impacted_tests.length === 0 ? (
                <p>No indexed TESTED_BY relationships were found.</p>
              ) : (
                <ul>
                  {report.impacted_tests.map((test) => (
                    <li key={test.id}>
                      <strong>{test.test_name}</strong>
                      <span>{test.file_path}</span>
                      <b>{Math.round(test.confidence * 100)}% confidence</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="missing-tests-heading">
              <h3 id="missing-tests-heading">Missing tests ({report.missing_tests.length})</h3>
              {report.missing_tests.length === 0 ? (
                <p>No missing TESTED_BY links were found.</p>
              ) : (
                <ul>
                  {report.missing_tests.map((test) => (
                    <li key={test.symbol_id}>
                      <strong>{test.symbol_name}</strong>
                      <span>{test.file_path}</span>
                      <b>{test.reason}</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="affected-routes-heading">
              <h3 id="affected-routes-heading">Affected routes ({report.impacted_endpoints.length})</h3>
              {report.impacted_endpoints.length === 0 ? (
                <p>No indexed affected routes were found.</p>
              ) : (
                <ul>
                  {report.impacted_endpoints.map((endpoint) => (
                    <li key={`${endpoint.method}-${endpoint.route}-${endpoint.handler_name}`}>
                      <strong>{endpoint.method} {endpoint.route}</strong>
                      <span>{endpoint.handler_name} · {endpoint.file_path}</span>
                      <b>{Math.round(endpoint.confidence * 100)}% confidence</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}
    </section>
  );
}
