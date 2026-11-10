import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import RecommendationsBoard from './RecommendationsBoard';
import { sampleRecommendations } from '../fixtures/recommendations';

describe('RecommendationsBoard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('renders "What to Work on Next" recommendations board with header and mode badge', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    expect(screen.getByText('WHAT TO WORK ON NEXT')).toBeInTheDocument();
    expect(screen.getByText('OFFLINE FIXTURE MODE')).toBeInTheDocument();
    expect(screen.getByText(/nishtha911\/RepoScope/)).toBeInTheDocument();
    expect(screen.getByText('ALL FINDINGS (10)')).toBeInTheDocument();
  });

  it('lists top 10 ranked findings with ranks #01 to #10', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const cards = screen.getAllByTestId('recommendation-card');
    expect(cards).toHaveLength(10);

    const ranks = screen.getAllByTestId('rank-badge');
    expect(ranks[0]).toHaveTextContent('#01');
    expect(ranks[1]).toHaveTextContent('#02');
    expect(ranks[9]).toHaveTextContent('#10');

    // Verify top finding title
    expect(
      screen.getByText('Add test coverage for SymbolResolver.resolve_calls()'),
    ).toBeInTheDocument();
  });

  it('displays category tags with distinct labels', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const categoryTags = screen.getAllByTestId('category-tag');
    expect(categoryTags.length).toBeGreaterThanOrEqual(10);

    expect(screen.getAllByText('Untested Hotspot').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Complexity Hotspot').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('API Doc Gap').length).toBeGreaterThanOrEqual(1);
  });

  it('displays impact badges and priority scores for findings', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const impactBadges = screen.getAllByTestId('impact-badge');
    expect(impactBadges.length).toBeGreaterThanOrEqual(10);

    expect(screen.getAllByText('CRITICAL IMPACT').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('HIGH IMPACT').length).toBeGreaterThanOrEqual(1);

    // Verify priority scores
    const priorityScores = screen.getAllByTestId('priority-score');
    expect(priorityScores[0]).toHaveTextContent('0.94');
    expect(priorityScores[1]).toHaveTextContent('0.88');
    expect(priorityScores[2]).toHaveTextContent('0.82');
  });

  it('toggles rationale dropdowns to show detailed rationale and feature citations', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const firstItem = sampleRecommendations[0];
    const toggleBtn = screen.getByTestId(`rationale-toggle-${firstItem.id}`);

    // Dropdown panel is initially closed
    expect(screen.queryByTestId(`rationale-panel-${firstItem.id}`)).not.toBeInTheDocument();
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');

    // Click to expand
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId(`rationale-panel-${firstItem.id}`)).toBeInTheDocument();
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/SymbolResolver\.resolve_calls\(\) has a high measured fan-in of 14/i)).toBeInTheDocument();

    // Verify feature citations inside the rationale panel
    const citations = screen.getAllByTestId('citation-pill');
    expect(citations.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/fan_in:/i)).toBeInTheDocument();

    // Click again to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId(`rationale-panel-${firstItem.id}`)).not.toBeInTheDocument();
  });

  it('expands and collapses all rationales via the global toggle button', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const expandAllBtn = screen.getByRole('button', { name: /Toggle all rationale dropdowns/i });
    expect(expandAllBtn).toHaveTextContent('EXPAND ALL RATIONALES');

    // Click Expand All
    fireEvent.click(expandAllBtn);

    // All panels should now be open
    sampleRecommendations.forEach((item) => {
      expect(screen.getByTestId(`rationale-panel-${item.id}`)).toBeInTheDocument();
    });
    expect(expandAllBtn).toHaveTextContent('COLLAPSE ALL RATIONALES');

    // Click Collapse All
    fireEvent.click(expandAllBtn);
    sampleRecommendations.forEach((item) => {
      expect(screen.queryByTestId(`rationale-panel-${item.id}`)).not.toBeInTheDocument();
    });
    expect(expandAllBtn).toHaveTextContent('EXPAND ALL RATIONALES');
  });

  it('filters findings by category tab', () => {
    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    // Filter to Untested Hotspots
    const untestedTab = screen.getByRole('tab', { name: /UNTESTED HOTSPOTS/i });
    fireEvent.click(untestedTab);

    let cards = screen.getAllByTestId('recommendation-card');
    expect(cards).toHaveLength(4);
    expect(screen.getByText('Add test coverage for SymbolResolver.resolve_calls()')).toBeInTheDocument();
    expect(screen.queryByText('Refactor ASTGraphBuilder.build_dependency_matrix()')).not.toBeInTheDocument();

    // Filter to Complexity Hotspots
    const complexityTab = screen.getByRole('tab', { name: /COMPLEXITY HOTSPOTS/i });
    fireEvent.click(complexityTab);

    cards = screen.getAllByTestId('recommendation-card');
    expect(cards).toHaveLength(3);
    expect(screen.getByText('Refactor ASTGraphBuilder.build_dependency_matrix()')).toBeInTheDocument();

    // Filter back to All Findings
    const allTab = screen.getByRole('tab', { name: /ALL FINDINGS/i });
    fireEvent.click(allTab);

    cards = screen.getAllByTestId('recommendation-card');
    expect(cards).toHaveLength(10);
  });

  it('invokes onInspectSymbol callback when clicking inspect button inside rationale panel', () => {
    const onInspect = vi.fn();

    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
        onInspectSymbol={onInspect}
      />,
    );

    const firstItem = sampleRecommendations[0];
    const toggleBtn = screen.getByTestId(`rationale-toggle-${firstItem.id}`);
    fireEvent.click(toggleBtn);

    const inspectBtn = screen.getByRole('button', { name: /INSPECT SYMBOL IN GRAPH →/i });
    fireEvent.click(inspectBtn);

    expect(onInspect).toHaveBeenCalledWith(firstItem.symbol_id);
  });

  it('simulates refresh loading state in offline mode', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(
      <RecommendationsBoard
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={true}
      />,
    );

    const refreshBtn = screen.getByRole('button', { name: /Refresh recommendations/i });
    fireEvent.click(refreshBtn);

    expect(screen.getByText('REFRESHING…')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.getByText('↻ REFRESH')).toBeInTheDocument();
  });

  it('fetches live recommendations from API when offlinePreview is false', async () => {
    const mockResponse = {
      recommendations: [
        {
          id: 501,
          snapshot_id: 2,
          symbol_id: 99,
          file_id: 10,
          category: 'UNTESTED_HOTSPOT',
          title: 'Live API: Add tests for core engine',
          description: 'High impact live finding from backend DB.',
          score: 0.99,
          confidence: 0.98,
          rationale: 'Live backend calculation shows critical fan-in.',
          rationale_source: 'llm_constrained',
          rationale_degraded_reason: null,
          feature_citations: [{ feature: 'fan_in', value: 20 }],
          computed_features: { impact: 0.95, likelihood: 0.9, effort: 0.4, confidence: 0.98, score: 0.99 },
          detector_evidence: {},
        },
      ],
      repo_id: 42,
      snapshot_id: 2,
      commit_sha: 'deadbeef1234',
      run_id: 9,
      gaps: [],
    };

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }),
    );

    render(
      <RecommendationsBoard
        repoId={42}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
        apiBase="http://localhost:8000/api"
      />,
    );

    expect(await screen.findByText('Live API: Add tests for core engine')).toBeInTheDocument();
    expect(screen.getByText('0.99')).toBeInTheDocument();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      'http://localhost:8000/api/repos/42/recommendations?k=10',
    );
  });

  it('displays error banner with retry option when API request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Connection refused to backend')),
    );

    render(
      <RecommendationsBoard
        repoId={42}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
      />,
    );

    expect(
      await screen.findByText(/FAILED TO LOAD RECOMMENDATIONS/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Connection refused to backend')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /RETRY FETCH/i })).toBeInTheDocument();
  });
});
