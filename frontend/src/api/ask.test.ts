import { afterEach, describe, expect, it, vi } from 'vitest';
import { askRepo, parseAskResponse } from './ask';

const source = {
  evidence_id: 'E2', snapshot_id: 9, file_id: 18, file_path: 'sample/core.py',
  symbol_id: 75, chunk_id: 75, start_line: 4, end_line: 6,
  text: 'def get_hmm():\n    """Get a thought."""\n    return \'hmmm...\'',
};
const response = () => ({ answer: "get_hmm returns 'hmmm...'. [E2]", evidence: [{ ...source }], gaps: ['Edge 12 has missing or invalid confidence'], timings: null });

afterEach(() => { vi.unstubAllGlobals(); });

describe('real AskResponse adapter', () => {
  it('maps API text to the citation snippet without renumbering E2', () => {
    const result = parseAskResponse(response());
    expect(Object.keys(result.citations)).toEqual(['E2']);
    expect(result.citations.E2.snippet).toBe(source.text);
    expect(result.citations.E2.snapshot_id).toBe(9);
    expect(result.citations.E2.symbol_id).toBe(75);
    expect(result.citations.E2.name).toBe('Symbol 75');
    expect(result.gaps).toEqual(response().gaps);
  });

  it('keeps insufficient-evidence responses empty, with no fixture fallback', () => {
    expect(parseAskResponse({ answer: 'Insufficient evidence.', evidence: [], gaps: ['No telemetry retrieved.'] }).citations).toEqual({});
  });

  it('rejects missing evidence even if legacy citations are present', () => {
    expect(() => parseAskResponse({ answer: 'claim [E2]', citations: { E2: source }, gaps: [] })).toThrow();
  });

  it('rejects a citation absent from the returned evidence', () => {
    expect(() => parseAskResponse({ ...response(), answer: 'claim [E999]' })).toThrow();
  });

  it('rejects duplicate IDs', () => {
    expect(() => parseAskResponse({ ...response(), evidence: [source, source] })).toThrow();
  });

  it('rejects mixed snapshots', () => {
    expect(() => parseAskResponse({ ...response(), evidence: [source, { ...source, evidence_id: 'E3', snapshot_id: 10 }] })).toThrow();
  });

  it.each(['../secret.py', '/absolute.py', 'C:/secret.py', 'sample\\core.py', 'sample//core.py'])('rejects invalid source path %s', (file_path) => {
    expect(() => parseAskResponse({ ...response(), evidence: [{ ...source, file_path }] })).toThrow();
  });

  it('rejects source text that does not match its line span', () => {
    expect(() => parseAskResponse({ ...response(), evidence: [{ ...source, end_line: 100 }] })).toThrow();
  });

  it('accepts a trailing source newline', () => {
    expect(parseAskResponse({ ...response(), evidence: [{ ...source, text: source.text + '\n' }] }).citations.E2.snippet).toBe(source.text + '\n');
  });

  it('does not invent symbol metadata when symbol_id is null', () => {
    const result = parseAskResponse({ ...response(), evidence: [{ ...source, symbol_id: null }] });
    expect(result.citations.E2.symbol_id).toBeUndefined();
    expect(result.citations.E2.name).toBe('sample/core.py');
  });
});

describe('live ask request', () => {
  it('uses same-origin API with no embedded Authorization header', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(response()), { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    await askRepo({ repoId: 33, question: ' What does get_hmm return? ' });
    expect(fetcher).toHaveBeenCalledWith('/api/repos/33/ask', expect.objectContaining({
      credentials: 'same-origin', cache: 'no-store', method: 'POST',
      body: JSON.stringify({ question: 'What does get_hmm return?' }),
      headers: { 'Content-Type': 'application/json' },
    }));
  });

  it('explains staging authentication failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })));
    await expect(askRepo({ repoId: 33, question: 'question' })).rejects.toMatchObject({ status: 401, code: 'UNAUTHORIZED' });
  });

  it('surfaces structured API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'HTTP_ERROR', message: 'Provider unavailable' } }), { status: 503 })));
    await expect(askRepo({ repoId: 33, question: 'question' })).rejects.toThrow('Provider unavailable');
  });

  it('rejects malformed successful responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>not JSON</html>', { status: 200 })));
    await expect(askRepo({ repoId: 33, question: 'question' })).rejects.toThrow('invalid answer');
  });

  it('rejects invalid inputs before HTTP', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    await expect(askRepo({ repoId: 0, question: 'question' })).rejects.toThrow();
    await expect(askRepo({ repoId: 33, question: ' ' })).rejects.toThrow();
    await expect(askRepo({ repoId: 33, question: 'x'.repeat(4097) })).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
