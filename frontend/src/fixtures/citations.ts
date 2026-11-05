import type { EvidencePack } from '../types/evidence';
/** Synthetic data only; never substituted for a live answer's missing evidence. */
export const citationPreviewPack: EvidencePack = {
  schema_version: 1, repository_id: 1, snapshot_id: 7, commit_sha: 'a'.repeat(40),
  entries: [
    {
      source: { evidence_id: 'E1', snapshot_id: 7, file_id: 11, file_path: 'demo/api/users.py',
        symbol_id: 101, chunk_id: 501, start_line: 12, end_line: 13,
        text: 'def create_user(payload):\n    return user_service.create(payload)\n' },
      name: 'create_user', qualname: 'create_user', kind: 'function',
      signature: 'def create_user(payload):', origin: 'seed', fused_score: 0.0327, paths: [],
    },
    {
      source: { evidence_id: 'E2', snapshot_id: 7, file_id: 12, file_path: 'demo/services/users.py',
        symbol_id: 202, chunk_id: 502, start_line: 30, end_line: 32,
        text: 'def create(self, payload):\n    user = User(payload.name)\n    return user\n' },
      name: 'create', qualname: 'UserService.create', kind: 'method',
      signature: 'def create(self, payload):', origin: 'expanded', fused_score: null,
      paths: [{ seed_symbol_id: 101, symbol_ids: [101, 202], edge_ids: [88],
        edge_kinds: ['CALLS'], directions: ['outgoing'], confidence: 0.9 }],
    },
  ],
  context_symbols: [], gaps: ['Synthetic preview: no live retrieval or generated answer was used.'],
  truncated: false, truncation_reasons: [],
};
