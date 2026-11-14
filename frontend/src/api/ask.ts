import type { CitationEvidence } from '../types/chat';

interface SourceRecord {
  evidence_id: string;
  snapshot_id: number;
  file_id: number;
  file_path: string;
  start_line: number;
  end_line: number;
  text: string;
  symbol_id?: number | null;
  chunk_id?: number | null;
}

export interface LiveCitation extends CitationEvidence {
  snapshot_id: number;
  file_id: number;
  chunk_id?: number;
}

export interface ParsedAskResponse {
  answer: string;
  citations: Record<string, LiveCitation>;
  gaps: string[];
}

export class AskApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(message: string, status = 0, code = 'INVALID_RESPONSE') {
    super(message);
    this.name = 'AskApiError';
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

function isSource(value: unknown): value is SourceRecord {
  if (!record(value) || !text(value.evidence_id) || !/^E[1-9]\d*$/.test(value.evidence_id)) return false;
  if (!positive(value.snapshot_id) || !positive(value.file_id) || !text(value.file_path)) return false;
  const parts = value.file_path.split('/');
  if (value.file_path.includes('\\') || value.file_path.includes('\0') || parts.some((p) => !p || p === '.' || p === '..') || parts[0].includes(':')) return false;
  if (!positive(value.start_line) || !positive(value.end_line) || value.end_line < value.start_line || !text(value.text)) return false;
  if (value.symbol_id != null && !positive(value.symbol_id)) return false;
  if (value.chunk_id != null && !positive(value.chunk_id)) return false;
  const lineCount = value.text.split('\n').length - (value.text.endsWith('\n') ? 1 : 0);
  return lineCount === value.end_line - value.start_line + 1;
}

export function parseAskResponse(value: unknown): ParsedAskResponse {
  if (!record(value) || !text(value.answer) || !Array.isArray(value.evidence) || !value.evidence.every(isSource)
      || !Array.isArray(value.gaps) || !value.gaps.every(text)) {
    throw new AskApiError('The server returned an invalid answer or source record.');
  }
  const citations: Record<string, LiveCitation> = {};
  let snapshot: number | undefined;
  for (const source of value.evidence) {
    if (Object.hasOwn(citations, source.evidence_id)) throw new AskApiError('Duplicate evidence ID in server response.');
    if (snapshot !== undefined && snapshot !== source.snapshot_id) throw new AskApiError('Mixed snapshots in server response.');
    snapshot = source.snapshot_id;
    citations[source.evidence_id] = {
      evidence_id: source.evidence_id,
      // The API does not supply symbol names or kinds. These are neutral UI
      // labels, not inferred repository metadata.
      name: source.symbol_id ? `Symbol ${source.symbol_id}` : source.file_path,
      kind: 'source',
      file_path: source.file_path,
      start_line: source.start_line,
      end_line: source.end_line,
      snippet: source.text,
      snapshot_id: source.snapshot_id,
      file_id: source.file_id,
      ...(source.symbol_id != null ? { symbol_id: source.symbol_id } : {}),
      ...(source.chunk_id != null ? { chunk_id: source.chunk_id } : {}),
    };
  }
  for (const match of value.answer.matchAll(/\[(E\d+)\]/g)) {
    if (!Object.hasOwn(citations, match[1])) throw new AskApiError('The answer references missing source evidence.');
  }
  return { answer: value.answer, citations, gaps: value.gaps };
}

interface AskOptions {
  repoId: number;
  question: string;
  apiBase?: string;
  signal?: AbortSignal;
}

export async function askRepo({ repoId, question, apiBase = '/api', signal }: AskOptions): Promise<ParsedAskResponse> {
  if (!positive(repoId)) throw new AskApiError('Select a valid repository ID.', 0, 'INVALID_INPUT');
  const trimmed = question.trim();
  if (!trimmed || trimmed.length > 4096) throw new AskApiError('Question must contain 1..4096 characters.', 0, 'INVALID_INPUT');
  const response = await fetch(`${apiBase.replace(/\/+$/, '')}/repos/${repoId}/ask`, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: trimmed }),
    signal,
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) throw new AskApiError(
      'Staging sign-in is required. Use the sign-in link above, then return and retry.', 401, 'UNAUTHORIZED');
    const error = record(body) && record(body.error) ? body.error : null;
    throw new AskApiError(error && text(error.message) ? error.message : `Answer request failed (HTTP ${response.status}).`,
      response.status, error && text(error.code) ? error.code : 'HTTP_ERROR');
  }
  return parseAskResponse(body);
}
