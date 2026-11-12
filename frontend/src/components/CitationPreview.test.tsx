// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CitationPreview from './CitationPreview';
import { mockNativeDialog } from '../test/citationDialog';
let restore: () => void;
beforeEach(() => { restore = mockNativeDialog(); });
afterEach(() => { cleanup(); restore(); vi.unstubAllGlobals(); });
describe('Additive offline citation preview', () => {
  it('opens a citation without making an API request', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    render(<CitationPreview />);
    expect(screen.getByRole('heading', { name: 'CITATION DRAWER — OFFLINE PREVIEW' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show citation preview' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open citation E2' }));
    expect(screen.getByRole('dialog').textContent).toContain('SYNTHETIC FIXTURE');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('hiding the preview unmounts its drawer', () => {
    render(<CitationPreview />);
    fireEvent.click(screen.getByRole('button', { name: 'Show citation preview' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open citation E1' }));
    // Programmatic jsdom click: a real modal makes the background inert.
    fireEvent.click(screen.getByRole('button', { name: 'Hide citation preview' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
