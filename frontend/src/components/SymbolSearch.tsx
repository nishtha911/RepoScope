import { useEffect, useId, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSymbols, SymbolsApiError } from '../api/symbols';
import type { SymbolKind, SymbolListItem } from '../api/symbols';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import './SymbolSearch.css';

interface Props {
  repoId: number;
  repoName: string;
  query: string;
  onQueryChange: (value: string) => void;
  apiBase?: string;
}
const labels: Record<SymbolKind, string> = {
  function: 'Function', method: 'Method', class: 'Class', endpoint: 'Endpoint',
  module: 'Module', parameter: 'Parameter', variable: 'Variable',
};
export default function SymbolSearch({ repoId, repoName, query, onQueryChange, apiBase }: Props) {
  const inputId = useId();
  const [kind, setKind] = useState<SymbolKind | ''>('');
  const [source, setSource] = useState<{ repoId: number; symbol: SymbolListItem } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const currentQuery = query.trim();
  const debouncedQuery = useDebouncedValue(currentQuery, 300);
  const validRepo = Number.isSafeInteger(repoId) && repoId > 0;
  const ready = validRepo && currentQuery.length > 0 && currentQuery.length <= 2000 && currentQuery === debouncedQuery;
  const results = useQuery({
    queryKey: ['symbols', repoId, debouncedQuery, kind, 20, apiBase ?? 'default'],
    queryFn: ({ signal }) => fetchSymbols({ repoId, query: debouncedQuery, kind, limit: 20, signal, apiBase }),
    enabled: ready,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
  useEffect(() => {
    if (source && source.repoId !== repoId) dialog.current?.close();
  }, [repoId, source]);
  function openSource(symbol: SymbolListItem) {
    setSource({ repoId, symbol });
    dialog.current?.showModal();
  }
  const visibleSymbols = ready ? results.data?.symbols : undefined;
  const selected = source?.repoId === repoId ? source.symbol : null;
  return (
    <section className="symbol-search" aria-labelledby={`${inputId}-heading`}>
      <header className="symbol-search__header">
        <h2 id={`${inputId}-heading`}>SYMBOL SEARCH</h2>
        <span className="symbol-search__mock">MOCK API</span>
      </header>
      <p className="symbol-search__context">{repoName} · repository ID {repoId}</p>
      <div className="symbol-search__controls">
        <div className="symbol-search__input-group">
          <label htmlFor={inputId}>Search symbols</label>
          <input id={inputId} className="bauhaus-input" type="search" value={query}
            onChange={(event) => onQueryChange(event.target.value)} maxLength={2000}
            placeholder="Search symbols by name…" autoComplete="off" />
        </div>
        <div>
          <label htmlFor={`${inputId}-kind`}>Symbol kind</label>
          <select id={`${inputId}-kind`} value={kind} onChange={(event) => setKind(event.target.value as SymbolKind | '')}>
            <option value="">All kinds</option>
            <option value="function">Function</option><option value="method">Method</option>
            <option value="class">Class</option><option value="endpoint">Endpoint</option>
            <option value="module">Module</option><option value="parameter">Parameter</option>
            <option value="variable">Variable</option>
          </select>
        </div>
      </div>
      <p className="symbol-search__notice">These are synthetic contract examples, not extracted repository facts. The current mock contains one method; try “resolve”.</p>
      <div aria-live="polite" aria-atomic="true" className="symbol-search__status">
        {!validRepo ? 'Select a valid repository.' : !currentQuery ? 'Type a symbol name to search.'
          : !ready ? 'Waiting for typing to stop…' : results.isPending ? 'Searching symbols…'
          : results.isError ? '' : `${visibleSymbols?.length ?? 0} matching symbol(s) shown.`}
      </div>
      {ready && results.isError && <div role="alert" className="symbol-search__error">
        <p>{results.error.message}{results.error instanceof SymbolsApiError ? ` [${results.error.code}]` : ''}</p>
        <button type="button" className="bauhaus-btn-invert" onClick={() => { void results.refetch(); }}>Retry search</button>
      </div>}
      {ready && results.isSuccess && visibleSymbols?.length === 0 && <p>No matching symbols. Try another name or kind.</p>}
      {visibleSymbols && visibleSymbols.length > 0 && <ul className="symbol-search__results" aria-label="Symbol results">
        {visibleSymbols.map((symbol) => <li key={symbol.id} className="symbol-search__result">
          <div className="symbol-search__result-heading">
            <span className="symbol-search__qualname">{symbol.qualname}</span>
            <span className={`symbol-search__badge symbol-search__badge--${symbol.kind}`}>{labels[symbol.kind]}</span>
          </div>
          <button type="button" className="symbol-search__location" onClick={() => openSource(symbol)}
            aria-label={`Open mock location for ${symbol.qualname}, lines ${symbol.start_line} to ${symbol.end_line}`}>
            {symbol.file_path}:L{symbol.start_line}–L{symbol.end_line}
          </button>
          <span className="symbol-search__source-note">Mock location · source not verified</span>
        </li>)}
      </ul>}
      <dialog ref={dialog} className="symbol-search__dialog" aria-labelledby={`${inputId}-source-title`} onClose={() => setSource(null)}>
        <h3 id={`${inputId}-source-title`}>Mock source location</h3>
        {selected && <dl>
          <dt>Repository</dt><dd>{repoName} (ID {repoId})</dd>
          <dt>Symbol</dt><dd>{selected.qualname} (ID {selected.id})</dd>
          <dt>File</dt><dd>{selected.file_path} (ID {selected.file_id})</dd>
          <dt>Lines</dt><dd>{selected.start_line}–{selected.end_line}, inclusive</dd>
        </dl>}
        <p>No source code or verified revision is available from this mock response. This action preserves file and line context for the Day 5 CodeViewer; it is not a live source link.</p>
        <button type="button" className="bauhaus-btn-invert" autoFocus onClick={() => dialog.current?.close()}>Close location</button>
      </dialog>
    </section>
  );
}
