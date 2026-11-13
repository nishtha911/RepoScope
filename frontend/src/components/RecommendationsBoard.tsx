import React, { useState, useEffect } from 'react';
import type {
  RecommendationItem,
  RecommendationsResponse,
} from '../types/recommendations';
import {
  getCategoryMeta,
  getImpactLevel,
  getImpactBadgeClass,
  formatScore,
} from '../utils/recommendations';
import './RecommendationsBoard.css';

export interface RecommendationsBoardProps {
  repoId: number;
  repoName: string;
  apiBase?: string;
  /** @deprecated Live API is always used. Retained for compatibility with callers. */
  offlinePreview?: boolean;
  onInspectSymbol?: (symbolId: number) => void;
  maxItems?: number;
}

type FilterCategory =
  | 'ALL'
  | 'UNTESTED_HOTSPOT'
  | 'COMPLEXITY_HOTSPOT'
  | 'API_DOC_GAP';

export const RecommendationsBoard: React.FC<RecommendationsBoardProps> = ({
  repoId,
  repoName,
  apiBase = 'http://localhost:8000/api',
  onInspectSymbol,
  maxItems = 10,
}) => {
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterCategory>('ALL');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [metaInfo, setMetaInfo] = useState<{
    snapshot_id: number | null;
    run_id: number | null;
    commit_sha: string | null;
  }>({ snapshot_id: null, run_id: null, commit_sha: null });

  useEffect(() => {
    let ignore = false;
    async function fetchLive() {
      try {
        const response = await fetch(
          `${apiBase}/repos/${repoId}/recommendations?k=${maxItems}`,
        );

        if (!response.ok) {
          throw new Error(
            `Recommendations API returned HTTP ${response.status}: ${response.statusText}`,
          );
        }

        const data = (await response.json()) as RecommendationsResponse;
        if (!ignore) {
          setItems(data.recommendations || []);
          setMetaInfo({
            snapshot_id: data.snapshot_id,
            run_id: data.run_id,
            commit_sha: data.commit_sha,
          });
          setError(null);
          setIsLoading(false);
        }
      } catch (err: unknown) {
        if (!ignore) {
          const message =
            err instanceof Error ? err.message : 'Failed to fetch recommendations';
          setError(message);
          setIsLoading(false);
        }
      }
    }

    fetchLive();
    return () => {
      ignore = true;
    };
  }, [apiBase, repoId, maxItems]);

  const handleRefresh = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${apiBase}/repos/${repoId}/recommendations?k=${maxItems}`,
      );

      if (!response.ok) {
        throw new Error(
          `Recommendations API returned HTTP ${response.status}: ${response.statusText}`,
        );
      }

      const data = (await response.json()) as RecommendationsResponse;
      setItems(data.recommendations || []);
      setMetaInfo({
        snapshot_id: data.snapshot_id,
        run_id: data.run_id,
        commit_sha: data.commit_sha,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch recommendations';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleRationale = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleAllRationales = () => {
    if (expandedIds.size === filteredItems.length) {
      setExpandedIds(new Set());
    } else {
      setExpandedIds(new Set(filteredItems.map((item) => item.id)));
    }
  };

  // Filter items
  const filteredItems = items.filter((item) => {
    if (activeFilter === 'ALL') return true;
    const norm = (item.category || '').toUpperCase();
    if (activeFilter === 'UNTESTED_HOTSPOT') return norm.includes('UNTESTED');
    if (activeFilter === 'COMPLEXITY_HOTSPOT') return norm.includes('COMPLEXITY');
    if (activeFilter === 'API_DOC_GAP') return norm.includes('DOC') || norm.includes('API');
    return true;
  });

  // Category counts
  const countUntested = items.filter((item) =>
    (item.category || '').toUpperCase().includes('UNTESTED'),
  ).length;
  const countComplexity = items.filter((item) =>
    (item.category || '').toUpperCase().includes('COMPLEXITY'),
  ).length;
  const countDocGaps = items.filter((item) => {
    const c = (item.category || '').toUpperCase();
    return c.includes('DOC') || c.includes('API');
  }).length;

  return (
    <div
      className="rec-board"
      role="region"
      aria-label="What to Work on Next Recommendations Board"
    >
      {/* HEADER SECTION */}
      <header className="rec-board__header bauhaus-border-b">
        <div className="rec-board__title-wrap">
          <span className="rec-board__kicker">
            ACTION RECOMMENDER // HEURISTIC PRIORITIZATION ENGINE
          </span>
          <h2 className="rec-board__title">WHAT TO WORK ON NEXT</h2>
          <p className="rec-board__desc">
            Top ranked findings prioritized by impact, likelihood, effort, and confidence.
            Each finding includes detailed feature citations and rationale explanations.
          </p>
        </div>

        <div className="rec-board__meta-box">
          <span
            className={`rec-board__mode-badge ${
              ''
            }`}
          >
            {`LIVE API: GET /api/repos/${repoId}/recommendations`}
          </span>

          <span className="rec-board__repo-info">
            REPO: <strong>{repoName}</strong> (#{repoId})
            {metaInfo.run_id && ` // RUN #${metaInfo.run_id}`}
          </span>
        </div>
      </header>

      {/* FILTER AND ACTION BAR */}
      <section
        className="rec-board__filter-bar bauhaus-border-b"
        aria-label="Category filters and actions"
      >
        <div className="rec-board__filter-chips" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeFilter === 'ALL'}
            className={`rec-board__filter-chip ${
              activeFilter === 'ALL' ? 'rec-board__filter-chip--active' : ''
            }`}
            onClick={() => setActiveFilter('ALL')}
          >
            ALL FINDINGS ({items.length})
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeFilter === 'UNTESTED_HOTSPOT'}
            className={`rec-board__filter-chip ${
              activeFilter === 'UNTESTED_HOTSPOT'
                ? 'rec-board__filter-chip--active'
                : ''
            }`}
            onClick={() => setActiveFilter('UNTESTED_HOTSPOT')}
          >
            🧪 UNTESTED HOTSPOTS ({countUntested})
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeFilter === 'COMPLEXITY_HOTSPOT'}
            className={`rec-board__filter-chip ${
              activeFilter === 'COMPLEXITY_HOTSPOT'
                ? 'rec-board__filter-chip--active'
                : ''
            }`}
            onClick={() => setActiveFilter('COMPLEXITY_HOTSPOT')}
          >
            COMPLEXITY HOTSPOTS ({countComplexity})
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeFilter === 'API_DOC_GAP'}
            className={`rec-board__filter-chip ${
              activeFilter === 'API_DOC_GAP'
                ? 'rec-board__filter-chip--active'
                : ''
            }`}
            onClick={() => setActiveFilter('API_DOC_GAP')}
          >
            📄 API DOC GAPS ({countDocGaps})
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            className="bauhaus-btn"
            style={{ padding: '6px 12px', fontSize: '0.72rem' }}
            onClick={toggleAllRationales}
            disabled={filteredItems.length === 0}
            aria-label="Toggle all rationale dropdowns"
          >
            {expandedIds.size === filteredItems.length && filteredItems.length > 0
              ? 'COLLAPSE ALL RATIONALES'
              : 'EXPAND ALL RATIONALES'}
          </button>

          <button
            type="button"
            className="bauhaus-btn-invert"
            style={{ padding: '6px 12px', fontSize: '0.72rem' }}
            onClick={handleRefresh}
            disabled={isLoading}
            aria-label="Refresh recommendations"
          >
            {isLoading ? 'REFRESHING…' : '↻ REFRESH'}
          </button>
        </div>
      </section>

      {/* MAIN CONTENT AREA */}
      <main className="rec-board__content">
        {/* Loading state */}
        {isLoading && (
          <div className="rec-board__state-box" role="status" aria-label="Loading">
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800 }}>
              CALCULATING TOP CODEBASE RECOMMENDATIONS…
            </span>
          </div>
        )}

        {/* Error state */}
        {error && !isLoading && (
          <div className="rec-board__error-box" role="alert">
            <div style={{ fontWeight: 800, marginBottom: '6px' }}>
              ⚠️ FAILED TO LOAD RECOMMENDATIONS
            </div>
            <div>{error}</div>
            <button
              type="button"
              className="bauhaus-btn"
              style={{ marginTop: '12px', padding: '6px 14px' }}
              onClick={handleRefresh}
            >
              RETRY FETCH
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && filteredItems.length === 0 && (
          <div className="rec-board__state-box">
            <h3 style={{ margin: 0 }}>NO FINDINGS MATCH THIS FILTER</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.85rem' }}>
              Select a different category tab or clear active filters.
            </p>
          </div>
        )}

        {/* Top 10 Ranked Findings List */}
        {!isLoading && !error && filteredItems.length > 0 && (
          <div
            className="rec-board__list"
            aria-label="Ranked recommendation findings"
          >
            {filteredItems.map((item, index) => {
              const rank = index + 1;
              const rankFormatted = rank < 10 ? `#0${rank}` : `#${rank}`;
              const catMeta = getCategoryMeta(item.category);
              const impactLevel = getImpactLevel(
                item.computed_features?.impact,
                item.score,
              );
              const impactBadgeClass = getImpactBadgeClass(impactLevel);
              const isExpanded = expandedIds.has(item.id);
              const panelId = `rationale-panel-${item.id}`;

              return (
                <article
                  key={item.id}
                  className="rec-card"
                  data-testid="recommendation-card"
                  aria-label={`Recommendation ${rankFormatted}: ${item.title}`}
                >
                  {/* CARD HEADER */}
                  <header className="rec-card__header">
                    <div className="rec-card__header-left">
                      {/* Rank Badge */}
                      <span
                        className="rec-card__rank-badge"
                        data-testid="rank-badge"
                      >
                        {rankFormatted}
                      </span>

                      {/* Category Tag */}
                      <span
                        className={`rec-cat-tag ${catMeta.className}`}
                        data-testid="category-tag"
                      >
                        <span>{catMeta.icon}</span>
                        <span>{catMeta.label}</span>
                      </span>

                      {/* Impact Badge */}
                      <span
                        className={`rec-impact-badge ${impactBadgeClass}`}
                        data-testid="impact-badge"
                      >
                        {impactLevel} IMPACT
                      </span>
                    </div>

                    {/* Priority Score */}
                    <div className="rec-card__header-right">
                      <div className="rec-card__score-wrap">
                        <span className="rec-card__score-label">PRIORITY SCORE</span>
                        <span
                          className="rec-card__score-val"
                          data-testid="priority-score"
                        >
                          {formatScore(item.score)}
                        </span>
                      </div>
                    </div>
                  </header>

                  {/* CARD BODY */}
                  <div className="rec-card__body">
                    <h3 className="rec-card__title">{item.title}</h3>
                    <p className="rec-card__desc">{item.description}</p>

                    {/* Location Badge (file & line / symbol qualname) */}
                    {(item.file_path || item.qualname) && (
                      <div className="rec-card__location" data-testid="location-badge">
                        <span>📍</span>
                        <span>
                          {item.file_path || 'Symbol'}:
                          {item.start_line ? `${item.start_line}` : ''}{' '}
                          {item.qualname && <code>({item.qualname})</code>}
                        </span>
                      </div>
                    )}

                    {/* Feature Metrics Strip */}
                    <div className="rec-card__metrics-bar">
                      <div className="rec-card__metric-token">
                        <span className="rec-card__metric-name">IMPACT:</span>
                        <span className="rec-card__metric-val">
                          {formatScore(item.computed_features?.impact)}
                        </span>
                      </div>
                      <div className="rec-card__metric-token">
                        <span className="rec-card__metric-name">LIKELIHOOD:</span>
                        <span className="rec-card__metric-val">
                          {formatScore(item.computed_features?.likelihood)}
                        </span>
                      </div>
                      <div className="rec-card__metric-token">
                        <span className="rec-card__metric-name">EFFORT:</span>
                        <span className="rec-card__metric-val">
                          {formatScore(item.computed_features?.effort)}
                        </span>
                      </div>
                      <div className="rec-card__metric-token">
                        <span className="rec-card__metric-name">CONFIDENCE:</span>
                        <span className="rec-card__metric-val">
                          {formatScore(item.computed_features?.confidence)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* RATIONALE DROPDOWN / ACCORDION */}
                  <div className="rec-card__rationale-wrap">
                    <button
                      type="button"
                      className="rec-card__dropdown-toggle"
                      onClick={() => toggleRationale(item.id)}
                      aria-expanded={isExpanded}
                      aria-controls={panelId}
                      data-testid={`rationale-toggle-${item.id}`}
                    >
                      <span>
                        {isExpanded ? '▴ HIDE RATIONALE' : '▾ WHY THIS MATTERS (RATIONALE)'}
                      </span>
                      <span style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        {item.rationale_source === 'llm_constrained'
                          ? 'LLM-CONSTRAINED'
                          : 'DETERMINISTIC'}
                      </span>
                    </button>

                    {isExpanded && (
                      <div
                        id={panelId}
                        className="rec-card__dropdown-panel"
                        data-testid={`rationale-panel-${item.id}`}
                      >
                        <div className="rec-card__rationale-header">
                          <strong style={{ fontSize: '0.72rem', letterSpacing: '0.05em' }}>
                            PRIORITIZATION RATIONALE:
                          </strong>

                          <span
                            className={`rec-card__rationale-source ${
                              item.rationale_source === 'llm_constrained'
                                ? 'rec-card__rationale-source--llm'
                                : 'rec-card__rationale-source--deterministic'
                            }`}
                          >
                            {item.rationale_source === 'llm_constrained'
                              ? '✓ LLM-CONSTRAINED RATIONALE'
                              : 'DETERMINISTIC RATIONALE'}
                          </span>
                        </div>

                        {/* Rationale text */}
                        <p className="rec-card__rationale-text">
                          {item.rationale || 'No detailed rationale generated for this finding.'}
                        </p>

                        {/* Feature Citations */}
                        {item.feature_citations && item.feature_citations.length > 0 && (
                          <div className="rec-card__citations-strip">
                            <span className="rec-card__citations-label">CITATIONS:</span>
                            {item.feature_citations.map((c, i) => (
                              <span
                                key={i}
                                className="rec-card__citation-pill"
                                data-testid="citation-pill"
                              >
                                {c.feature}: <strong>{c.value}</strong>
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Actions in panel */}
                        <div className="rec-card__panel-actions">
                          {item.symbol_id && onInspectSymbol && (
                            <button
                              type="button"
                              className="bauhaus-btn-invert rec-card__inspect-btn"
                              onClick={() => onInspectSymbol(item.symbol_id!)}
                            >
                              INSPECT SYMBOL IN GRAPH →
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
};

export default RecommendationsBoard;
