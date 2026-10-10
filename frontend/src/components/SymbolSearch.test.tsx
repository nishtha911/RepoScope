import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SymbolSearch from './SymbolSearch';
const item = { id: 101, file_id: 12, name: 'resolve_calls', qualname: 'SymbolResolver.resolve_calls', kind: 'method', file_path: 'resolver.py', start_line: 142, end_line: 180 };
function Harness({ repoId = 1 }: { repoId?: number }) {
  const [query, setQuery] = useState('');
  return <SymbolSearch repoId={repoId} repoName={`Mock ${repoId}`} query={query} onQueryChange={setQuery} />;
}
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>);
  return { ...view, client };
}
function successfulFetch(symbols = [item]) {
  const mock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ symbols }), { status: 200 }));
  vi.stubGlobal('fetch', mock); return mock;
}
describe('SymbolSearch', () => {
  it('does not fetch blank input and debounces typing', async () => {
    vi.useFakeTimers(); const mock = successfulFetch(); mount();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'resolve' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(299); });
    expect(mock).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(mock).toHaveBeenCalledTimes(1);
  });
  it('shows method badges and mock line context without invented confidence', async () => {
    successfulFetch(); mount();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'resolve' } });
    expect(await screen.findByText('SymbolResolver.resolve_calls')).toBeInTheDocument();
    expect(screen.getByText('Method', { selector: 'span' })).toBeInTheDocument();
    expect(screen.queryByText(/CONFIDENCE/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Open mock location/ }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('142–180, inclusive')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close location' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('sends lowercase kind filters', async () => {
    const mock = successfulFetch(); mount();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'resolve' } });
    await screen.findByText('SymbolResolver.resolve_calls');
    fireEvent.change(screen.getByLabelText('Symbol kind'), { target: { value: 'class' } });
    await waitFor(() => expect(new URL(mock.mock.calls.at(-1)![0]).searchParams.get('kind')).toBe('class'));
  });
  it('distinguishes empty results', async () => {
    successfulFetch([]); mount();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'absent' } });
    expect(await screen.findByText(/No matching symbols/)).toBeInTheDocument();
  });
  it('shows errors instead of demo fallback results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Backend unavailable'))); mount();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'resolve' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    expect(screen.queryByText('SymbolResolver.resolve_calls')).not.toBeInTheDocument();
  });
  it('isolates repository query keys and hides old results during a new request', async () => {
    const mock = successfulFetch(); const { rerender, client } = mount();
    fireEvent.change(screen.getByLabelText('Search symbols'), { target: { value: 'resolve' } });
    await screen.findByText('SymbolResolver.resolve_calls');
    mock.mockImplementation(() => new Promise(() => {}));
    rerender(<QueryClientProvider client={client}><Harness repoId={2} /></QueryClientProvider>);
    await waitFor(() => expect(new URL(mock.mock.calls.at(-1)![0]).pathname).toBe('/api/repos/2/symbols'));
    expect(screen.queryByText('SymbolResolver.resolve_calls')).not.toBeInTheDocument();
  });
});
