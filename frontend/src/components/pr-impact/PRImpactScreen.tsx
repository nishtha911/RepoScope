import { useState, type FormEvent } from 'react';
import { AlertCircle, Check, LoaderCircle, RotateCw, X } from 'lucide-react';
import { analyzePr, submitPrFeedback } from '../../api/prImpact';
import type { PRImpactReport } from '../../types/prImpact';
import './PRImpactScreen.css';

interface Props {
  repoId: number;
  onExploreGraph?: (symbolId?: number) => void;
}

function riskClass(level: string) {
  return `reposcope-risk--${level.toLowerCase()}`;
}

export default function PRImpactScreen({ repoId, onExploreGraph }: Props) {
  const [patch, setPatch] = useState('');
  const [report, setReport] = useState<PRImpactReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedbackPending, setFeedbackPending] = useState(false);

  async function handleAnalyze(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      setReport(await analyzePr(repoId, { patch: patch.trim() }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Patch analysis failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleFeedback(action: 'accepted' | 'dismissed') {
    if (!report || feedbackPending) return;
    setFeedbackPending(true);
    try {
      const digest = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(patch),
      );
      const analysisKey = `patch:${Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('')}`;
      await submitPrFeedback(repoId, analysisKey, action);
      setReport({ ...report, feedback: action });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Feedback could not be saved.');
    } finally {
      setFeedbackPending(false);
    }
  }

  return (
    <div className="reposcope-pr-screen">
      <header className="reposcope-page-header">
        <div>
          <span className="reposcope-eyebrow">PR IMPACT // DAY 14</span>
          <h1 className="reposcope-page-title">Change with confidence.</h1>
          <p className="reposcope-page-subtitle">
            Paste a unified git patch to analyze its live blast radius against the indexed graph.
          </p>
        </div>
      </header>

      <form className="reposcope-pr-submit" onSubmit={handleAnalyze}>
        <label htmlFor="patch-input">Unified git patch</label>
        <textarea
          id="patch-input"
          className="bauhaus-input reposcope-pr-submit__textarea"
          value={patch}
          onChange={(event) => setPatch(event.target.value)}
          placeholder="Paste the output of git diff or a provider-generated patch…"
          required
          maxLength={1_000_000}
        />
        <div className="reposcope-pr-submit__footer">
          <span>{patch.length.toLocaleString()} / 1,000,000 characters</span>
          <button type="submit" className="bauhaus-btn-invert" disabled={isSubmitting || !patch.trim()}>
            {isSubmitting ? <LoaderCircle className="reposcope-spin" size={15} /> : <RotateCw size={15} />}
            {isSubmitting ? 'ANALYZING…' : 'ANALYZE PATCH'}
          </button>
        </div>
      </form>

      {error && <div className="reposcope-form-error" role="alert"><AlertCircle size={16} /> {error}</div>}

      {report && (
        <section className="reposcope-pr-report" aria-live="polite">
          <div className="reposcope-pr-report__header">
            <div>
              <span className={`reposcope-risk-badge ${riskClass(report.risk_level)}`}>{report.risk_level}</span>
              <h2>{report.patch_name ?? 'Patch analysis'}</h2>
              <p>{report.summary}</p>
            </div>
            <div className="reposcope-pr-report__feedback">
              <span>Analysis feedback: {report.feedback}</span>
              <button type="button" className="bauhaus-btn" disabled={feedbackPending} onClick={() => void handleFeedback('accepted')}>
                <Check size={14} /> ACCEPT
              </button>
              <button type="button" className="bauhaus-btn" disabled={feedbackPending} onClick={() => void handleFeedback('dismissed')}>
                <X size={14} /> DISMISS
              </button>
            </div>
          </div>

          <div className="reposcope-telemetry-grid reposcope-pr-metrics-grid">
            <Metric label="Risk score" value={`${Math.round(report.risk_score * 100)} / 100`} />
            <Metric label="Files changed" value={report.files_changed_count} />
            <Metric label="Impacted symbols" value={report.impacted_symbols_count} />
            <Metric label="Affected endpoints" value={report.affected_endpoints_count} />
          </div>

          <div className="reposcope-pr-report__grid">
            <ReportList
              title="Impacted tests"
              empty="No impacted tests were linked."
              items={report.impacted_tests ?? []}
              render={(item) => `${String(item.test_name ?? item.id)} · ${String(item.file_path ?? '')}`}
            />
            <ReportList
              title="Missing tests"
              empty="No test gaps were detected."
              items={report.missing_tests ?? []}
              render={(item) => `${String(item.symbol_name ?? '')} · ${String(item.reason ?? '')}`}
              onSymbol={(item) => {
                const symbolId = Number(item.symbol_id);
                if (Number.isSafeInteger(symbolId) && symbolId > 0) onExploreGraph?.(symbolId);
              }}
            />
            <ReportList
              title="Impacted endpoints"
              empty="No affected endpoints were detected."
              items={report.impacted_endpoints ?? []}
              render={(item) => `${String(item.method ?? '')} ${String(item.route ?? '')} · ${String(item.handler_name ?? '')}`}
            />
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="reposcope-telemetry-card reposcope-telemetry-card--beige">
      <span className="reposcope-telemetry-card__label">{label}</span>
      <strong className="reposcope-telemetry-card__value">{value}</strong>
    </div>
  );
}

function ReportList<T extends object>({
  title,
  empty,
  items,
  render,
  onSymbol,
}: {
  title: string;
  empty: string;
  items: T[];
  render: (item: T) => string;
  onSymbol?: (item: T) => void;
}) {
  return (
    <section className="reposcope-report-list">
      <h3>{title} <span>{items.length}</span></h3>
      {items.length === 0 ? <p className="reposcope-muted">{empty}</p> : (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>
              <span>{render(item)}</span>
              {onSymbol && <button type="button" className="reposcope-inline-link-btn" onClick={() => onSymbol(item)}>INSPECT</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
