import { describe, expect, it } from 'vitest';
import { citationPreviewPack } from '../fixtures/citations';
import { isEvidenceId, parseEvidencePack } from './evidence';
function copy() { return JSON.parse(JSON.stringify(citationPreviewPack)); }
describe('Evidence Pack runtime contract', () => {
  it('accepts the backend-compatible fixture without rewriting source', () => {
    const input = copy();
    expect(parseEvidencePack(input)).toBe(input);
    expect(input.entries[0].source.text.endsWith('\n')).toBe(true);
  });
  it.each(['E0', 'e1', 'E01', 'E-1', '[E1]', 'E1<script>'])('rejects invalid label %s', value => {
    expect(isEvidenceId(value)).toBe(false);
  });
  it('rejects a mismatched snapshot', () => {
    const input = copy(); input.entries[1].source.snapshot_id = 8;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it('rejects duplicate IDs instead of resolving the wrong source', () => {
    const input = copy(); input.entries[1].source.evidence_id = 'E1';
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it('rejects duplicate chunks', () => {
    const input = copy(); input.entries[1].source.chunk_id = input.entries[0].source.chunk_id;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it.each(['../secret.py', '/secret.py', 'C:/secret.py', 'a\\secret.py'])('rejects path %s', path => {
    const input = copy(); input.entries[0].source.file_path = path;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it('rejects inconsistent source line ranges', () => {
    const input = copy(); input.entries[0].source.end_line = 99;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it('rejects path terminal mismatch', () => {
    const input = copy(); input.entries[1].paths[0].symbol_ids[1] = 999;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it.each([-1, 1.1, NaN, Infinity])('rejects confidence %s', score => {
    const input = copy(); input.entries[1].paths[0].confidence = score;
    expect(() => parseEvidencePack(input)).toThrow();
  });
  it('retains zero confidence and an empty pack', () => {
    const input = copy(); input.entries[1].paths[0].confidence = 0;
    expect(parseEvidencePack(input).entries[1].paths[0].confidence).toBe(0);
    input.entries = [];
    expect(parseEvidencePack(input).entries).toEqual([]);
  });
});
