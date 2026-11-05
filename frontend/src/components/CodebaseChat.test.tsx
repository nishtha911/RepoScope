import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import CodebaseChat from './CodebaseChat';

describe('CodebaseChat', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('renders chat interface with welcome message and suggestion chips', () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    expect(screen.getByText('CODEBASE CHAT // GRAPHRAG')).toBeInTheDocument();
    expect(screen.getByText('OFFLINE FIXTURE STREAM')).toBeInTheDocument();
    expect(screen.getByText(/nishtha911\/RepoScope/)).toBeInTheDocument();

    // Welcome message content
    expect(screen.getByText(/Hello! I am the/i)).toBeInTheDocument();

    // Suggestion chips
    expect(
      screen.getByRole('button', { name: /How does the two-pass AST reference resolver work\?/i }),
    ).toBeInTheDocument();
  });

  it('submits question when typing in textarea and pressing Enter', async () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const textarea = screen.getByRole('textbox', {
      name: /Ask a question about the repository/i,
    });
    fireEvent.change(textarea, { target: { value: 'How does the resolver work?' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // User message bubble appears
    expect(screen.getByText('How does the resolver work?')).toBeInTheDocument();

    // Streaming begins
    expect(screen.getByText(/GENERATING STREAMING EVIDENCE RESPONSE/i)).toBeInTheDocument();

    // Advance timers through streaming completion
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Finished streaming - streaming bar gone, metrics visible
    expect(screen.queryByText(/GENERATING STREAMING EVIDENCE RESPONSE/i)).not.toBeInTheDocument();
    expect(screen.getByText(/TOTAL:/i)).toBeInTheDocument();
  });

  it('clicking a starter suggestion chip submits the prompt immediately', async () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const chip = screen.getByRole('button', {
      name: /Explain the hybrid RRF search fusion algorithm with formula/i,
    });
    fireEvent.click(chip);

    // User message appears in messages log
    const matches = screen.getAllByText(
      'Explain the hybrid RRF search fusion algorithm with formula.',
    );
    expect(matches.length).toBeGreaterThanOrEqual(2);

    // Advance streaming timer
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Assistant response with RRF content rendered
    expect(screen.getByText(/Reciprocal Rank Fusion \(RRF\) Search/i)).toBeInTheDocument();
  });

  it('allows stopping active generation early', async () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const chip = screen.getByRole('button', {
      name: /How does the two-pass AST reference resolver work\?/i,
    });
    fireEvent.click(chip);

    // Verify streaming is active
    const stopBtn = screen.getByRole('button', { name: /Stop generation/i });
    expect(stopBtn).toBeInTheDocument();

    // Click stop
    fireEvent.click(stopBtn);

    // Stop button disappears immediately
    expect(screen.queryByRole('button', { name: /Stop generation/i })).not.toBeInTheDocument();
  });

  it('clears chat history when clicking CLEAR CHAT', () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const clearBtn = screen.getByRole('button', { name: /Clear chat messages/i });
    fireEvent.click(clearBtn);

    // Only initial welcome remains
    expect(screen.getByText(/Hello! I am the/i)).toBeInTheDocument();
  });

  it('expands referenced evidence drawer and triggers onSelectSymbol', () => {
    const onSelectSymbol = vi.fn();
    render(
      <CodebaseChat
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview
        onSelectSymbol={onSelectSymbol}
      />,
    );

    // Initial welcome message has citations [E1], [E2]
    const drawerToggle = screen.getByRole('button', { name: /Toggle referenced evidence list/i });
    expect(drawerToggle).toBeInTheDocument();
    expect(drawerToggle).toHaveAttribute('aria-expanded', 'false');

    // Click to expand drawer
    fireEvent.click(drawerToggle);
    expect(drawerToggle).toHaveAttribute('aria-expanded', 'true');

    // Evidence items are visible
    expect(screen.getByText('SymbolResolver.resolve_calls')).toBeInTheDocument();
    const inspectBtn = screen.getAllByRole('button', { name: /INSPECT SYMBOL →/i })[0];
    fireEvent.click(inspectBtn);

    expect(onSelectSymbol).toHaveBeenCalledWith(101);
  });

  it('handles live API errors gracefully with alert banner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Connection refused')),
    );

    render(
      <CodebaseChat
        repoId={1}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
      />,
    );

    const textarea = screen.getByRole('textbox', {
      name: /Ask a question about the repository/i,
    });
    fireEvent.change(textarea, { target: { value: 'Why did the server crash?' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // Wait for async rejection
    await act(async () => {
      vi.runAllTimers();
    });

    expect(
      await screen.findByText(/Failed to generate answer from server/i),
    ).toBeInTheDocument();
  });

  it('shows timing breakdown bar (retrieval, expansion, synthesis) after streaming completes', async () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    // Send a resolver question which uses the resolver fixture (timings defined)
    const chip = screen.getByRole('button', {
      name: /How does the two-pass AST reference resolver work\?/i,
    });
    fireEvent.click(chip);

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Timing breakdown bar should be visible
    expect(screen.getByLabelText('Pipeline timing breakdown')).toBeInTheDocument();
    expect(screen.getByText('PIPELINE TIMINGS')).toBeInTheDocument();
    expect(screen.getByText('Retrieval')).toBeInTheDocument();
    expect(screen.getByText('Graph Expansion')).toBeInTheDocument();
    expect(screen.getByText('LLM Synthesis')).toBeInTheDocument();
  });

  it('shows timing stages with correct ms labels for resolver fixture', async () => {
    render(<CodebaseChat repoId={1} repoName="nishtha911/RepoScope" offlinePreview />);

    const chip = screen.getByRole('button', {
      name: /How does the two-pass AST reference resolver work\?/i,
    });
    fireEvent.click(chip);

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Resolver fixture: retrieval=29, expansion=11, synthesis=78, total=118
    expect(screen.getByText('29ms')).toBeInTheDocument();
    expect(screen.getByText('11ms')).toBeInTheDocument();
    expect(screen.getByText('78ms')).toBeInTheDocument();
    // Total = 29+11+78 = 118
    expect(screen.getAllByText('118ms').length).toBeGreaterThanOrEqual(1);
  });

  it('wires online mode to POST /api/repos/{id}/ask and maps timings from response', async () => {
    const mockTimings = { retrieval_ms: 50, expansion_ms: 20, synthesis_ms: 130 };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          answer: 'Live answer from the API.',
          evidence: [],
          gaps: [],
          timings: mockTimings,
        }),
      }),
    );

    render(
      <CodebaseChat
        repoId={42}
        repoName="nishtha911/RepoScope"
        offlinePreview={false}
        apiBase="http://localhost:8000/api"
      />,
    );

    const textarea = screen.getByRole('textbox', {
      name: /Ask a question about the repository/i,
    });
    fireEvent.change(textarea, { target: { value: 'What is the blast radius?' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await act(async () => {
      vi.runAllTimers();
    });

    // Answer rendered
    expect(await screen.findByText('Live answer from the API.')).toBeInTheDocument();

    // Correct endpoint called
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      'http://localhost:8000/api/repos/42/ask',
      expect.objectContaining({ method: 'POST' }),
    );

    // Timing breakdown rendered
    expect(screen.getByText('50ms')).toBeInTheDocument();
    expect(screen.getByText('20ms')).toBeInTheDocument();
    expect(screen.getByText('130ms')).toBeInTheDocument();
    // Total = 200ms
    expect(screen.getByText('200ms')).toBeInTheDocument();
  });
});
