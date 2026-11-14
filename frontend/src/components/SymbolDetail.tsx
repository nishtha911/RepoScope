import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchSymbolDetail,
  fetchSymbolNeighbors,
  SymbolsApiError,
} from '../api/symbols';
import type {
  Neighbor,
  SymbolDetailResponse,
  SymbolKind,
} from '../api/symbols';
import './SymbolDetail.css';

interface Props {
  symbolId: number;
  repoId?: number;
  repoName?: string;
  offlinePreview?: boolean;
  apiBase?: string;
  onSelectSymbol?: (symbolId: number) => void;
  onBackToOverview?: () => void;
}

type DirectionFilter = 'ALL' | 'UPSTREAM' | 'DOWNSTREAM';

const kindLabels: Record<SymbolKind, string> = {
  function: 'Function',
  method: 'Method',
  class: 'Class',
  endpoint: 'Endpoint',
  module: 'Module',
  parameter: 'Parameter',
  variable: 'Variable',
};

export default function SymbolDetail({
  symbolId,
  repoId = 1,
  repoName = 'nishtha911/RepoScope',
  apiBase,
  onSelectSymbol,
  onBackToOverview,
}: Props) {
  const [filter, setFilter] = useState<DirectionFilter>('ALL');

  const validSymbolId = Number.isSafeInteger(symbolId) && symbolId > 0;

  // Query 1: Symbol detail metadata
  const detailQuery = useQuery({
    queryKey: ['symbol-detail', symbolId, apiBase ?? 'default'],
    queryFn: ({ signal }) =>
      fetchSymbolDetail({
        symbolId,
        signal,
        apiBase,
      }),
    enabled: validSymbolId,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Query 2: Upstream callers (dir=in)
  const upstreamQuery = useQuery({
    queryKey: ['symbol-neighbors', symbolId, 'in', apiBase ?? 'default'],
    queryFn: ({ signal }) =>
      fetchSymbolNeighbors({
        symbolId,
        direction: 'in',
        signal,
        apiBase,
      }),
    enabled: validSymbolId,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Query 3: Downstream callees (dir=out)
  const downstreamQuery = useQuery({
    queryKey: ['symbol-neighbors', symbolId, 'out', apiBase ?? 'default'],
    queryFn: ({ signal }) =>
      fetchSymbolNeighbors({
        symbolId,
        direction: 'out',
        signal,
        apiBase,
      }),
    enabled: validSymbolId,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Determine active data source
  let detail: SymbolDetailResponse | undefined;
  let upstreamCallers: Neighbor[] = [];
  let downstreamCallees: Neighbor[] = [];

  detail = detailQuery.data;
  upstreamCallers = upstreamQuery.data?.neighbors ?? [];
  downstreamCallees = downstreamQuery.data?.neighbors ?? [];

  const isLoading =
    (detailQuery.isPending || upstreamQuery.isPending || downstreamQuery.isPending);

  const isError =
    (detailQuery.isError || upstreamQuery.isError || downstreamQuery.isError);

  const error =
    detailQuery.error || upstreamQuery.error || downstreamQuery.error;

  function handleRetry() {
    void detailQuery.refetch();
    void upstreamQuery.refetch();
    void downstreamQuery.refetch();
  }

  function renderCallerCard(neighbor: Neighbor) {
    const isInbound = neighbor.direction === 'in';
    const confidencePercent =
      neighbor.confidence !== null
        ? `${Math.round(neighbor.confidence * 100)}%`
        : 'UNSPECIFIED';

    return (
      <li
        key={`${neighbor.symbol_id}-${neighbor.direction}`}
        className="symbol-detail__caller-card"
      >
        <div className="symbol-detail__caller-top">
          <span className="symbol-detail__caller-name">{neighbor.name}</span>

          <div className="symbol-detail__caller-badges">
            <span className="symbol-detail__edge-badge">
              {neighbor.relationship_type}
            </span>

            <span
              className="symbol-detail__direction-badge"
              title={
                isInbound
                  ? 'Upstream caller: calls this symbol'
                  : 'Downstream callee: called by this symbol'
              }
            >
              {isInbound ? '← Inbound Caller' : '→ Outbound Callee'}
            </span>
          </div>
        </div>

        <div className="symbol-detail__caller-meta">
          <div>
            CONFIDENCE:{' '}
            <span className="symbol-detail__confidence-score">
              {confidencePercent} ({neighbor.confidence ?? 'N/A'})
            </span>
          </div>

          {onSelectSymbol && (
            <button
              type="button"
              className="bauhaus-btn-invert"
              style={{ padding: '4px 12px', fontSize: '0.75rem' }}
              onClick={() => onSelectSymbol(neighbor.symbol_id)}
              aria-label={`Inspect symbol ${neighbor.name} with ID ${neighbor.symbol_id}`}
            >
              INSPECT SYMBOL #{neighbor.symbol_id} →
            </button>
          )}
        </div>
      </li>
    );
  }

  return (
    <section className="symbol-detail" aria-labelledby="symbol-detail-heading">
      {/* HEADER BAR */}
      <header className="symbol-detail__header">
        <div className="symbol-detail__title-group">
          <h2 id="symbol-detail-heading">
            SYMBOL DETAIL &amp; 1-HOP NEIGHBORHOOD
          </h2>

          <p className="symbol-detail__subtitle">
            {repoName} (Repo ID: {repoId}) · Symbol ID: #{symbolId}
          </p>
        </div>

        <div className="symbol-detail__actions">
          {onBackToOverview && (
            <button
              type="button"
              className="bauhaus-btn"
              onClick={onBackToOverview}
            >
              ← BACK TO OVERVIEW
            </button>
          )}

          <span className="symbol-detail__badge">
            LIVE API
          </span>
        </div>
      </header>

      {!validSymbolId && (
        <div className="symbol-detail__loading" role="status">
          Select a symbol from Code search or Ask RepoScope to inspect its live graph neighborhood.
        </div>
      )}

      {/* LOADING STATE */}
      {isLoading && (
        <div className="symbol-detail__loading" role="status" aria-live="polite">
          [ FETCHING SYMBOL #{symbolId} METADATA &amp; 1-HOP NEIGHBORS FROM BACKEND... ]
        </div>
      )}

      {/* ERROR STATE */}
      {isError && (
        <div className="symbol-detail__error" role="alert">
          <h3>FAILED TO LOAD SYMBOL #{symbolId}</h3>
          <p>
            {error instanceof Error ? error.message : 'An error occurred.'}
            {error instanceof SymbolsApiError ? ` [${error.code}]` : ''}
          </p>
          <button
            type="button"
            className="bauhaus-btn-invert"
            onClick={handleRetry}
          >
            RETRY REQUEST
          </button>
        </div>
      )}

      {/* MAIN CONTENT */}
      {!isLoading && !isError && detail && (
        <>
          <div className="symbol-detail__main-grid">
            {/* LEFT COLUMN: METADATA PANEL */}
            <div className="symbol-detail__panel bauhaus-border-r">
              <div className="symbol-detail__panel-header">
                <h3>METADATA PANEL</h3>
                <span
                  className={`symbol-search__badge symbol-search__badge--${detail.kind}`}
                >
                  {kindLabels[detail.kind] ?? detail.kind}
                </span>
              </div>

              <div className="symbol-detail__metadata-list">
                {/* STATS ROW: LINES & COMPLEXITY */}
                <div className="symbol-detail__stat-row">
                  <div className="symbol-detail__stat-card">
                    <span className="symbol-detail__stat-label">LINES (RANGE)</span>
                    <span className="symbol-detail__stat-value">
                      L{detail.start_line}–L{detail.end_line}
                    </span>
                    <span className="symbol-detail__stat-sub">
                      {detail.end_line - detail.start_line + 1} lines total
                    </span>
                  </div>

                  <div className="symbol-detail__stat-card">
                    <span className="symbol-detail__stat-label">
                      CYCLOMATIC COMPLEXITY
                    </span>
                    <span className="symbol-detail__stat-value">
                      {detail.cyclomatic_complexity ?? 'N/A'}
                    </span>
                    <span className="symbol-detail__stat-sub">
                      {detail.cyclomatic_complexity !== null
                        ? detail.cyclomatic_complexity <= 5
                          ? 'Low complexity (simple)'
                          : detail.cyclomatic_complexity <= 10
                            ? 'Moderate complexity'
                            : 'High complexity hotspot'
                        : 'Not computed'}
                    </span>
                  </div>
                </div>

                {/* QUALNAME & FILE */}
                <dl className="symbol-detail__meta-item">
                  <dt>QUALIFIED NAME</dt>
                  <dd style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                    {detail.qualname}
                  </dd>

                  <dt style={{ marginTop: '14px' }}>FILE PATH</dt>
                  <dd style={{ fontFamily: 'var(--font-mono)' }}>
                    {detail.file_path}
                  </dd>
                </dl>

                {/* SIGNATURE */}
                <dl className="symbol-detail__meta-item">
                  <dt>SIGNATURE</dt>
                  <dd>
                    <pre className="symbol-detail__signature-block">
                      <code>{detail.signature || 'No signature declared'}</code>
                    </pre>
                  </dd>
                </dl>

                {/* DOCSTRING */}
                <dl className="symbol-detail__meta-item">
                  <dt>DOCSTRING</dt>
                  <dd>
                    {detail.docstring ? (
                      <p className="symbol-detail__docstring">{detail.docstring}</p>
                    ) : (
                      <span style={{ color: '#777', fontStyle: 'italic' }}>
                        No docstring provided.
                      </span>
                    )}
                  </dd>
                </dl>
              </div>
            </div>

            {/* RIGHT COLUMN: 1-HOP UPSTREAM / DOWNSTREAM CALLERS */}
            <div className="symbol-detail__panel">
              <div className="symbol-detail__panel-header">
                <h3>1-HOP NEIGHBORHOOD CALLERS</h3>
                <span className="symbol-detail__badge">
                  GET /api/symbols/{symbolId}/neighbors
                </span>
              </div>

              {/* DIRECTION FILTER TABS */}
              <div
                className="symbol-detail__tabs"
                role="tablist"
                aria-label="Caller direction"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={filter === 'ALL'}
                  className={`symbol-detail__tab-btn ${
                    filter === 'ALL' ? 'symbol-detail__tab-btn--active' : ''
                  }`}
                  onClick={() => setFilter('ALL')}
                >
                  ALL 1-HOP ({upstreamCallers.length + downstreamCallees.length})
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={filter === 'UPSTREAM'}
                  className={`symbol-detail__tab-btn ${
                    filter === 'UPSTREAM' ? 'symbol-detail__tab-btn--active' : ''
                  }`}
                  onClick={() => setFilter('UPSTREAM')}
                >
                  UPSTREAM CALLERS ({upstreamCallers.length})
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={filter === 'DOWNSTREAM'}
                  className={`symbol-detail__tab-btn ${
                    filter === 'DOWNSTREAM' ? 'symbol-detail__tab-btn--active' : ''
                  }`}
                  onClick={() => setFilter('DOWNSTREAM')}
                >
                  DOWNSTREAM CALLEES ({downstreamCallees.length})
                </button>
              </div>

              {/* UPSTREAM CALLERS SECTION */}
              {(filter === 'ALL' || filter === 'UPSTREAM') && (
                <div className="symbol-detail__callers-section">
                  <div className="symbol-detail__callers-header">
                    <span className="symbol-detail__callers-title">
                      ↑ UPSTREAM CALLERS (INBOUND CALLS)
                    </span>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      dir=in
                    </span>
                  </div>

                  <p className="symbol-detail__callers-desc">
                    Symbols that invoke <code>{detail.name}</code> directly:
                  </p>

                  {upstreamCallers.length === 0 ? (
                    <div className="symbol-detail__empty-callers">
                      No 1-hop upstream callers found in the code graph.
                    </div>
                  ) : (
                    <ul
                      className="symbol-detail__caller-list"
                      aria-label="Upstream callers list"
                    >
                      {upstreamCallers.map(renderCallerCard)}
                    </ul>
                  )}
                </div>
              )}

              {/* DOWNSTREAM CALLEES SECTION */}
              {(filter === 'ALL' || filter === 'DOWNSTREAM') && (
                <div className="symbol-detail__callers-section">
                  <div className="symbol-detail__callers-header">
                    <span className="symbol-detail__callers-title">
                      ↓ DOWNSTREAM CALLEES (OUTBOUND CALLS)
                    </span>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      dir=out
                    </span>
                  </div>

                  <p className="symbol-detail__callers-desc">
                    Symbols that <code>{detail.name}</code> invokes directly:
                  </p>

                  {downstreamCallees.length === 0 ? (
                    <div className="symbol-detail__empty-callers">
                      No 1-hop downstream callees found in the code graph.
                    </div>
                  ) : (
                    <ul
                      className="symbol-detail__caller-list"
                      aria-label="Downstream callees list"
                    >
                      {downstreamCallees.map(renderCallerCard)}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* BOTTOM SECTION: INDEXED SOURCE LOCATION */}
          <div className="bauhaus-border-t symbol-detail__source-panel">
            <div className="symbol-detail__panel-header">
              <h3>INDEXED SOURCE LOCATION</h3>
            </div>
            <p className="symbol-detail__source-note">
              This workspace exposes verified symbol metadata and graph relationships from the
              selected snapshot. Full source retrieval is not part of the current API contract.
            </p>
            <code className="symbol-detail__source-location">
              {detail.file_path}:L{detail.start_line}–L{detail.end_line}
            </code>
          </div>
        </>
      )}
    </section>
  );
}

