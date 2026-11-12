import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PROverviewCard from './PROverviewCard';
import { normalizeRiskLevel, getRiskBadgeClass } from '../utils/prImpact';
import type { PRImpactReport } from '../types/prImpact';

describe('PROverviewCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const baseReport: PRImpactReport = {
    pr_url: 'https://github.com/nishtha911/RepoScope/pull/42',
    patch_name: null,
    risk_level: 'Low',
    risk_score: 0.04,
    files_changed_count: 3,
    impacted_symbols_count: 14,
    affected_endpoints_count: 1,
    impacted_tests_count: 2,
    summary: 'Refactor AST parsing with low downstream blast radius.',
  };

  describe('Utility functions', () => {
    it('normalizes risk levels correctly', () => {
      expect(normalizeRiskLevel('LOW')).toBe('Low');
      expect(normalizeRiskLevel('Low')).toBe('Low');
      expect(normalizeRiskLevel('MEDIUM')).toBe('Medium');
      expect(normalizeRiskLevel('Medium')).toBe('Medium');
      expect(normalizeRiskLevel('med')).toBe('Medium');
      expect(normalizeRiskLevel('HIGH')).toBe('High');
      expect(normalizeRiskLevel('High')).toBe('High');
      expect(normalizeRiskLevel('CRITICAL')).toBe('Critical');
      expect(normalizeRiskLevel('Critical')).toBe('Critical');
    });

    it('assigns correct CSS class for each risk level', () => {
      expect(getRiskBadgeClass('Low')).toBe('pr-risk-badge--low');
      expect(getRiskBadgeClass('Medium')).toBe('pr-risk-badge--medium');
      expect(getRiskBadgeClass('High')).toBe('pr-risk-badge--high');
      expect(getRiskBadgeClass('Critical')).toBe('pr-risk-badge--critical');
    });
  });

  describe('Risk Level Badges', () => {
    const riskCases: Array<{
      level: 'Low' | 'Medium' | 'High' | 'Critical';
      expectedClass: string;
    }> = [
      { level: 'Low', expectedClass: 'pr-risk-badge--low' },
      { level: 'Medium', expectedClass: 'pr-risk-badge--medium' },
      { level: 'High', expectedClass: 'pr-risk-badge--high' },
      { level: 'Critical', expectedClass: 'pr-risk-badge--critical' },
    ];

    riskCases.forEach(({ level, expectedClass }) => {
      it(`renders "${level}" risk level badge with class "${expectedClass}"`, () => {
        const report: PRImpactReport = {
          ...baseReport,
          risk_level: level,
        };

        render(<PROverviewCard report={report} />);

        const badge = screen.getByRole('status', { name: new RegExp(`Risk Level: ${level}`, 'i') });
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass(expectedClass);
        expect(badge.textContent).toBe(level);
      });
    });
  });

  describe('Metrics and Blast Radius Display', () => {
    it('displays impacted files, symbols, affected endpoints, and impacted tests count', () => {
      render(<PROverviewCard report={baseReport} />);

      // Impacted files count
      const filesMetric = screen.getByTestId('metric-files');
      expect(filesMetric).toBeInTheDocument();
      expect(filesMetric).toHaveTextContent('3');
      expect(filesMetric).toHaveTextContent(/IMPACTED FILES/i);

      // Impacted symbols count
      const symbolsMetric = screen.getByTestId('metric-symbols');
      expect(symbolsMetric).toBeInTheDocument();
      expect(symbolsMetric).toHaveTextContent('14');
      expect(symbolsMetric).toHaveTextContent(/IMPACTED SYMBOLS/i);

      // Affected endpoints count
      const endpointsMetric = screen.getByTestId('metric-endpoints');
      expect(endpointsMetric).toBeInTheDocument();
      expect(endpointsMetric).toHaveTextContent('1');
      expect(endpointsMetric).toHaveTextContent(/AFFECTED ENDPOINTS/i);

      // Impacted tests count
      const testsMetric = screen.getByTestId('metric-tests');
      expect(testsMetric).toBeInTheDocument();
      expect(testsMetric).toHaveTextContent('2');
      expect(testsMetric).toHaveTextContent(/IMPACTED TESTS/i);

      // Risk score
      expect(screen.getByText('0.04')).toBeInTheDocument();

      // Summary
      expect(screen.getByText(/Refactor AST parsing with low downstream blast radius/i)).toBeInTheDocument();
    });

    it('renders custom title if provided', () => {
      render(<PROverviewCard report={baseReport} title="Custom PR Blast Radius #42" />);
      expect(screen.getByText('Custom PR Blast Radius #42')).toBeInTheDocument();
    });

    it('renders fallback title when neither title nor pr_url is present', () => {
      const patchReport: PRImpactReport = {
        ...baseReport,
        pr_url: null,
        patch_name: null,
      };
      render(<PROverviewCard report={patchReport} />);
      expect(screen.getByText('Pull Request Analysis')).toBeInTheDocument();
    });
  });

  describe('Actions & Interactivity', () => {
    it('copies assessment summary to clipboard when clicking COPY SUMMARY', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      render(<PROverviewCard report={baseReport} />);

      const copyBtn = screen.getByRole('button', { name: /Copy summary to clipboard/i });
      expect(copyBtn).toHaveTextContent('COPY SUMMARY');

      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(writeTextMock).toHaveBeenCalledWith(
          expect.stringContaining('PR Risk: Low (0.04) | Files: 3 | Symbols: 14 | Endpoints: 1'),
        );
      });

      expect(copyBtn).toHaveTextContent('✓ COPIED');
    });

    it('invokes onViewDetails callback when VIEW FULL BLAST RADIUS button is clicked', () => {
      const onViewDetails = vi.fn();
      render(<PROverviewCard report={baseReport} onViewDetails={onViewDetails} />);

      const detailsBtn = screen.getByRole('button', { name: /VIEW FULL BLAST RADIUS →/i });
      fireEvent.click(detailsBtn);

      expect(onViewDetails).toHaveBeenCalledTimes(1);
    });

    it('renders link to GitHub PR when pr_url is present', () => {
      render(<PROverviewCard report={baseReport} />);

      const link = screen.getByRole('link', { name: /OPEN GITHUB PR ↗/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', 'https://github.com/nishtha911/RepoScope/pull/42');
      expect(link).toHaveAttribute('target', '_blank');
    });

    it('applies compact styling when compact prop is true', () => {
      const { container } = render(<PROverviewCard report={baseReport} compact />);
      const article = container.querySelector('.pr-overview-card');
      expect(article).toHaveClass('pr-overview-card--compact');
    });
  });
});
