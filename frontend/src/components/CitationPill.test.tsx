// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CitationPill from './CitationPill';
afterEach(cleanup);
describe('CitationPill', () => {
  it('uses a real button and passes the exact evidence ID', () => {
    const select = vi.fn();
    render(<CitationPill evidenceId="E2" onSelect={select} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open citation E2' }));
    expect(select).toHaveBeenCalledWith('E2');
  });
  it('disables invalid IDs', () => {
    const select = vi.fn();
    render(<CitationPill evidenceId="E0" onSelect={select} />);
    const button = screen.getByRole('button', { name: 'Open citation E0' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(select).not.toHaveBeenCalled();
  });
  it('exposes dialog state for assistive technology', () => {
    render(<CitationPill evidenceId="E1" onSelect={() => {}} expanded controls="drawer-1" />);
    const button = screen.getByRole('button');
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(button.getAttribute('aria-controls')).toBe('drawer-1');
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CitationPill from './CitationPill';
import type { CitationEvidence } from '../types/chat';

const mockEvidence: CitationEvidence = {
  evidence_id: 'E1',
  symbol_id: 101,
  name: 'SymbolResolver.resolve_calls',
  file_path: 'backend/reposcope/parsing/resolver.py',
  start_line: 45,
  end_line: 68,
  snippet: 'def resolve_calls(self, ast_tree): return []',
  kind: 'function',
  signature: 'def resolve_calls(self, ast_tree: ast.AST):',
  fused_score: 0.092,
};

describe('CitationPill', () => {
  it('renders citation badge with [E1] text', () => {
    render(<CitationPill evidenceId="E1" evidence={mockEvidence} />);
    const button = screen.getByRole('button', { name: /Citation \[E1\]/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('[E1]');
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands popover details on click and shows file path and snippet', () => {
    render(<CitationPill evidenceId="E1" evidence={mockEvidence} />);
    const pill = screen.getByRole('button', { name: /Citation \[E1\]/i });

    // Expand
    fireEvent.click(pill);
    expect(pill).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('SymbolResolver.resolve_calls')).toBeInTheDocument();
    expect(screen.getByText('backend/reposcope/parsing/resolver.py:45-68')).toBeInTheDocument();
    expect(screen.getByText('SCORE: 0.092')).toBeInTheDocument();
    expect(screen.getByText(/def resolve_calls/i)).toBeInTheDocument();

    // Close with close button
    const closeBtn = screen.getByRole('button', { name: /Close citation details/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByText('SymbolResolver.resolve_calls')).not.toBeInTheDocument();
  });

  it('triggers onSelectSymbol when clicking inspect button', () => {
    const onSelectSymbol = vi.fn();
    render(
      <CitationPill
        evidenceId="E1"
        evidence={mockEvidence}
        onSelectSymbol={onSelectSymbol}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Citation \[E1\]/i }));
    const inspectBtn = screen.getByRole('button', { name: /INSPECT SYMBOL/i });
    fireEvent.click(inspectBtn);

    expect(onSelectSymbol).toHaveBeenCalledWith(101);
  });

  it('copies path to clipboard when clicking copy path', () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    render(<CitationPill evidenceId="E1" evidence={mockEvidence} />);
    fireEvent.click(screen.getByRole('button', { name: /Citation \[E1\]/i }));

    const copyBtn = screen.getByRole('button', { name: /COPY PATH/i });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith('backend/reposcope/parsing/resolver.py:45-68');
  });

  it('closes popover on Escape key', () => {
    render(<CitationPill evidenceId="E1" evidence={mockEvidence} />);
    const pill = screen.getByRole('button', { name: /Citation \[E1\]/i });
    fireEvent.click(pill);

    expect(screen.getByText('SymbolResolver.resolve_calls')).toBeInTheDocument();
    fireEvent.keyDown(pill, { key: 'Escape' });
    expect(screen.queryByText('SymbolResolver.resolve_calls')).not.toBeInTheDocument();
  });
});
