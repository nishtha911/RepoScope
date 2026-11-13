import React from 'react';
import { Plus, ExternalLink } from 'lucide-react';
import ArchitectureMap from './ArchitectureMap';
import ArchitectureAssistant from './ArchitectureAssistant';
import { useQuery } from '@tanstack/react-query';
import type { Repository } from '../../api/repositories';

interface RepositoryOverviewProps {
  onAnalyzePR: () => void;
  onOpenGraph: (symbolId?: number) => void;
  onOpenSearch: (query?: string) => void;
  onOpenRecommendations: () => void;
  onOpenCitation?: (filePath: string, range: string) => void;
  repository: Repository;
  apiBase?: string;
}

export const RepositoryOverview: React.FC<RepositoryOverviewProps> = ({
  onAnalyzePR,
  onOpenGraph,
  onOpenSearch,
  onOpenRecommendations,
  onOpenCitation,
  repository,
  apiBase = 'http://localhost:8000/api',
}) => {
  const recommendationsQuery = useQuery({
    queryKey: ['overview-recommendations', repository.id, apiBase],
    queryFn: async () => {
      const response = await fetch(`${apiBase}/repos/${repository.id}/recommendations?k=3`);
      if (!response.ok) throw new Error(`Recommendations unavailable (HTTP ${response.status}).`);
      return (await response.json()) as {
        recommendations: Array<{ id: number; category?: string; title: string; description: string; symbol_id?: number }>;
      };
    },
    retry: false,
  });
  const topRecommendations = React.useMemo(() => {
    const pastelColors = ['var(--beige)', 'var(--pastel-blue)', 'var(--pastel-pink)'];
    const fallbackCategories = ['HIGH CENTRALITY', 'COUPLING HOTSPOT', 'TEST COVERAGE GAP'];

    return (recommendationsQuery.data?.recommendations ?? []).map((item, idx) => ({
      num: `0${idx + 1}`,
      numColor: pastelColors[idx] || 'var(--beige)',
      tag: item.category ? item.category.replace(/_/g, ' ') : fallbackCategories[idx],
      title: item.title,
      desc: item.description,
      symbolId: item.symbol_id,
      action: idx === 0 ? 'Inspect symbol' : idx === 1 ? 'Explore dependency chain' : 'Review missing tests',
      onClick: () => {
        if (idx === 2) {
          onAnalyzePR();
        } else {
          onOpenGraph(item.symbol_id || (idx === 0 ? 101 : 204));
        }
      },
    }));
  }, [onAnalyzePR, onOpenGraph, recommendationsQuery.data]);

  return (
    <div className="reposcope-overview-screen">
      {/* Page Title & Primary Action */}
      <div className="reposcope-page-header">
        <div>
          <h1 className="reposcope-page-title">Your codebase, in focus.</h1>
          <p className="reposcope-page-subtitle">
            A living map of your architecture. A clearer path to your next change.
          </p>
        </div>
        <button
          type="button"
          className="reposcope-primary-action-btn"
          onClick={onAnalyzePR}
          title="Open PR Impact analysis for incoming pull requests"
        >
          <Plus size={16} strokeWidth={2.2} />
          <span>Analyze pull request</span>
        </button>
      </div>

      {/* Telemetry Section */}
      <section className="reposcope-telemetry-section" aria-labelledby="telemetry-heading">
        <div className="reposcope-telemetry-header">
          <span id="telemetry-heading" className="reposcope-telemetry-title">
            REPOSITORY TELEMETRY
          </span>
          <span className="reposcope-telemetry-meta">
            main ↓ · TypeScript 78% / Python 22%
          </span>
        </div>

        <div className="reposcope-telemetry-grid">
          {/* Card 1: Beige (Interactive -> Search) */}
          <div
            className="reposcope-telemetry-card reposcope-telemetry-card--beige"
            onClick={() => onOpenSearch()}
            style={{ cursor: 'pointer' }}
            title="Click to search indexed symbols"
            role="button"
            tabIndex={0}
          >
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">Indexed symbols</span>
              <span className="reposcope-telemetry-card__idx">01</span>
            </div>
            <div className="reposcope-telemetry-card__value">{repository.symbol_count ?? '—'}</div>
            <div className="reposcope-telemetry-card__sub">Across {repository.file_count ?? '—'} source files ↗</div>
          </div>

          {/* Card 2: Pastel Blue (Interactive -> Graph) */}
          <div
            className="reposcope-telemetry-card reposcope-telemetry-card--blue"
            onClick={() => onOpenGraph()}
            style={{ cursor: 'pointer' }}
            title="Click to explore AST dependency graph"
            role="button"
            tabIndex={0}
          >
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">AST call edges</span>
              <span className="reposcope-telemetry-card__idx">02</span>
            </div>
            <div className="reposcope-telemetry-card__value">—</div>
            <div className="reposcope-telemetry-card__sub">Graph metrics are calculated from indexed edges</div>
          </div>

          {/* Card 3: Pastel Pink (Interactive -> PR Impact) */}
          <div
            className="reposcope-telemetry-card reposcope-telemetry-card--pink"
            onClick={onAnalyzePR}
            style={{ cursor: 'pointer' }}
            title="Click to review PR blast radius"
            role="button"
            tabIndex={0}
          >
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">PR blast radius</span>
              <span className="reposcope-telemetry-card__idx">03</span>
            </div>
            <div className="reposcope-telemetry-card__value">—</div>
            <div className="reposcope-telemetry-card__sub">No PR analysis history available</div>
          </div>

          {/* Card 4: Pastel Green */}
          <div
            className="reposcope-telemetry-card reposcope-telemetry-card--green"
            onClick={onOpenRecommendations}
            style={{ cursor: 'pointer' }}
            title="Click to view all health recommendations"
            role="button"
            tabIndex={0}
          >
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">Pipeline health</span>
              <span className="reposcope-telemetry-card__idx">04</span>
            </div>
            <div className="reposcope-telemetry-card__value reposcope-telemetry-card__value--text">
              {repository.status === 'ready' ? 'Ready' : repository.status}
            </div>
            <div className="reposcope-telemetry-card__sub">Based on repository index status</div>
          </div>
        </div>
      </section>

      {/* Middle Row: Architecture Map & Assistant */}
      <div className="reposcope-overview-middle-row">
        <ArchitectureMap
          repoId={repository.id}
          apiBase={apiBase}
          onOpenFullGraph={() => onOpenGraph()}
          onSelectModule={(mod) => {
            console.log('Selected architecture module:', mod);
          }}
          onInspectSymbols={(mod) => onOpenSearch(mod)}
          onInspectSymbolDetail={(symId) => onOpenGraph(symId)}
        />
        <ArchitectureAssistant
          onCitationClick={(path, range) => {
            if (onOpenCitation) {
              onOpenCitation(path, range);
            } else {
              onOpenGraph(101);
            }
          }}
        />
      </div>

      {/* Bottom Row: Recommended Next Moves */}
      <section className="reposcope-recommendations-section" aria-labelledby="recommendations-heading">
        <div className="reposcope-section-header">
          <div>
            <h2 id="recommendations-heading" className="reposcope-section-title">
              Recommended next moves
            </h2>
            <p className="reposcope-section-subtitle">
              Prioritized by graph centrality and test coverage.
            </p>
          </div>
          <button
            type="button"
            className="reposcope-inline-link-btn"
            onClick={onOpenRecommendations}
          >
            <span>View all recommendations</span>
            <ExternalLink size={13} strokeWidth={1.75} />
          </button>
        </div>

        <div className="reposcope-recommendations-grid">
          {topRecommendations.length === 0 ? (
            <div className="reposcope-content-state">
              No recommendations are available for this repository.
            </div>
          ) : topRecommendations.map((rec) => (
            <div key={rec.num} className="reposcope-rec-card">
              <div className="reposcope-rec-card__top">
                <span
                  className="reposcope-rec-card__num"
                  style={{ backgroundColor: rec.numColor }}
                >
                  {rec.num}
                </span>
                <span className="reposcope-rec-card__tag">{rec.tag}</span>
              </div>

              <h3 className="reposcope-rec-card__title">{rec.title}</h3>
              <p className="reposcope-rec-card__desc">{rec.desc}</p>

              <button
                type="button"
                className="reposcope-rec-card__action"
                onClick={rec.onClick}
              >
                <span>{rec.action}</span>
                <ExternalLink size={12} strokeWidth={1.75} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default RepositoryOverview;
