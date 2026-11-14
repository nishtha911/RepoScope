import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, ChevronDown, LoaderCircle, RefreshCw, X } from 'lucide-react';
import { getRecommendations } from '../api/recommendations';
import { submitRecommendationFeedback } from '../api/prImpact';
import type { RecommendationItem } from '../types/recommendations';
import './RecommendationsBoard.css';

interface Props {
  repoId: number;
  repoName: string;
  apiBase?: string;
  offlinePreview?: boolean;
  onInspectSymbol?: (symbolId: number) => void;
}

const filters = ['ALL', 'UNTESTED_HOTSPOT', 'COMPLEXITY_HOTSPOT', 'API_DOC_GAP'] as const;
type Filter = (typeof filters)[number];

export default function RecommendationsBoard({ repoId, repoName, onInspectSymbol }: Props) {
  const [filter, setFilter] = useState<Filter>('ALL');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [feedback, setFeedback] = useState<Record<number, string>>({});
  const query = useQuery({
    queryKey: ['recommendations', repoId],
    queryFn: ({ signal }) => getRecommendations(repoId, 10, signal),
    retry: false,
  });
  const items = query.data?.recommendations ?? [];
  const visible = items.filter((item) => filter === 'ALL' || item.category.toUpperCase() === filter);

  async function sendFeedback(item: RecommendationItem, action: 'accepted' | 'dismissed') {
    try {
      await submitRecommendationFeedback(item.id, action);
      setFeedback((previous) => ({ ...previous, [item.id]: action }));
    } catch {
      setFeedback((previous) => ({ ...previous, [item.id]: 'failed' }));
    }
  }

  return (
    <section className="rec-board" aria-labelledby="recommendations-title">
      <header className="rec-board__header">
        <div className="rec-board__title-wrap">
          <span className="rec-board__kicker">LIVE RECOMMENDER // PUBLISHED SNAPSHOT</span>
          <h1 id="recommendations-title" className="rec-board__title">What to work on next</h1>
          <p className="rec-board__desc">
            Findings returned by the repository recommendation API, ranked by deterministic impact,
            likelihood, effort, and confidence.
          </p>
        </div>
        <div className="rec-board__meta-box">
          <span className="rec-board__mode-badge">LIVE API</span>
          <span className="rec-board__repo-info">{repoName} · {query.data?.commit_sha?.slice(0, 7) ?? 'current snapshot'}</span>
        </div>
      </header>

      <div className="rec-board__filter-bar">
        <div className="rec-board__filter-chips" role="tablist">
          {filters.map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={filter === option}
              className={`rec-board__filter-chip ${filter === option ? 'rec-board__filter-chip--active' : ''}`}
              onClick={() => setFilter(option)}
            >
              {option.replaceAll('_', ' ')} ({option === 'ALL' ? items.length : items.filter((item) => item.category.toUpperCase() === option).length})
            </button>
          ))}
        </div>
        <button type="button" className="bauhaus-btn-invert" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw size={14} className={query.isFetching ? 'reposcope-spin' : ''} /> REFRESH
        </button>
      </div>

      {query.isPending && <div className="rec-board__state-box"><LoaderCircle className="reposcope-spin" /> Loading recommendations…</div>}
      {query.isError && <div className="rec-board__error-box" role="alert">Recommendations are unavailable until the repository index is ready.</div>}
      {!query.isPending && !query.isError && visible.length === 0 && (
        <div className="rec-board__state-box">No findings match this filter.</div>
      )}
      <div className="rec-board__list">
        {visible.map((item, index) => {
          const isExpanded = expanded.has(item.id);
          const action = feedback[item.id];
          return (
            <article key={item.id} className="rec-board__item">
              <div className="rec-board__item-rank">#{String(index + 1).padStart(2, '0')}</div>
              <div className="rec-board__item-main">
                <div className="rec-board__item-heading">
                  <span className="rec-board__item-category">{item.category}</span>
                  <span className="rec-board__item-score">{item.score === null ? '—' : item.score.toFixed(3)}</span>
                </div>
                <h2>{item.title}</h2>
                <p>{item.description}</p>
                <div className="rec-board__item-actions">
                  <button type="button" className="bauhaus-btn" onClick={() => setExpanded((previous) => {
                    const next = new Set(previous);
                    if (next.has(item.id)) next.delete(item.id); else next.add(item.id);
                    return next;
                  })}>
                    <ChevronDown size={14} /> {isExpanded ? 'HIDE RATIONALE' : 'SHOW RATIONALE'}
                  </button>
                  {item.symbol_id && onInspectSymbol && (
                    <button type="button" className="bauhaus-btn" onClick={() => onInspectSymbol(item.symbol_id!)}>
                      INSPECT SYMBOL
                    </button>
                  )}
                  <button type="button" className="bauhaus-btn" onClick={() => void sendFeedback(item, 'accepted')} disabled={Boolean(action)}>
                    <Check size={14} /> {action === 'accepted' ? 'ACCEPTED' : 'ACCEPT'}
                  </button>
                  <button type="button" className="bauhaus-btn" onClick={() => void sendFeedback(item, 'dismissed')} disabled={Boolean(action)}>
                    <X size={14} /> {action === 'dismissed' ? 'DISMISSED' : 'DISMISS'}
                  </button>
                </div>
                {isExpanded && (
                  <div className="rec-board__rationale">
                    <strong>{item.rationale_source ?? 'deterministic'}</strong>
                    <p>{item.rationale ?? 'No rationale was returned for this finding.'}</p>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
