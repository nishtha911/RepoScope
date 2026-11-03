import { describe, expect, it, vi } from 'vitest';
import {
  fetchSymbolDetail,
  fetchSymbolNeighbors,
  fetchSymbols,
} from './symbols';
import type { Neighbor, SymbolDetailResponse, SymbolListItem } from './symbols';

const item: SymbolListItem = {
  id: 101,
  file_id: 12,
  name: 'resolve_calls',
  qualname: 'SymbolResolver.resolve_calls',
  kind: 'method',
  file_path: 'resolver.py',
  start_line: 142,
  end_line: 180,
};

const detailItem: SymbolDetailResponse = {
  ...item,
  signature: 'def resolve_calls(self, ast_tree) -> list[Edge]:',
  docstring: 'Resolves call expressions to candidate symbol IDs.',
  cyclomatic_complexity: 4,
};

const neighborItem: Neighbor = {
  symbol_id: 204,
  name: 'SymbolScanner.scan',
  relationship_type: 'CALLS',
  confidence: 1.0,
  direction: 'in',
};

describe('fetchSymbols', () => {
  it('encodes parameters and forwards cancellation', async () => {
    const mock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ symbols: [item] }), { status: 200 }),
      );
    vi.stubGlobal('fetch', mock);
    const controller = new AbortController();
    expect(
      (
        await fetchSymbols({
          repoId: 1,
          query: 'a&b',
          kind: 'method',
          signal: controller.signal,
        })
      ).symbols,
    ).toHaveLength(1);
    const [address, init] = mock.mock.calls[0];
    const url = new URL(address);
    expect(url.pathname).toBe('/api/repos/1/symbols');
    expect(url.searchParams.get('q')).toBe('a&b');
    expect(url.searchParams.get('kind')).toBe('method');
    expect(init.signal).toBe(controller.signal);
  });

  it('preserves the error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { message: 'Invalid kind', code: 'VALIDATION_ERROR' },
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({
      message: 'Invalid kind',
      code: 'VALIDATION_ERROR',
      status: 422,
    });
  });

  it('rejects the wrong response envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: [item] }), { status: 200 }),
      ),
    );
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  });

  it('rejects reversed source ranges', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ symbols: [{ ...item, end_line: 1 }] }),
          { status: 200 },
        ),
      ),
    );
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  });

  it('rejects invalid repo IDs before fetching', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);
    await expect(fetchSymbols({ repoId: 0, query: 'x' })).rejects.toThrow(
      'numeric repository ID',
    );
    expect(mock).not.toHaveBeenCalled();
  });
});

describe('fetchSymbolDetail', () => {
  it('fetches symbol detail by ID with signature and complexity', async () => {
    const mock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(detailItem), { status: 200 }),
      );
    vi.stubGlobal('fetch', mock);
    const detail = await fetchSymbolDetail({ symbolId: 101 });
    expect(detail.id).toBe(101);
    expect(detail.signature).toBe(
      'def resolve_calls(self, ast_tree) -> list[Edge]:',
    );
    expect(detail.cyclomatic_complexity).toBe(4);
    const [address] = mock.mock.calls[0];
    const url = new URL(address);
    expect(url.pathname).toBe('/api/symbols/101');
  });

  it('rejects invalid symbol ID', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);
    await expect(fetchSymbolDetail({ symbolId: -1 })).rejects.toThrow(
      'numeric symbol ID',
    );
    expect(mock).not.toHaveBeenCalled();
  });

  it('handles backend error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { message: 'Symbol not found', code: 'NOT_FOUND' },
          }),
          { status: 404 },
        ),
      ),
    );
    await expect(fetchSymbolDetail({ symbolId: 999 })).rejects.toMatchObject({
      message: 'Symbol not found',
      code: 'NOT_FOUND',
      status: 404,
    });
  });

  it('rejects response missing required metadata', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ id: 101, name: 'missing_fields' }),
          { status: 200 },
        ),
      ),
    );
    await expect(fetchSymbolDetail({ symbolId: 101 })).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  });
});

describe('fetchSymbolNeighbors', () => {
  it('fetches callers with direction and types query params', async () => {
    const mock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ neighbors: [neighborItem] }),
          { status: 200 },
        ),
      );
    vi.stubGlobal('fetch', mock);
    const res = await fetchSymbolNeighbors({
      symbolId: 101,
      direction: 'in',
      types: 'CALLS',
    });
    expect(res.neighbors).toHaveLength(1);
    expect(res.neighbors[0].name).toBe('SymbolScanner.scan');
    expect(res.neighbors[0].direction).toBe('in');
    const [address] = mock.mock.calls[0];
    const url = new URL(address);
    expect(url.pathname).toBe('/api/symbols/101/neighbors');
    expect(url.searchParams.get('dir')).toBe('in');
    expect(url.searchParams.get('types')).toBe('CALLS');
  });

  it('rejects invalid direction', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);
    await expect(
      fetchSymbolNeighbors({
        symbolId: 101,
        direction: 'invalid' as unknown as 'in',
      }),
    ).rejects.toThrow("Direction must be 'in' or 'out'");
    expect(mock).not.toHaveBeenCalled();
  });

  it('rejects unsupported edge types', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);
    await expect(
      fetchSymbolNeighbors({ symbolId: 101, types: 'UNKNOWN_TYPE' }),
    ).rejects.toThrow('Unsupported edge kind');
    expect(mock).not.toHaveBeenCalled();
  });

  it('handles backend error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              message: 'types must be comma-separated allowed edge kinds',
              code: 'VALIDATION_ERROR',
            },
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(
      fetchSymbolNeighbors({ symbolId: 101, types: 'CALLS' }),
    ).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      status: 422,
    });
  });
});
