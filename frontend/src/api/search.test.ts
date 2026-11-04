import { describe, expect, it, vi } from 'vitest';
import {
  classifySearchHit,
  searchRepo,
} from './search';

const sampleHits = [
  {
    symbol_id: 101,
    name: 'SymbolResolver.resolve_calls',
    score: 0.092,
    file_path: 'backend/reposcope/parsing/resolver.py',
    snippet: 'def resolve_calls(self, ast_tree):',
  },
  {
    symbol_id: 301,
    name: 'POST /api/repos/{id}/search',
    score: 0.065,
    file_path: 'backend/reposcope/api/repos.py',
    snippet: '@router.post("/repos/{repo_id}/search")',
  },
  {
    symbol_id: 401,
    name: 'Architecture Overview',
    score: 0.049,
    file_path: 'docs/architecture.md',
    snippet: '# Architecture: Hybrid RRF Search',
  },
];

describe('classifySearchHit', () => {
  it('identifies API endpoints from name, path, or route decorators', () => {
    expect(
      classifySearchHit({
        name: 'POST /api/repos/{id}/search',
        file_path: 'backend/reposcope/api/repos.py',
        snippet: '@router.post("/repos/{id}/search")',
      }),
    ).toBe('endpoint');

    expect(
      classifySearchHit({
        name: 'get_symbols',
        file_path: 'backend/reposcope/api/symbols.py',
        snippet: 'def get_symbols():',
      }),
    ).toBe('endpoint');
  });

  it('identifies documentation from markdown extensions or docs paths', () => {
    expect(
      classifySearchHit({
        name: 'Architecture Guide',
        file_path: 'docs/architecture.md',
        snippet: '# Architecture Guide',
      }),
    ).toBe('documentation');
  });

  it('identifies code symbols by default', () => {
    expect(
      classifySearchHit({
        name: 'SymbolScanner.scan',
        file_path: 'backend/reposcope/ingestion/scanner.py',
        snippet: 'def scan(self, directory):',
      }),
    ).toBe('symbol');
  });
});

describe('searchRepo', () => {
  it('makes POST request to /api/repos/{id}/search and returns categorized hits with latency', async () => {
    const mock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: 'resolver',
          hits: sampleHits,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal('fetch', mock);

    const result = await searchRepo({
      repoId: 1,
      query: 'resolver',
      mode: 'hybrid',
    });

    expect(result.query).toBe('resolver');
    expect(result.hits).toHaveLength(3);
    expect(result.hits[0].category).toBe('symbol');
    expect(result.hits[1].category).toBe('endpoint');
    expect(result.hits[2].category).toBe('documentation');
    expect(result.latency_ms).toBeGreaterThanOrEqual(0);

    const [address, init] = mock.mock.calls[0];
    const url = new URL(address);
    expect(url.pathname).toBe('/api/repos/1/search');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      q: 'resolver',
      mode: 'hybrid',
    });
  });

  it('rejects empty query before fetching', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);

    await expect(searchRepo({ repoId: 1, query: '   ' })).rejects.toThrow(
      'Search query must not be empty.',
    );
    expect(mock).not.toHaveBeenCalled();
  });

  it('rejects invalid repo ID', async () => {
    const mock = vi.fn();
    vi.stubGlobal('fetch', mock);

    await expect(searchRepo({ repoId: 0, query: 'test' })).rejects.toThrow(
      'Select a valid numeric repository ID.',
    );
    expect(mock).not.toHaveBeenCalled();
  });

  it('preserves backend error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { message: 'Repository not found', code: 'NOT_FOUND' },
          }),
          { status: 404 },
        ),
      ),
    );

    await expect(searchRepo({ repoId: 999, query: 'test' })).rejects.toMatchObject(
      {
        message: 'Repository not found',
        code: 'NOT_FOUND',
        status: 404,
      },
    );
  });

  it('rejects invalid response shape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ invalid: true }), { status: 200 }),
      ),
    );

    await expect(searchRepo({ repoId: 1, query: 'test' })).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  });
});
