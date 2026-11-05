/** Matches the source-bearing portion of the backend Evidence Pack v1. */
export interface EvidencePath {
  seed_symbol_id: number;
  symbol_ids: number[];
  edge_ids: number[];
  edge_kinds: string[];
  directions: ('incoming' | 'outgoing')[];
  confidence: number;
}
export interface EvidenceEntry {
  source: {
    evidence_id: string;
    snapshot_id: number;
    file_id: number;
    file_path: string;
    symbol_id: number | null;
    chunk_id: number | null;
    start_line: number;
    end_line: number;
    text: string;
  };
  name: string;
  qualname: string | null;
  kind: string;
  signature: string | null;
  origin: 'seed' | 'expanded';
  fused_score: number | null;
  paths: EvidencePath[];
}
export interface EvidencePack {
  schema_version: 1;
  repository_id: number;
  snapshot_id: number;
  commit_sha: string | null;
  entries: EvidenceEntry[];
  context_symbols?: unknown[];
  gaps: string[];
  truncated: boolean;
  truncation_reasons: string[];
}
export interface CitationSelection {
  answerId: string;
  evidenceId: string;
  pack: EvidencePack;
}
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;
export const isEvidenceId = (v: string): boolean => /^E[1-9][0-9]*$/.test(v);

/** Validate the fields used by the drawer; never invent source or confidence. */
export function parseEvidencePack(value: unknown): EvidencePack {
  const bad = (): never => { throw new Error('Invalid or inconsistent Evidence Pack'); };
  if (!record(value)) return bad();
  if (value.schema_version !== 1 || !positive(value.repository_id) || !positive(value.snapshot_id)) return bad();
  if (value.commit_sha !== null && (typeof value.commit_sha !== 'string' || !/^[0-9a-fA-F]{40,64}$/.test(value.commit_sha))) return bad();
  if (!Array.isArray(value.entries) || value.entries.length > 1000 ||
      !Array.isArray(value.gaps) || !value.gaps.every(text) ||
      !Array.isArray(value.truncation_reasons) || !value.truncation_reasons.every(text) ||
      typeof value.truncated !== 'boolean' || value.truncated !== (value.truncation_reasons.length > 0)) return bad();
  const chunks = new Set<number>();
  for (const [index, entry] of value.entries.entries()) {
    if (!record(entry) || !record(entry.source)) return bad();
    const s = entry.source;
    if (s.evidence_id !== `E${index + 1}` || s.snapshot_id !== value.snapshot_id ||
        !positive(s.file_id) || !positive(s.symbol_id) || !positive(s.chunk_id) ||
        !positive(s.start_line) || !positive(s.end_line) || s.end_line < s.start_line ||
        !text(s.file_path) || !text(s.text) || chunks.has(s.chunk_id)) return bad();
    chunks.add(s.chunk_id);
    const parts = s.file_path.split('/');
    if (s.file_path.startsWith('/') || s.file_path.includes('\\') || s.file_path.includes('\0') ||
        parts.some(p => p === '' || p === '.' || p === '..') || parts[0].includes(':')) return bad();
    const normalized = s.text.replace(/\r\n?/g, '\n');
    const lineCount = normalized.split('\n').length - (normalized.endsWith('\n') ? 1 : 0);
    if (s.end_line - s.start_line + 1 !== lineCount) return bad();
    if (!text(entry.name) || !text(entry.kind) ||
        (entry.qualname !== null && !text(entry.qualname)) ||
        (entry.signature !== null && !text(entry.signature)) ||
        (entry.fused_score !== null && (typeof entry.fused_score !== 'number' || !Number.isFinite(entry.fused_score) || entry.fused_score < 0)) ||
        !Array.isArray(entry.paths) || !['seed', 'expanded'].includes(String(entry.origin))) return bad();
    if ((entry.origin === 'expanded') !== (entry.paths.length > 0)) return bad();
    for (const path of entry.paths) {
      if (!record(path) || !positive(path.seed_symbol_id) ||
          !Array.isArray(path.symbol_ids) || !path.symbol_ids.every(positive) ||
          !Array.isArray(path.edge_ids) || !path.edge_ids.every(positive) ||
          !Array.isArray(path.edge_kinds) || !path.edge_kinds.every(text) ||
          !Array.isArray(path.directions) || !path.directions.every(d => d === 'incoming' || d === 'outgoing') ||
          typeof path.confidence !== 'number' || !Number.isFinite(path.confidence) || path.confidence < 0 || path.confidence > 1) return bad();
      const count = path.edge_ids.length;
      if (count < 1 || count > 2 || path.symbol_ids.length !== count + 1 ||
          path.edge_kinds.length !== count || path.directions.length !== count ||
          path.symbol_ids[0] !== path.seed_symbol_id || path.symbol_ids[count] !== s.symbol_id ||
          new Set(path.symbol_ids).size !== path.symbol_ids.length) return bad();
    }
  }
  // Additional graph-only metadata is preserved but is not used as a citation.
  return value as unknown as EvidencePack;
}
