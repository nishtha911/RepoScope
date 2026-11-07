import React, { useState } from 'react';
import type { PRImpactReport } from '../types/prImpact';
import { normalizeRiskLevel, getRiskBadgeClass } from '../utils/prImpact';
import './PROverviewCard.css';

export interface PROverviewCardProps {
  report: PRImpactReport;
  title?: string;
  kicker?: string;
  onViewDetails?: () => void;
  compact?: boolean;
  className?: string;
}

export const PROverviewCard: React.FC<PROverviewCardProps> = ({
  report,
  title,
  kicker = 'PR BLAST RADIUS OVERVIEW',
  onViewDetails,
  compact = false,
  className = '',
}) => {
  const [copied, setCopied] = useState(false);
  const normalizedLevel = normalizeRiskLevel(report.risk_level);
  const badgeClass = getRiskBadgeClass(report.risk_level);

  const displayTitle =
    title ||
    report.pr_url ||
    report.patch_name ||
    'Pull Request Analysis';

  const handleCopySummary = async () => {
    try {
      await navigator.clipboard.writeText(
        `PR Risk: ${normalizedLevel} (${report.risk_score.toFixed(2)}) | Files: ${report.files_changed_count} | Symbols: ${report.impacted_symbols_count} | Endpoints: ${report.affected_endpoints_count}\n${report.summary}`,
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore clipboard write errors
    }
  };

  return (
    <article
      className={`pr-overview-card ${compact ? 'pr-overview-card--compact' : ''} ${className}`}
      aria-label={`PR Impact Overview: ${displayTitle}`}
    >
      {/* Top Header */}
      <header className="pr-overview-card__header">
        <div className="pr-overview-card__title-wrap">
          {kicker && <span className="pr-overview-card__kicker">{kicker}</span>}
          <h3 className="pr-overview-card__title">{displayTitle}</h3>
        </div>

        <div className="pr-overview-card__header-right">
          {/* Risk Level Badge (Low, Medium, High, Critical) */}
          <span
            className={`pr-risk-badge ${badgeClass}`}
            role="status"
            aria-label={`Risk Level: ${normalizedLevel}`}
            data-testid="risk-badge"
          >
            {normalizedLevel}
          </span>

          {/* Risk Score */}
          <div className="pr-overview-card__score-wrap">
            <span className="pr-overview-card__score-label">RISK SCORE</span>
            <span className="pr-overview-card__score-value">
              {report.risk_score.toFixed(2)}
            </span>
          </div>
        </div>
      </header>

      {/* Metrics Grid */}
      <div className="pr-overview-card__metrics-grid">
        {/* Metric 1: Impacted Files */}
        <div className="pr-overview-card__metric-item" data-testid="metric-files">
          <span className="pr-overview-card__metric-label">IMPACTED FILES</span>
          <span className="pr-overview-card__metric-value">
            {report.files_changed_count}
          </span>
          <span className="pr-overview-card__metric-sub">changed files in diff</span>
        </div>

        {/* Metric 2: Impacted Symbols */}
        <div className="pr-overview-card__metric-item" data-testid="metric-symbols">
          <span className="pr-overview-card__metric-label">IMPACTED SYMBOLS</span>
          <span className="pr-overview-card__metric-value">
            {report.impacted_symbols_count}
          </span>
          <span className="pr-overview-card__metric-sub">AST functions & classes</span>
        </div>

        {/* Metric 3: Affected Endpoints */}
        <div className="pr-overview-card__metric-item" data-testid="metric-endpoints">
          <span className="pr-overview-card__metric-label">AFFECTED ENDPOINTS</span>
          <span className="pr-overview-card__metric-value">
            {report.affected_endpoints_count}
          </span>
          <span className="pr-overview-card__metric-sub">exposed API routes</span>
        </div>

        {/* Metric 4: Impacted Tests */}
        <div className="pr-overview-card__metric-item" data-testid="metric-tests">
          <span className="pr-overview-card__metric-label">IMPACTED TESTS</span>
          <span className="pr-overview-card__metric-value">
            {report.impacted_tests_count}
          </span>
          <span className="pr-overview-card__metric-sub">linked verification suites</span>
        </div>
      </div>

      {/* Summary Rationale Box */}
      {report.summary && (
        <div className="pr-overview-card__summary">
          <strong className="pr-overview-card__summary-label">ASSESSMENT SUMMARY: </strong>
          <span className="pr-overview-card__summary-text">{report.summary}</span>
        </div>
      )}

      {/* Card Actions Footer */}
      <footer className="pr-overview-card__footer">
        <div className="pr-overview-card__footer-left">
          {report.pr_url && (
            <a
              href={report.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="pr-overview-card__link"
            >
              OPEN GITHUB PR ↗
            </a>
          )}
          <button
            type="button"
            className="pr-overview-card__btn-copy"
            onClick={handleCopySummary}
            aria-label="Copy summary to clipboard"
          >
            {copied ? '✓ COPIED' : 'COPY SUMMARY'}
          </button>
        </div>

        {onViewDetails && (
          <button
            type="button"
            className="bauhaus-btn-invert pr-overview-card__btn-details"
            onClick={onViewDetails}
          >
            VIEW FULL BLAST RADIUS →
          </button>
        )}
      </footer>
    </article>
  );
};

export default PROverviewCard;
