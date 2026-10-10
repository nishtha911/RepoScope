export type SymbolKind = 'module' | 'class' | 'function' | 'method' | 'parameter' | 'variable' | 'endpoint';
export interface SymbolListItem {
  id: number;
  file_id: number;
  name: string;
  qualname: string;
  kind: SymbolKind;
  file_path: string;
  start_line: number;
  end_line: number;
}
export interface SymbolListResponse { symbols: SymbolListItem[] }
const kinds = new Set<string>(['module', 'class', 'function', 'method', 'parameter', 'variable', 'endpoint']);
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const positive = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
function isSymbol(value: unknown): value is SymbolListItem {
  return record(value) && positive(value.id) && positive(value.file_id)
    && text(value.name) && text(value.qualname) && text(value.file_path)
    && typeof value.kind === 'string' && kinds.has(value.kind)
    && positive(value.start_line) && positive(value.end_line) && value.end_line >= value.start_line;
}
export class SymbolsApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = 'SymbolsApiError';
    this.status = status;
    this.code = code;
  }
}
export interface FetchSymbolsOptions {
  repoId: number;
  query: string;
  kind?: SymbolKind | '';
  limit?: number;
  signal?: AbortSignal;
  apiBase?: string;
}
export async function fetchSymbols({ repoId, query, kind = '', limit = 20, signal,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
}: FetchSymbolsOptions): Promise<SymbolListResponse> {
  if (!positive(repoId)) throw new Error('Select a valid numeric repository ID.');
  if (query.trim().length > 2000) throw new Error('Search must be at most 2000 characters.');
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new Error('Limit must be between 1 and 100.');
  if (kind && !kinds.has(kind)) throw new Error('Unsupported symbol kind.');
  const params = new URLSearchParams({ q: query.trim(), limit: String(limit) });
  if (kind) params.set('kind', kind);
  const response = await fetch(`${apiBase.replace(/\/$/, '')}/repos/${repoId}/symbols?${params}`, { signal });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = record(body) && record(body.error) ? body.error : null;
    throw new SymbolsApiError(error && text(error.message) ? error.message : `Symbol search failed (HTTP ${response.status}).`,
      response.status, error && text(error.code) ? error.code : 'HTTP_ERROR');
  }
  if (!record(body) || !Array.isArray(body.symbols) || !body.symbols.every(isSymbol)) {
    throw new SymbolsApiError('The server returned an invalid symbols response.', response.status, 'INVALID_RESPONSE');
  }
  return { symbols: body.symbols };
}
