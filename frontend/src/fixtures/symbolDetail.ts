// Synthetic demonstration fixtures for symbol detail and neighborhood traversal.
// Used in offline preview mode and unit tests.

import type { SymbolDetailResponse, Neighbor } from '../api/symbols';

export const fixtureSymbolDetail: SymbolDetailResponse = {
  id: 101,
  file_id: 12,
  name: 'resolve_calls',
  qualname: 'SymbolResolver.resolve_calls',
  kind: 'method',
  file_path: 'backend/reposcope/parsing/resolver.py',
  start_line: 142,
  end_line: 180,
  signature: 'def resolve_calls(self, ast_tree) -> list[Edge]:',
  docstring: 'Resolves call expressions to candidate symbol IDs.',
  cyclomatic_complexity: 4,
};

export const fixtureUpstreamNeighbors: Neighbor[] = [
  {
    symbol_id: 204,
    name: 'SymbolScanner.scan',
    relationship_type: 'CALLS',
    confidence: 1.0,
    direction: 'in',
  },
];

export const fixtureDownstreamNeighbors: Neighbor[] = [
  {
    symbol_id: 305,
    name: 'ReferenceResolver.resolve',
    relationship_type: 'CALLS',
    confidence: 0.92,
    direction: 'out',
  },
];

