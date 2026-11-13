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

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  citations?: Record<string, CitationEvidence>;
  error?: string;
  latencyMs?: number;
}
