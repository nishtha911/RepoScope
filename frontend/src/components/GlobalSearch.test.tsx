import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import GlobalSearch from './GlobalSearch';

const mockHits = [
  {
    symbol_id: 101,
    name: 'resolve_calls',
    score: 0.95,
    file_path: 'backend/reposcope/parsing/resolver.py',
    snippet: 'def resolve_calls(self, repo_id: int):',
    category: 'symbol' as const,
  },
  {
    symbol_id: 201,
    name: 'GET /api/repos/{id}/search',
    score: 0.88,
    file_path: 'backend/reposcope/api/repos.py',
    snippet: '@router.post("/{repo_id}/search")',
    category: 'endpoint' as const,
  },
  {
    symbol_id: 301,
    name: 'Architecture Overview',
    score: 0.72,
    file_path: 'docs/architecture.md',
    snippet: '# RepoScope Architecture Guide',
    category: 'documentation' as const,
  },
];

interface HarnessProps {
  repoId?: number;
  offlinePreview?: boolean;
  onSelectSymbol?: (id: number) => void;
  onLatencyChange?: (ms: number) => void;
  initialQuery?: string;
}

function Harness({
  repoId = 1,
  offlinePreview = false,
  onSelectSymbol,
  onLatencyChange,
  initialQuery = '',
}: HarnessProps) {
  const [query, setQuery] = useState(initialQuery);
  return (
    <GlobalSearch
      repoId={repoId}
      repoName="RepoScope"
      query={query}
      onQueryChange={setQuery}
      offlinePreview={offlinePreview}
      onSelectSymbol={onSelectSymbol}
      onLatencyChange={onLatencyChange}
    />
  );
}

function mount(props: HarnessProps = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const view = render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
    </QueryClientProvider>,
  );

  return { ...view, client };
}

function mockSuccessfulSearch(hits = mockHits, query = 'resolve') {
  const mockFetch = vi.fn().mockImplementation(async () => {
    return new Response(
      JSON.stringify({
        query,
        hits: hits.map((h) => ({
          symbol_id: h.symbol_id,
          name: h.name,
          score: h.score,
          file_path: h.file_path,
          snippet: h.snippet,
        })),
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      },
    );
  });

  vi.stubGlobal('fetch', mockFetch);
  return mockFetch;
}

describe('GlobalSearch', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not fetch on blank input and debounces typing', async () => {
    vi.useFakeTimers();
    const mockFetch = mockSuccessfulSearch();
    mount();

    expect(mockFetch).not.toHaveBeenCalled();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(299);
    });
    expect(mockFetch).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/repos/1/search');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({
      q: 'resolve',
      mode: 'hybrid',
    });
  });

  it('renders search results with category badges and score', async () => {
    mockSuccessfulSearch();
    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    expect(await screen.findByText('resolve_calls')).toBeInTheDocument();
    expect(screen.getByText('GET /api/repos/{id}/search')).toBeInTheDocument();
    expect(screen.getByText('Architecture Overview')).toBeInTheDocument();

    expect(screen.getByText('SYMBOL')).toBeInTheDocument();
    expect(screen.getByText('ENDPOINT')).toBeInTheDocument();
    expect(screen.getByText('DOCUMENTATION')).toBeInTheDocument();
    expect(screen.getByText('SCORE: 0.950')).toBeInTheDocument();
  });

  it('filters results across tabs: All, Symbols, Documentation, Endpoints', async () => {
    mockSuccessfulSearch();
    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    await screen.findByText('resolve_calls');

    // Tab buttons with counts
    const allTab = screen.getByRole('tab', { name: /ALL \(3\)/i });
    const symbolsTab = screen.getByRole('tab', { name: /SYMBOLS \(1\)/i });
    const docsTab = screen.getByRole('tab', { name: /DOCUMENTATION \(1\)/i });
    const endpointsTab = screen.getByRole('tab', { name: /ENDPOINTS \(1\)/i });

    expect(allTab).toHaveAttribute('aria-selected', 'true');

    // Filter by Symbols
    fireEvent.click(symbolsTab);
    expect(screen.getByText('resolve_calls')).toBeInTheDocument();
    expect(screen.queryByText('GET /api/repos/{id}/search')).not.toBeInTheDocument();
    expect(screen.queryByText('Architecture Overview')).not.toBeInTheDocument();

    // Filter by Endpoints
    fireEvent.click(endpointsTab);
    expect(screen.queryByText('resolve_calls')).not.toBeInTheDocument();
    expect(screen.getByText('GET /api/repos/{id}/search')).toBeInTheDocument();
    expect(screen.queryByText('Architecture Overview')).not.toBeInTheDocument();

    // Filter by Documentation
    fireEvent.click(docsTab);
    expect(screen.queryByText('resolve_calls')).not.toBeInTheDocument();
    expect(screen.queryByText('GET /api/repos/{id}/search')).not.toBeInTheDocument();
    expect(screen.getByText('Architecture Overview')).toBeInTheDocument();

    // Return to All
    fireEvent.click(allTab);
    expect(screen.getByText('resolve_calls')).toBeInTheDocument();
    expect(screen.getByText('GET /api/repos/{id}/search')).toBeInTheDocument();
    expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
  });

  it('displays latency metrics in UI and fires onLatencyChange', async () => {
    const onLatencyChange = vi.fn();
    mockSuccessfulSearch();
    mount({ onLatencyChange });

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    await screen.findByText('resolve_calls');

    expect(screen.getByText(/SEARCH LATENCY:/)).toBeInTheDocument();
    expect(screen.getByText(/MODE: HYBRID/)).toBeInTheDocument();
    expect(screen.getByText(/TOTAL HITS: 3/)).toBeInTheDocument();

    await waitFor(() => {
      expect(onLatencyChange).toHaveBeenCalled();
      expect(typeof onLatencyChange.mock.calls[0][0]).toBe('number');
    });
  });

  it('switches search modes between hybrid, lexical, and vector', async () => {
    const mockFetch = mockSuccessfulSearch();
    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });
    await screen.findByText('resolve_calls');

    const modeSelect = screen.getByLabelText('Search Mode');
    fireEvent.change(modeSelect, { target: { value: 'vector' } });

    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(JSON.parse(lastCall[1].body)).toEqual({
        q: 'resolve',
        mode: 'vector',
      });
    });
  });

  it('triggers onSelectSymbol when clicking inspect button', async () => {
    const onSelectSymbol = vi.fn();
    mockSuccessfulSearch();
    mount({ onSelectSymbol });

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    await screen.findByText('resolve_calls');

    const inspectBtn = screen.getByRole('button', {
      name: /Inspect resolve_calls with ID 101/i,
    });
    fireEvent.click(inspectBtn);

    expect(onSelectSymbol).toHaveBeenCalledWith(101);
  });

  it('clears search input when clicking clear button', async () => {
    mockSuccessfulSearch();
    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    const clearBtn = await screen.findByRole('button', {
      name: 'Clear search query',
    });
    fireEvent.click(clearBtn);

    expect(input).toHaveValue('');
  });

  it('supports offline fixture preview mode without calling fetch', async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);

    mount({ offlinePreview: true });

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolver' } });

    // Should find fixture hits matching "resolver"
    expect(await screen.findByText('SymbolResolver.resolve_calls')).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.getByText('OFFLINE FIXTURE')).toBeInTheDocument();
  });

  it('shows error banner with retry option on API failure', async () => {
    const mockFetch = vi.fn().mockImplementation(async () => {
      return new Response(
        JSON.stringify({
          detail: 'Database connection failed',
        }),
        {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    });
    vi.stubGlobal('fetch', mockFetch);

    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'resolve' } });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Database connection failed',
    );
    expect(screen.getByRole('button', { name: 'Retry Search' })).toBeInTheDocument();
  });

  it('displays empty state when query returns no results', async () => {
    mockSuccessfulSearch([], 'nonexistent');
    mount();

    const input = screen.getByLabelText('Search Query');
    fireEvent.change(input, { target: { value: 'nonexistent' } });

    expect(
      await screen.findByText(/No all hits found for “nonexistent”\./i),
    ).toBeInTheDocument();
  });
});
