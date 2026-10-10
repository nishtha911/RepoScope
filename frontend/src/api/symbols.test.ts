import { describe, expect, it, vi } from 'vitest';
import { fetchSymbols } from './symbols';
const item = { id: 101, file_id: 12, name: 'resolve_calls', qualname: 'SymbolResolver.resolve_calls', kind: 'method', file_path: 'resolver.py', start_line: 142, end_line: 180 };
describe('fetchSymbols', () => {
  it('encodes parameters and forwards cancellation', async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ symbols: [item] }), { status: 200 }));
    vi.stubGlobal('fetch', mock);
    const controller = new AbortController();
    expect((await fetchSymbols({ repoId: 1, query: 'a&b', kind: 'method', signal: controller.signal })).symbols).toHaveLength(1);
    const [address, init] = mock.mock.calls[0];
    const url = new URL(address);
    expect(url.pathname).toBe('/api/repos/1/symbols');
    expect(url.searchParams.get('q')).toBe('a&b');
    expect(url.searchParams.get('kind')).toBe('method');
    expect(init.signal).toBe(controller.signal);
  });
  it('preserves the error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Invalid kind', code: 'VALIDATION_ERROR' } }), { status: 422 })));
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({ message: 'Invalid kind', code: 'VALIDATION_ERROR', status: 422 });
  });
  it('rejects the wrong response envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [item] }), { status: 200 })));
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('rejects reversed source ranges', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ symbols: [{ ...item, end_line: 1 }] }), { status: 200 })));
    await expect(fetchSymbols({ repoId: 1, query: 'x' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('rejects invalid repo IDs before fetching', async () => {
    const mock = vi.fn(); vi.stubGlobal('fetch', mock);
    await expect(fetchSymbols({ repoId: 0, query: 'x' })).rejects.toThrow('numeric repository ID');
    expect(mock).not.toHaveBeenCalled();
  });
});
