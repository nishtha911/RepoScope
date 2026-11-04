export type SearchMode = 'hybrid' | 'lexical' | 'vector';

export type SearchCategory = 'all' | 'symbols' | 'documentation' | 'endpoints';

export interface SearchHit {
  symbol_id: number;
  name: string;
  score: number;
  file_path: string;
  snippet: string;
  category: 'symbol' | 'documentation' | 'endpoint';
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  latency_ms: number;
}

interface RawSearchHit {
  symbol_id: number;
  name: string;
  score: number;
  file_path: string;
  snippet: string;
}

interface RawSearchResponse {
  query: string;
  hits: RawSearchHit[];
}

export class SearchApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = 'SearchApiError';
    this.status = status;
    this.code = code;
  }
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const positive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

const text = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

function isRawSearchHit(value: unknown): value is RawSearchHit {
  if (!record(value)) return false;
  return (
    positive(value.symbol_id) &&
    text(value.name) &&
    typeof value.score === 'number' &&
    Number.isFinite(value.score) &&
    text(value.file_path) &&
    typeof value.snippet === 'string'
  );
}

function isRawSearchResponse(value: unknown): value is RawSearchResponse {
  if (!record(value)) return false;
  return (
    text(value.query) &&
    Array.isArray(value.hits) &&
    value.hits.every(isRawSearchHit)
  );
}

export function classifySearchHit(
  hit: Pick<SearchHit, 'name' | 'file_path' | 'snippet'>,
): 'symbol' | 'documentation' | 'endpoint' {
  const path = hit.file_path.toLowerCase();
  const name = hit.name.toLowerCase();
  const snippet = hit.snippet.toLowerCase();

  // Endpoints detection: API route naming or HTTP route decorator patterns
  if (
    name.startsWith('get ') ||
    name.startsWith('post ') ||
    name.startsWith('put ') ||
    name.startsWith('delete ') ||
    name.startsWith('patch ') ||
    path.includes('api/') ||
    path.includes('routes/') ||
    snippet.includes('@router.') ||
    snippet.includes('@app.') ||
    snippet.includes('app.include_router')
  ) {
    return 'endpoint';
  }

  // Documentation detection: markdown files, rst files, docs directory
  if (
    path.endsWith('.md') ||
    path.endsWith('.rst') ||
    path.includes('docs/') ||
    path.includes('documentation/') ||
    snippet.startsWith('#') ||
    name.includes('doc')
  ) {
    return 'documentation';
  }

  // Default: code symbol (function, method, class)
  return 'symbol';
}

export interface SearchRepoOptions {
  repoId: number;
  query: string;
  mode?: SearchMode;
  signal?: AbortSignal;
  apiBase?: string;
}

export async function searchRepo({
  repoId,
  query,
  mode = 'hybrid',
  signal,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
}: SearchRepoOptions): Promise<SearchResponse> {
  if (!positive(repoId)) {
    throw new Error('Select a valid numeric repository ID.');
  }
  const trimmed = query.trim();
  if (trimmed.length === 0) {
    throw new Error('Search query must not be empty.');
  }
  if (trimmed.length > 2000) {
    throw new Error('Search query must be at most 2000 characters.');
  }
  if (mode !== 'hybrid' && mode !== 'lexical' && mode !== 'vector') {
    throw new Error("Mode must be 'hybrid', 'lexical', or 'vector'.");
  }

  const startTime = performance.now();
  const response = await fetch(
    `${apiBase.replace(/\/$/, '')}/repos/${repoId}/search`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ q: trimmed, mode }),
      signal,
    },
  );
  const elapsed = Math.max(1, Math.round(performance.now() - startTime));
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const error =
      record(body) && record(body.error) ? body.error : null;
    const detail =
      record(body) && text(body.detail) ? body.detail : null;
    const errorMessage =
      error && text(error.message) ? error.message : null;
    const message =
      errorMessage ??
      detail ??
      `Search failed (HTTP ${response.status}).`;
    throw new SearchApiError(
      message,
      response.status,
      error && text(error.code) ? error.code : 'HTTP_ERROR',
    );
  }

  if (!isRawSearchResponse(body)) {
    throw new SearchApiError(
      'The server returned an invalid search response.',
      response.status,
      'INVALID_RESPONSE',
    );
  }

  const enrichedHits: SearchHit[] = body.hits.map((hit) => ({
    ...hit,
    category: classifySearchHit(hit),
  }));

  return {
    query: body.query,
    hits: enrichedHits,
    latency_ms: elapsed,
  };
}
