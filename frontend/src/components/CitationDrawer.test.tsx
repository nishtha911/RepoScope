// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CitationDrawer from './CitationDrawer';
import { citationPreviewPack } from '../fixtures/citations';
import { mockNativeDialog } from '../test/citationDialog';
let restore: () => void;
beforeEach(() => { restore = mockNativeDialog(); });
afterEach(() => { cleanup(); restore(); vi.restoreAllMocks(); });
function copy() { return structuredClone(citationPreviewPack); }
function select(evidenceId = 'E2', pack = copy()) { return { answerId: 'answer-1', evidenceId, pack }; }
describe('CitationDrawer', () => {
  it('shows the exact file, cited range, relationship and path confidence', () => {
    render(<CitationDrawer selection={select()} onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Citation [E2]' })).toBeTruthy();
    expect(screen.getByText('demo/services/users.py')).toBeTruthy();
    expect(screen.getByText('30–32 (inclusive)')).toBeTruthy();
    expect(screen.getByText('Path 1: CALLS')).toBeTruthy();
    expect(screen.getByText('Path confidence: 0.9 (90%)')).toBeTruthy();
    expect(document.querySelector('[data-line-number="30"]')?.getAttribute('data-highlighted')).toBe('true');
    expect(document.querySelector('[data-line-number="33"]')).toBeNull();
  });
  it('does not invent confidence for direct retrieval seeds', () => {
    render(<CitationDrawer selection={select('E1')} onClose={() => {}} />);
    expect(screen.getByText(/no graph relationship path/)).toBeTruthy();
    expect(screen.queryByText(/Path confidence: 1/)).toBeNull();
    expect(screen.getByText(/0.0327 \(not a confidence percentage\)/)).toBeTruthy();
  });
  it('shows unknown IDs without falling back to E1', () => {
    render(<CitationDrawer selection={select('E999')} onClose={() => {}} />);
    expect(screen.getByRole('alert').textContent).toContain('not present');
    expect(screen.queryByRole('region', { name: 'Code preview' })).toBeNull();
  });
  it('blocks invalid packs', () => {
    const pack = copy(); pack.entries[0].source.snapshot_id = 999;
    render(<CitationDrawer selection={select('E1', pack)} onClose={() => {}} />);
    expect(screen.getByRole('alert').textContent).toContain('invalid');
  });
  it('displays every path, incoming traversal and zero confidence', () => {
    const pack = copy();
    pack.entries[1].paths.push({ seed_symbol_id: 9, symbol_ids: [9, 10, 202],
      edge_ids: [90, 91], edge_kinds: ['CALLS', 'USES'], directions: ['incoming', 'outgoing'], confidence: 0 });
    render(<CitationDrawer selection={select('E2', pack)} onClose={() => {}} />);
    expect(screen.getByText('Path 2: CALLS → USES')).toBeTruthy();
    expect(screen.getByText('Path confidence: 0 (0%)')).toBeTruthy();
    expect(screen.getByText(/incoming traversal · stored edge #90/)).toBeTruthy();
  });
  it('focuses close and handles Escape through native cancel', () => {
    const close = vi.fn();
    render(<CitationDrawer selection={select()} onClose={close} />);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close citation drawer' }));
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
    expect(close).toHaveBeenCalledOnce();
  });
  it('closes on the close button and backdrop, not panel content', () => {
    const close = vi.fn();
    render(<CitationDrawer selection={select()} onClose={close} />);
    fireEvent.click(screen.getByText('Stored signature'));
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Close citation drawer' }));
    fireEvent.click(screen.getByRole('dialog'));
    expect(close).toHaveBeenCalledTimes(2);
  });
  it('renders source as text, never HTML', () => {
    const pack = copy(); pack.entries[0].source.text = 'def create_user(payload):\n    return "<img src=x onerror=alert(1)>"\n';
    render(<CitationDrawer selection={select('E1', pack)} onClose={() => {}} />);
    expect(screen.getByRole('region', { name: 'Code preview' }).textContent).toContain('<img src=x onerror=alert(1)>');
    expect(screen.getByRole('dialog').querySelector('img')).toBeNull();
  });
  it('restores focus when closed', () => {
    const opener = document.createElement('button'); document.body.append(opener); opener.focus();
    const view = render(<CitationDrawer selection={select()} onClose={() => {}} />);
    view.rerender(<CitationDrawer selection={null} onClose={() => {}} />);
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
