import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, GitBranch, Search, Sparkles } from 'lucide-react';
import type { Repository } from '../../api/repositories';
import { getRecommendations } from '../../api/recommendations';
import './RepositoryOverview.css';

interface Props {
  repository: Repository;
  onAnalyzePR: () => void;
  onOpenGraph: (symbolId?: number) => void;
  onOpenRecommendations: () => void;
  onOpenSearch: () => void;
}

function formatNumber(value: number | null) {
  return value === null ? '—' : new Intl.NumberFormat().format(value);
}

export default function RepositoryOverview({
  repository,
  onAnalyzePR,
  onOpenGraph,
  onOpenRecommendations,
  onOpenSearch,
}: Props) {
  const recommendationsQuery = useQuery({
    queryKey: ['recommendations', repository.id, 'overview'],
    queryFn: ({ signal }) => getRecommendations(repository.id, 3, signal),
    enabled: repository.status === 'ready',
    retry: false,
  });
  const recommendations = recommendationsQuery.data?.recommendations ?? [];

  return (
    <div className="reposcope-overview-screen">
      <header className="reposcope-page-header">
        <div>
          <span className="reposcope-eyebrow">REPOSITORY OVERVIEW</span>
          <h1 className="reposcope-page-title">{repository.name}</h1>
          <p className="reposcope-page-subtitle">
            Live architecture intelligence for the indexed {repository.default_branch} branch.
          </p>
        </div>
        <div className="reposcope-page-actions">
          <button type="button" className="bauhaus-btn" onClick={onOpenSearch}>
            <Search size={15} /> SEARCH CODE
          </button>
          <button type="button" className="bauhaus-btn-invert" onClick={onAnalyzePR}>
            ANALYZE PATCH <ArrowUpRight size={15} />
          </button>
        </div>
      </header>

      <section className="reposcope-telemetry-section" aria-labelledby="repo-telemetry">
        <div className="reposcope-telemetry-header">
          <span id="repo-telemetry" className="reposcope-telemetry-title">LIVE REPOSITORY TELEMETRY</span>
          <span className="reposcope-telemetry-meta">
            {repository.status.toUpperCase()} · {repository.head_sha?.slice(0, 7) ?? 'awaiting index'}
          </span>
        </div>
        <div className="reposcope-telemetry-grid">
          <div className="reposcope-telemetry-card reposcope-telemetry-card--beige">
            <span className="reposcope-telemetry-card__label">Indexed symbols</span>
            <strong className="reposcope-telemetry-card__value">{formatNumber(repository.symbol_count)}</strong>
            <span className="reposcope-telemetry-card__sub">From the current snapshot</span>
          </div>
          <div className="reposcope-telemetry-card reposcope-telemetry-card--blue">
            <span className="reposcope-telemetry-card__label">Source files</span>
            <strong className="reposcope-telemetry-card__value">{formatNumber(repository.file_count)}</strong>
            <span className="reposcope-telemetry-card__sub">Indexed repository files</span>
          </div>
          <div className="reposcope-telemetry-card reposcope-telemetry-card--pink">
            <span className="reposcope-telemetry-card__label">Snapshot</span>
            <strong className="reposcope-telemetry-card__value">{repository.snapshot_id ?? '—'}</strong>
            <span className="reposcope-telemetry-card__sub">Published graph snapshot</span>
          </div>
          <div className="reposcope-telemetry-card reposcope-telemetry-card--green">
            <span className="reposcope-telemetry-card__label">Pipeline health</span>
            <strong className="reposcope-telemetry-card__value reposcope-telemetry-card__value--text">
              {repository.status === 'ready' ? 'Ready' : repository.status}
            </strong>
            <span className="reposcope-telemetry-card__sub">API and worker status</span>
          </div>
        </div>
      </section>

      <section className="reposcope-overview-middle-row" aria-label="Live repository tools">
        <div className="reposcope-arch-card reposcope-live-panel">
          <div className="reposcope-arch-card__header">
            <div>
              <span className="reposcope-eyebrow">GRAPH WORKSPACE</span>
              <h2 className="reposcope-arch-card__title">Explore the dependency graph</h2>
              <p className="reposcope-arch-card__subtitle">
                Search a symbol to inspect its real upstream and downstream relationships.
              </p>
            </div>
            <GitBranch size={20} />
          </div>
          <div className="reposcope-live-panel__empty">
            <p>Graph navigation starts from a live symbol result.</p>
            <button type="button" className="bauhaus-btn-invert" onClick={onOpenSearch}>
              FIND A SYMBOL <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
        <div className="reposcope-assistant-panel reposcope-live-panel">
          <span className="reposcope-eyebrow">ASK REPOSCOPE</span>
          <h2 className="reposcope-assistant-panel__title">Ask grounded questions.</h2>
          <p className="reposcope-assistant-panel__answer">
            The Q&A workflow uses the indexed snapshot and returns evidence-backed answers.
          </p>
          <button type="button" className="bauhaus-btn-invert" onClick={() => onOpenGraph()}>
            OPEN GRAPH <ArrowUpRight size={14} />
          </button>
        </div>
      </section>

      <section className="reposcope-recommendations-section" aria-labelledby="overview-recommendations">
        <div className="reposcope-section-header">
          <div>
            <span className="reposcope-eyebrow">HEURISTIC FINDINGS</span>
            <h2 id="overview-recommendations" className="reposcope-section-title">Recommended next moves</h2>
            <p className="reposcope-section-subtitle">Generated from the current published snapshot.</p>
          </div>
          <button type="button" className="reposcope-inline-link-btn" onClick={onOpenRecommendations}>
            VIEW ALL <ArrowUpRight size={13} />
          </button>
        </div>
        {recommendationsQuery.isPending && <div className="reposcope-live-panel__empty">Loading live recommendations…</div>}
        {recommendationsQuery.isError && (
          <div className="reposcope-form-error" role="alert">
            Recommendations are unavailable until the repository index is ready.
          </div>
        )}
        {!recommendationsQuery.isPending && !recommendationsQuery.isError && recommendations.length === 0 && (
          <div className="reposcope-live-panel__empty">
            <Sparkles size={18} />
            <p>No recommendations were published for this snapshot.</p>
          </div>
        )}
        <div className="reposcope-recommendations-grid">
          {recommendations.map((item, index) => (
            <article key={item.id} className="reposcope-recommendation-card">
              <div>
                <div className="reposcope-recommendation-card__top">
                  <span className="reposcope-recommendation-card__num">{String(index + 1).padStart(2, '0')}</span>
                  <span className="reposcope-recommendation-card__tag">{item.category}</span>
                </div>
                <h3 className="reposcope-recommendation-card__title">{item.title}</h3>
                <p className="reposcope-recommendation-card__desc">{item.description}</p>
              </div>
              {item.symbol_id && (
                <button type="button" className="reposcope-recommendation-card__action" onClick={() => onOpenGraph(item.symbol_id!)}>
                  INSPECT SYMBOL <ArrowUpRight size={13} />
                </button>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
