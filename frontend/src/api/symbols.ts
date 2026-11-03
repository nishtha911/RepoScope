export type SymbolKind =
  | 'module'
  | 'class'
  | 'function'
  | 'method'
  | 'parameter'
  | 'variable'
  | 'endpoint';

export type EdgeKind =
  | 'CALLS'
  | 'IMPORTS'
  | 'INHERITS'
  | 'EXPOSES'
  | 'USES'
  | 'TESTED_BY';

export type Direction = 'in' | 'out';

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

export interface SymbolDetailResponse extends SymbolListItem {
  signature: string | null;
  docstring: string | null;
  cyclomatic_complexity: number | null;
}

export interface SymbolListResponse {
  symbols: SymbolListItem[];
}

export interface Neighbor {
  symbol_id: number;
  name: string;
  relationship_type: EdgeKind;
  confidence: number | null;
  direction: Direction;
}

export interface NeighborsResponse {
  neighbors: Neighbor[];
}

const kinds = new Set<string>([
  'module',
  'class',
  'function',
  'method',
  'parameter',
  'variable',
  'endpoint',
]);

const edgeKinds = new Set<string>([
  'CALLS',
  'IMPORTS',
  'INHERITS',
  'EXPOSES',
  'USES',
  'TESTED_BY',
]);

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const positive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

const text = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

function isSymbol(value: unknown): value is SymbolListItem {
  return (
    record(value) &&
    positive(value.id) &&
    positive(value.file_id) &&
    text(value.name) &&
    text(value.qualname) &&
    text(value.file_path) &&
    typeof value.kind === 'string' &&
    kinds.has(value.kind) &&
    positive(value.start_line) &&
    positive(value.end_line) &&
    value.end_line >= value.start_line
  );
}

function isSymbolDetail(value: unknown): value is SymbolDetailResponse {
  if (!isSymbol(value)) return false;
  const s = value as unknown as Record<string, unknown>;
  const validSignature =
    s.signature === null || typeof s.signature === 'string';
  const validDocstring =
    s.docstring === null || typeof s.docstring === 'string';
  const validComplexity =
    s.cyclomatic_complexity === null ||
    (typeof s.cyclomatic_complexity === 'number' &&
      Number.isSafeInteger(s.cyclomatic_complexity) &&
      s.cyclomatic_complexity >= 1);
  return validSignature && validDocstring && validComplexity;
}

function isNeighbor(value: unknown): value is Neighbor {
  if (!record(value)) return false;
  if (!positive(value.symbol_id)) return false;
  if (!text(value.name)) return false;
  if (
    typeof value.relationship_type !== 'string' ||
    !edgeKinds.has(value.relationship_type)
  ) {
    return false;
  }
  const validConfidence =
    value.confidence === null ||
    (typeof value.confidence === 'number' &&
      Number.isFinite(value.confidence) &&
      value.confidence >= 0 &&
      value.confidence <= 1);
  const validDirection = value.direction === 'in' || value.direction === 'out';
  return validConfidence && validDirection;
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

export async function fetchSymbols({
  repoId,
  query,
  kind = '',
  limit = 20,
  signal,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
}: FetchSymbolsOptions): Promise<SymbolListResponse> {
  if (!positive(repoId)) {
    throw new Error('Select a valid numeric repository ID.');
  }
  if (query.trim().length > 2000) {
    throw new Error('Search must be at most 2000 characters.');
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error('Limit must be between 1 and 100.');
  }
  if (kind && !kinds.has(kind)) throw new Error('Unsupported symbol kind.');
  const params = new URLSearchParams({ q: query.trim(), limit: String(limit) });
  if (kind) params.set('kind', kind);
  const response = await fetch(
    `${apiBase.replace(/\/$/, '')}/repos/${repoId}/symbols?${params}`,
    { signal },
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = record(body) && record(body.error) ? body.error : null;
    throw new SymbolsApiError(
      error && text(error.message)
        ? error.message
        : `Symbol search failed (HTTP ${response.status}).`,
      response.status,
      error && text(error.code) ? error.code : 'HTTP_ERROR',
    );
  }
  if (
    !record(body) ||
    !Array.isArray(body.symbols) ||
    !body.symbols.every(isSymbol)
  ) {
    throw new SymbolsApiError(
      'The server returned an invalid symbols response.',
      response.status,
      'INVALID_RESPONSE',
    );
  }
  return { symbols: body.symbols };
}

export interface FetchSymbolDetailOptions {
  symbolId: number;
  signal?: AbortSignal;
  apiBase?: string;
}

export async function fetchSymbolDetail({
  symbolId,
  signal,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
}: FetchSymbolDetailOptions): Promise<SymbolDetailResponse> {
  if (!positive(symbolId)) {
    throw new Error('Select a valid numeric symbol ID.');
  }
  const response = await fetch(
    `${apiBase.replace(/\/$/, '')}/symbols/${symbolId}`,
    { signal },
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = record(body) && record(body.error) ? body.error : null;
    throw new SymbolsApiError(
      error && text(error.message)
        ? error.message
        : `Symbol detail failed (HTTP ${response.status}).`,
      response.status,
      error && text(error.code) ? error.code : 'HTTP_ERROR',
    );
  }
  if (!isSymbolDetail(body)) {
    throw new SymbolsApiError(
      'The server returned an invalid symbol detail response.',
      response.status,
      'INVALID_RESPONSE',
    );
  }
  return body;
}

export interface FetchSymbolNeighborsOptions {
  symbolId: number;
  direction?: Direction;
  types?: string;
  signal?: AbortSignal;
  apiBase?: string;
}

export async function fetchSymbolNeighbors({
  symbolId,
  direction = 'out',
  types = '',
  signal,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
}: FetchSymbolNeighborsOptions): Promise<NeighborsResponse> {
  if (!positive(symbolId)) {
    throw new Error('Select a valid numeric symbol ID.');
  }
  if (direction !== 'in' && direction !== 'out') {
    throw new Error("Direction must be 'in' or 'out'.");
  }
  if (types) {
    const parts = types.split(',').map((part) => part.trim());
    if (parts.some((part) => !edgeKinds.has(part))) {
      throw new Error('Unsupported edge kind in types filter.');
    }
  }
  const params = new URLSearchParams({ dir: direction });
  if (types.trim()) {
    params.set('types', types.trim());
  }
  const response = await fetch(
    `${apiBase.replace(/\/$/, '')}/symbols/${symbolId}/neighbors?${params}`,
    { signal },
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = record(body) && record(body.error) ? body.error : null;
    throw new SymbolsApiError(
      error && text(error.message)
        ? error.message
        : `Symbol neighbors failed (HTTP ${response.status}).`,
      response.status,
      error && text(error.code) ? error.code : 'HTTP_ERROR',
    );
  }
  if (
    !record(body) ||
    !Array.isArray(body.neighbors) ||
    !body.neighbors.every(isNeighbor)
  ) {
    throw new SymbolsApiError(
      'The server returned an invalid symbol neighbors response.',
      response.status,
      'INVALID_RESPONSE',
    );
  }
  return { neighbors: body.neighbors };
}
