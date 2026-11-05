// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import CitationInspector from './CitationInspector';
import { citationPreviewPack } from '../fixtures/citations';
import { mockNativeDialog } from '../test/citationDialog';
let restore: () => void;
beforeEach(() => { restore = mockNativeDialog(); });
afterEach(() => { cleanup(); restore(); });
describe('Answer-scoped citation resolution', () => {
  it('opens the clicked pill and closes it', () => {
    render(<CitationInspector answerId="a" pack={citationPreviewPack}>{cite => <p>Answer {cite('E2')}</p>}</CitationInspector>);
    const pill = screen.getByRole('button', { name: 'Open citation E2' });
    fireEvent.click(pill);
    expect(screen.getByRole('dialog').textContent).toContain('UserService.create');
    expect(pill.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Close citation drawer' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(pill);
  });
  it('closes stale selection when answer or pack changes', () => {
    const view = render(<CitationInspector answerId="a" pack={citationPreviewPack}>{cite => cite('E1')}</CitationInspector>);
    fireEvent.click(screen.getByRole('button', { name: 'Open citation E1' }));
    const other = structuredClone(citationPreviewPack);
    other.entries[0].source.file_path = 'different_answer.py';
    view.rerender(<CitationInspector answerId="b" pack={other}>{cite => cite('E1')}</CitationInspector>);
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Open citation E1' }));
    expect(screen.getByRole('dialog').textContent).toContain('different_answer.py');
  });
});
