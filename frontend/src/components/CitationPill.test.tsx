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
  });
});
