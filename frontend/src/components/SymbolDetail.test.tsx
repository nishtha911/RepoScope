import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SymbolDetail from './SymbolDetail';
import type {
  Neighbor,
  SymbolDetailResponse,
} from '../api/symbols';

const mockDetail: SymbolDetailResponse = {
  id: 101,
  file_id: 12,
  name: 'resolve_calls',
  qualname: 'SymbolResolver.resolve_calls',
  kind: 'method',
  file_path: 'backend/reposcope/parsing/resolver.py',
  start_line: 142,
  end_line: 180,
  signature: 'def resolve_calls(self, ast_tree) -> list[Edge]:',
  docstring: 'Resolves call expressions to candidate symbol IDs.',
  cyclomatic_complexity: 4,
};

const mockUpstream: Neighbor[] = [
  {
    symbol_id: 204,
    name: 'SymbolScanner.scan',
    relationship_type: 'CALLS',
    confidence: 1.0,
    direction: 'in',
  },
];

const mockDownstream: Neighbor[] = [
  {
    symbol_id: 305,
    name: 'ReferenceResolver.resolve',
    relationship_type: 'CALLS',
    confidence: 0.92,
    direction: 'out',
  },
];

function mount(
  props: {
    symbolId?: number;
    offlinePreview?: boolean;
    onSelectSymbol?: (id: number) => void;
    onBackToOverview?: () => void;
  } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <SymbolDetail
        symbolId={props.symbolId ?? 101}
        offlinePreview={props.offlinePreview ?? false}
        onSelectSymbol={props.onSelectSymbol}
        onBackToOverview={props.onBackToOverview}
      />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

function mockApiSuccess({
  detail = mockDetail,
  upstream = mockUpstream,
  downstream = mockDownstream,
}: {
  detail?: SymbolDetailResponse;
  upstream?: Neighbor[];
  downstream?: Neighbor[];
} = {}) {
  const mockFetch = vi.fn().mockImplementation(async (url: string) => {
    const parsed = new URL(url);
    if (parsed.pathname === `/api/symbols/${detail.id}`) {
      return new Response(JSON.stringify(detail), { status: 200 });
    }
    if (parsed.pathname === `/api/symbols/${detail.id}/neighbors`) {
      const dir = parsed.searchParams.get('dir');
      if (dir === 'in') {
        return new Response(JSON.stringify({ neighbors: upstream }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ neighbors: downstream }), {
        status: 200,
      });
    }
    return new Response(JSON.stringify({ error: { message: 'Not found', code: 'NOT_FOUND' } }), {
      status: 404,
    });
  });
  vi.stubGlobal('fetch', mockFetch);
  return mockFetch;
}

describe('SymbolDetail', () => {
  it('renders metadata panel with lines, complexity, and signature in live API mode', async () => {
    mockApiSuccess();
    mount({ symbolId: 101 });

    expect(
      await screen.findByText('SymbolResolver.resolve_calls'),
    ).toBeInTheDocument();
    expect(screen.getByText('L142–L180')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(
      screen.getByText('def resolve_calls(self, ast_tree) -> list[Edge]:'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Resolves call expressions to candidate symbol IDs.'),
    ).toBeInTheDocument();
  });

  it('renders 1-hop upstream and downstream callers list with confidence scores and relationship types', async () => {
    mockApiSuccess();
    mount({ symbolId: 101 });

    expect(await screen.findByText('SymbolScanner.scan')).toBeInTheDocument();
    expect(screen.getByText('ReferenceResolver.resolve')).toBeInTheDocument();

    // Check relationship badges
    const badges = screen.getAllByText('CALLS');
    expect(badges.length).toBeGreaterThanOrEqual(2);

    // Check confidence scores
    expect(screen.getByText(/100% \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/92% \(0.92\)/)).toBeInTheDocument();
  });

  it('filters between all, upstream callers, and downstream callees', async () => {
    mockApiSuccess();
    mount({ symbolId: 101 });

    expect(await screen.findByText('SymbolScanner.scan')).toBeInTheDocument();
    expect(screen.getByText('ReferenceResolver.resolve')).toBeInTheDocument();

    // Filter to UPSTREAM only
    fireEvent.click(screen.getByRole('tab', { name: /UPSTREAM CALLERS/ }));
    expect(screen.getByText('SymbolScanner.scan')).toBeInTheDocument();
    expect(
      screen.queryByText('ReferenceResolver.resolve'),
    ).not.toBeInTheDocument();

    // Filter to DOWNSTREAM only
    fireEvent.click(screen.getByRole('tab', { name: /DOWNSTREAM CALLEES/ }));
    expect(
      screen.queryByText('SymbolScanner.scan'),
    ).not.toBeInTheDocument();
    expect(screen.getByText('ReferenceResolver.resolve')).toBeInTheDocument();
  });

  it('triggers onSelectSymbol when clicking inspect button on a caller', async () => {
    mockApiSuccess();
    const onSelect = vi.fn();
    mount({ symbolId: 101, onSelectSymbol: onSelect });

    expect(await screen.findByText('SymbolScanner.scan')).toBeInTheDocument();
    const inspectBtn = screen.getByRole('button', {
      name: /Inspect symbol SymbolScanner\.scan with ID 204/,
    });
    fireEvent.click(inspectBtn);
    expect(onSelect).toHaveBeenCalledWith(204);
  });

  it('renders empty states when no upstream or downstream callers exist', async () => {
    mockApiSuccess({ upstream: [], downstream: [] });
    mount({ symbolId: 101 });

    expect(
      await screen.findByText(
        'No 1-hop upstream callers found in the code graph.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'No 1-hop downstream callees found in the code graph.',
      ),
    ).toBeInTheDocument();
  });

  it('renders error state and retries on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Network error loading symbol')),
    );
    mount({ symbolId: 101 });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Network error loading symbol',
    );

    // Provide successful mock and click retry
    mockApiSuccess();
    fireEvent.click(screen.getByRole('button', { name: /RETRY REQUEST/ }));
    expect(
      await screen.findByText('SymbolResolver.resolve_calls'),
    ).toBeInTheDocument();
  });

  it('renders correctly in offline preview mode without making HTTP requests', () => {
    const mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);

    mount({ symbolId: 101, offlinePreview: true });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(
      screen.getByText('SymbolResolver.resolve_calls'),
    ).toBeInTheDocument();
    expect(screen.getByText('OFFLINE FIXTURE')).toBeInTheDocument();
    expect(screen.getByText('L142–L180')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('SymbolScanner.scan')).toBeInTheDocument();
    expect(screen.getByText('ReferenceResolver.resolve')).toBeInTheDocument();
  });

  it('calls onBackToOverview when back button is clicked', async () => {
    mockApiSuccess();
    const onBack = vi.fn();
    mount({ symbolId: 101, onBackToOverview: onBack });

    const backBtn = await screen.findByRole('button', {
      name: /BACK TO OVERVIEW/,
    });
    fireEvent.click(backBtn);
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
