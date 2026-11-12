import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import PRImpactView from './PRImpactView';

describe('PRImpactView', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('renders PR impact interface with header, tabs, and history table', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    expect(screen.getByText('PR IMPACT ANALYSIS // BLAST RADIUS ENGINE')).toBeInTheDocument();
    expect(screen.getByText('OFFLINE FIXTURE MODE')).toBeInTheDocument();
    expect(screen.getAllByText(/nishtha911\/RepoScope/).length).toBeGreaterThanOrEqual(1);

    // Tabs
    expect(screen.getByRole('tab', { name: /01 \/\/ GITHUB PULL REQUEST URL/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /02 \/\/ RAW GIT PATCH \/ UNIFIED DIFF/i })).toBeInTheDocument();

    // Initial Active Report
    expect(screen.getByText('ACTIVE ASSESSMENT REPORT')).toBeInTheDocument();
    expect(screen.getAllByText('RISK SCORE').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('metric-files')).toBeInTheDocument();
    expect(screen.getByTestId('metric-symbols')).toBeInTheDocument();
    expect(screen.getByTestId('metric-endpoints')).toBeInTheDocument();

    // History Table
    expect(screen.getByText('RECENT PR IMPACT ANALYSES')).toBeInTheDocument();
    expect(screen.getAllByText('#42 Refactor resolver.py AST pass').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('#41 Upgrade pgvector HNSW index params').length).toBeGreaterThanOrEqual(1);
  });

  it('validates invalid GitHub PR URLs and displays error message', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const input = screen.getByLabelText(/GITHUB PULL REQUEST URL/i);
    const submitBtn = screen.getByRole('button', { name: /ANALYZE PR IMPACT →/i });

    // Enter invalid URL
    fireEvent.change(input, { target: { value: 'https://example.com/not-a-pr' } });
    fireEvent.click(submitBtn);

    expect(
      screen.getByText(/Invalid GitHub Pull Request URL. Format: https:\/\/github.com\/owner\/repo\/pull\/123/i),
    ).toBeInTheDocument();
  });

  it('populates PR URL when clicking sample PR chip and submits analysis', async () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const sampleChip = screen.getByRole('button', { name: '#42 Refactor resolver.py AST pass' });
    fireEvent.click(sampleChip);

    const input = screen.getByLabelText(/GITHUB PULL REQUEST URL/i) as HTMLInputElement;
    expect(input.value).toBe('https://github.com/nishtha911/RepoScope/pull/42');

    const submitBtn = screen.getByRole('button', { name: /ANALYZE PR IMPACT →/i });
    fireEvent.click(submitBtn);

    // Shows loading state
    expect(screen.getByText('CALCULATING BLAST RADIUS…')).toBeInTheDocument();

    // Advance fake timers for fixture simulation
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // Submitting finishes, report updated
    expect(screen.queryByText('CALCULATING BLAST RADIUS…')).not.toBeInTheDocument();
    expect(screen.getAllByRole('status', { name: /risk level: low/i }).length).toBeGreaterThanOrEqual(1);
  });

  it('switches to raw git patch tab, loads sample patch, and submits', async () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const patchTab = screen.getByRole('tab', { name: /02 \/\/ RAW GIT PATCH/i });
    fireEvent.click(patchTab);

    // Textarea is present
    const textarea = screen.getByLabelText(/PASTE UNIFIED GIT PATCH/i) as HTMLTextAreaElement;
    expect(textarea).toBeInTheDocument();

    // Click Load Sample Patch
    const loadSampleBtn = screen.getByRole('button', { name: /LOAD SAMPLE PATCH/i });
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toContain('diff --git');

    // Submit analysis
    const submitBtn = screen.getByRole('button', { name: /ANALYZE RAW PATCH →/i });
    fireEvent.click(submitBtn);

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    expect(screen.getByText(/Evaluated pasted unified diff/i)).toBeInTheDocument();
  });

  it('clicking VIEW REPORT in the history table updates active report', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    // Click VIEW REPORT for PR #41
    const viewButtons = screen.getAllByRole('button', { name: /View report for/i });
    fireEvent.click(viewButtons[1]); // #41 is the 2nd item

    // Active report now reflects PR #41
    expect(
      screen.getAllByText('https://github.com/nishtha911/RepoScope/pull/41').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole('status', { name: /risk level: medium/i }).length).toBeGreaterThanOrEqual(1);
  });

  it('wires live API POST /api/repos/{id}/pr-impact in online mode', async () => {
    const mockReport = {
      pr_url: 'https://github.com/nishtha911/RepoScope/pull/99',
      risk_level: 'HIGH',
      risk_score: 0.65,
      files_changed_count: 12,
      impacted_symbols_count: 55,
      affected_endpoints_count: 4,
      impacted_tests_count: 8,
      summary: 'High blast radius modification touching core database schema.',
    };

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockReport,
      }),
    );

    render(
      <PRImpactView
        repoId={42}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
        apiBase="http://localhost:8000/api"
      />,
    );

    const input = screen.getByLabelText(/GITHUB PULL REQUEST URL/i);
    fireEvent.change(input, {
      target: { value: 'https://github.com/nishtha911/RepoScope/pull/99' },
    });

    const submitBtn = screen.getByRole('button', { name: /ANALYZE PR IMPACT →/i });
    fireEvent.click(submitBtn);

    await act(async () => {
      vi.runAllTimers();
    });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      'http://localhost:8000/api/repos/42/pr-impact',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          pr_url: 'https://github.com/nishtha911/RepoScope/pull/99',
        }),
      }),
    );

    expect(
      await screen.findByRole('status', { name: /risk level: high/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('0.65').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('High blast radius modification touching core database schema.')).toBeInTheDocument();
  });

  it('handles live API errors gracefully with error banner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Connection refused')),
    );

    render(
      <PRImpactView
        repoId={42}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
      />,
    );

    const input = screen.getByLabelText(/GITHUB PULL REQUEST URL/i);
    fireEvent.change(input, {
      target: { value: 'https://github.com/nishtha911/RepoScope/pull/99' },
    });

    const submitBtn = screen.getByRole('button', { name: /ANALYZE PR IMPACT →/i });
    fireEvent.click(submitBtn);

    await act(async () => {
      vi.runAllTimers();
    });

    expect(
      await screen.findByText(/Failed to calculate PR impact: Connection refused/i),
    ).toBeInTheDocument();
  });

  it('renders impacted tests and exposed endpoints panels with confidence badges', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    // Details Section Header
    expect(screen.getByText('DOWNSTREAM DEPENDENCY RIPPLE')).toBeInTheDocument();
    expect(screen.getByText('IMPACTED TESTS & EXPOSED ENDPOINTS')).toBeInTheDocument();

    // Feedback Action Bar
    expect(screen.getByText('STATUS: PENDING REVIEW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Accept recommendations/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dismiss analysis/i })).toBeInTheDocument();

    // Check panels
    expect(screen.getByTestId('affected-endpoints-panel')).toBeInTheDocument();
    expect(screen.getByTestId('impacted-tests-panel')).toBeInTheDocument();
    expect(screen.getByTestId('missing-tests-panel')).toBeInTheDocument();

    // Initial report #42 has relevant tests
    expect(screen.getByText('test_resolve_calls_exact_match')).toBeInTheDocument();
    expect(
      screen.getAllByText('backend/tests/unit/test_resolver.py').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('100% PATH')).toBeInTheDocument();

    // Initial report #42 has no missing tests
    expect(
      screen.getByText(/All modified production symbols have linked test coverage/i),
    ).toBeInTheDocument();
  });

  it('updates feedback status when clicking Accept and Dismiss buttons', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const acceptBtn = screen.getByRole('button', { name: /Accept recommendations/i });
    const dismissBtn = screen.getByRole('button', { name: /Dismiss analysis/i });

    // Initial status
    expect(screen.getByText('STATUS: PENDING REVIEW')).toBeInTheDocument();

    // Click Accept
    fireEvent.click(acceptBtn);
    expect(screen.getByText('✓ RECOMMENDATIONS ACCEPTED')).toBeInTheDocument();

    // Click Dismiss
    fireEvent.click(dismissBtn);
    expect(screen.getByText('✕ ANALYSIS DISMISSED')).toBeInTheDocument();
  });

  it('renders affected endpoints and missing test gaps when inspecting PR #41', () => {
    render(<PRImpactView repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    // Select PR #41 from history
    const viewButtons = screen.getAllByRole('button', { name: /View report for/i });
    fireEvent.click(viewButtons[1]); // PR #41

    // Endpoints for PR #41
    expect(screen.getByText('/api/repos/{id}/search')).toBeInTheDocument();
    expect(screen.getByText('search_repository')).toBeInTheDocument();
    expect(screen.getByText('94% CONFIDENCE')).toBeInTheDocument();

    // Missing test gap for PR #41
    expect(screen.getByText('tune_ef_search_param')).toBeInTheDocument();
    expect(
      screen.getByText(/Modified performance tuning callable lacks direct test coverage/i),
    ).toBeInTheDocument();
  });
});
