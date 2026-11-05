export interface CitationEvidence {
  evidence_id: string; // e.g. "E1", "E2"
  symbol_id?: number;
  name: string;
  file_path: string;
  start_line: number;
  end_line: number;
  snippet: string;
  kind: string; // e.g. "function", "class", "endpoint", "module"
  signature?: string | null;
  origin?: 'seed' | 'expanded';
  fused_score?: number | null;
}

/** Per-stage latency breakdown returned by POST /api/repos/{id}/ask */
export interface AskTimings {
  retrieval_ms: number;
  expansion_ms: number;
  synthesis_ms: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  citations?: Record<string, CitationEvidence>;
  error?: string;
  latencyMs?: number;
  /** Per-stage breakdown received from the API (online mode only) */
  timings?: AskTimings;
}
