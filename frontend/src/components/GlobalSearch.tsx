import { useEffect, useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  searchRepo,
  SearchApiError,
} from '../api/search';
import type {
  SearchCategory,
  SearchHit,
  SearchMode,
} from '../api/search';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import './GlobalSearch.css';

interface Props {
  repoId: number;
  repoName: string;
  query: string;
  onQueryChange: (query: string) => void;
  apiBase?: string;
  /** @deprecated Live API is always used. Retained for compatibility with callers. */
  offlinePreview?: boolean;
  onSelectSymbol?: (symbolId: number) => void;
  onLatencyChange?: (latencyMs: number) => void;
}

const categoryLabels: Record<SearchCategory, string> = {
  all: 'All',
  symbols: 'Symbols',
  documentation: 'Documentation',
  endpoints: 'Endpoints',
};

export default function GlobalSearch({
  repoId,
  repoName,
  query,
  onQueryChange,
  apiBase,
  onSelectSymbol,
  onLatencyChange,
}: Props) {
  const inputId = useId();
  const [activeTab, setActiveTab] = useState<SearchCategory>('all');
  const [mode, setMode] = useState<SearchMode>('hybrid');

  const trimmedQuery = query.trim();
  const debouncedQuery = useDebouncedValue(trimmedQuery, 300);

  const validRepo = Number.isSafeInteger(repoId) && repoId > 0;
  const ready =
    validRepo &&
    trimmedQuery.length > 0 &&
    trimmedQuery.length <= 2000 &&
    trimmedQuery === debouncedQuery;

  const searchQuery = useQuery({
    queryKey: [
      'global-search',
      repoId,
      debouncedQuery,
      mode,
      apiBase ?? 'default',
    ],
    queryFn: ({ signal }) =>
      searchRepo({
        repoId,
        query: debouncedQuery,
        mode,
        signal,
        apiBase,
      }),
    enabled: ready,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Calculate results based on mode
  let allHits: SearchHit[] = [];
  let latencyMs = 0;

  if (searchQuery.data) {
    allHits = searchQuery.data.hits;
    latencyMs = searchQuery.data.latency_ms;
  }

  // Notify parent of measured latency
  useEffect(() => {
    if (latencyMs > 0) {
      onLatencyChange?.(latencyMs);
    }
  }, [latencyMs, onLatencyChange]);

  // Tab filtering: All, Symbols, Documentation, Endpoints
  const symbolHits = allHits.filter((h) => h.category === 'symbol');
  const docHits = allHits.filter((h) => h.category === 'documentation');
  const endpointHits = allHits.filter((h) => h.category === 'endpoint');

  const tabCounts: Record<SearchCategory, number> = {
    all: allHits.length,
    symbols: symbolHits.length,
    documentation: docHits.length,
    endpoints: endpointHits.length,
  };

  const visibleHits =
    activeTab === 'all'
      ? allHits
      : activeTab === 'symbols'
        ? symbolHits
        : activeTab === 'documentation'
          ? docHits
          : endpointHits;

  const isPending = ready && searchQuery.isPending;
  const isError = ready && searchQuery.isError;
  const error = searchQuery.error;

  return (
    <section className="global-search" aria-labelledby={`${inputId}-title`}>
      {/* HEADER */}
      <header className="global-search__header">
        <h2 id={`${inputId}-title`}>GLOBAL CODEBASE SEARCH</h2>

        <span className="global-search__badge">
          POST /api/repos/{'{id}'}/search
        </span>
      </header>

      <p className="global-search__context">
        Repository: <strong>{repoName}</strong> (ID #{repoId}) · Multi-retriever Hybrid Search
      </p>

      {/* SEARCH CONTROLS */}
      <div className="global-search__controls">
        <div className="global-search__input-wrap">
          <label htmlFor={inputId}>Search Query</label>

          <div className="global-search__input-row">
            <input
              id={inputId}
              className="bauhaus-input"
              type="search"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Search symbols, documentation, and endpoints…"
              maxLength={2000}
              autoComplete="off"
            />

            {query.length > 0 && (
              <button
                type="button"
                className="global-search__clear-btn"
                onClick={() => onQueryChange('')}
                aria-label="Clear search query"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        <div className="global-search__mode-wrap">
          <label htmlFor={`${inputId}-mode`}>Search Mode</label>

          <select
            id={`${inputId}-mode`}
            value={mode}
            onChange={(e) => setMode(e.target.value as SearchMode)}
          >
            <option value="hybrid">Hybrid (RRF Fusion)</option>
            <option value="lexical">Lexical (BM25)</option>
            <option value="vector">Vector (ANN)</option>
          </select>
        </div>
      </div>

      {/* LATENCY & EXECUTION METRICS BAR */}
      {trimmedQuery.length > 0 && (allHits.length > 0 || latencyMs > 0) && (
        <div className="global-search__metrics-bar" role="region" aria-label="Search latency and execution metrics">
          <div className="global-search__latency">
            <span>SEARCH LATENCY:</span>
            <span className="global-search__latency-tag">
              {latencyMs}ms
            </span>
          </div>

          <div className="global-search__meta-tags">
            <span>MODE: {mode.toUpperCase()}</span>
            <span>TOTAL HITS: {allHits.length}</span>
            <span>FILTER: {categoryLabels[activeTab].toUpperCase()}</span>
          </div>
        </div>
      )}

      {/* TAB FILTERS: ALL, SYMBOLS, DOCUMENTATION, ENDPOINTS */}
      {trimmedQuery.length > 0 && (
        <div
          className="global-search__tabs"
          role="tablist"
          aria-label="Filter search results by category"
        >
          {(['all', 'symbols', 'documentation', 'endpoints'] as SearchCategory[]).map(
            (tab) => {
              const isActive = activeTab === tab;
              const count = tabCounts[tab];

              return (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={`global-search__tab-btn ${
                    isActive ? 'global-search__tab-btn--active' : ''
                  }`}
                  onClick={() => setActiveTab(tab)}
                >
                  {categoryLabels[tab].toUpperCase()} ({count})
                </button>
              );
            },
          )}
        </div>
      )}

      {/* STATUS / ANNOUNCEMENTS */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="global-search__status"
      >
        {!validRepo
          ? 'Select a valid repository.'
          : trimmedQuery.length === 0
            ? 'Type a query to search symbols, endpoints, and documentation.'
            : isPending
              ? 'Executing hybrid reciprocal rank fusion search…'
              : isError
                ? ''
                : `${visibleHits.length} matching result(s) in ${categoryLabels[activeTab]}.`}
      </div>

      {/* ERROR BANNER */}
      {isError && (
        <div role="alert" className="global-search__error">
          <h3>SEARCH FAILED</h3>
          <p>
            {error instanceof Error ? error.message : 'Unknown search error'}
            {error instanceof SearchApiError ? ` [${error.code}]` : ''}
          </p>

          <button
            type="button"
            className="bauhaus-btn-invert"
            onClick={() => void searchQuery.refetch()}
          >
            Retry Search
          </button>
        </div>
      )}

      {/* EMPTY STATE */}
      {trimmedQuery.length > 0 &&
        !isPending &&
        !isError &&
        visibleHits.length === 0 && (
          <div className="global-search__empty">
            <p>
              No {categoryLabels[activeTab].toLowerCase()} hits found for “{trimmedQuery}”.
            </p>
            {activeTab !== 'all' && (
              <button
                type="button"
                className="bauhaus-btn-invert"
                style={{ marginTop: '12px' }}
                onClick={() => setActiveTab('all')}
              >
                View all categories ({allHits.length} hits)
              </button>
            )}
          </div>
        )}

      {/* RESULTS LIST */}
      {visibleHits.length > 0 && (
        <ul className="global-search__results" aria-label="Search results">
          {visibleHits.map((hit) => {
            const isSymbol = hit.category === 'symbol';
            const isEndpoint = hit.category === 'endpoint';

            return (
              <li key={`${hit.symbol_id}-${hit.name}`} className="global-search__card">
                <div className="global-search__card-header">
                  <span className="global-search__hit-name">{hit.name}</span>

                  <div className="global-search__badges">
                    <span
                      className={`global-search__category-badge global-search__category-badge--${hit.category}`}
                    >
                      {hit.category.toUpperCase()}
                    </span>

                    <span className="global-search__score-badge" title="RRF / ANN Match Score">
                      SCORE: {hit.score.toFixed(3)}
                    </span>
                  </div>
                </div>

                <div className="global-search__file-path">
                  {hit.file_path}
                </div>

                <pre className="global-search__snippet">
                  <code>{hit.snippet}</code>
                </pre>

                {onSelectSymbol && (
                  <div className="global-search__card-footer">
                    <button
                      type="button"
                      className="bauhaus-btn-invert"
                      style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                      onClick={() => onSelectSymbol(hit.symbol_id)}
                      aria-label={`Inspect ${hit.name} with ID ${hit.symbol_id}`}
                    >
                      {isSymbol
                        ? `INSPECT SYMBOL #${hit.symbol_id} →`
                        : isEndpoint
                          ? `INSPECT ROUTE #${hit.symbol_id} →`
                          : `VIEW DOC #${hit.symbol_id} →`}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
