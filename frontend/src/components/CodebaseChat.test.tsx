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
    expect(screen.getByText(/SIMULATING FIXTURE RESPONSE/i)).toBeInTheDocument();

    // Advance timers through streaming completion
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Finished streaming - streaming bar gone, metrics visible
    expect(screen.queryByText(/GENERATING STREAMING EVIDENCE RESPONSE/i)).not.toBeInTheDocument();
    expect(screen.getByText(/LATENCY:/i)).toBeInTheDocument();
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
});
