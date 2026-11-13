import React from 'react';
import { Plus, ExternalLink } from 'lucide-react';
import ArchitectureMap from './ArchitectureMap';
import ArchitectureAssistant from './ArchitectureAssistant';

interface RepositoryOverviewProps {
  onAnalyzePR: () => void;
  onOpenGraph: () => void;
  onOpenRecommendations: () => void;
}

export const RepositoryOverview: React.FC<RepositoryOverviewProps> = ({
  onAnalyzePR,
  onOpenGraph,
  onOpenRecommendations,
}) => {
  const recommendations = [
    {
      num: '01',
      numColor: 'var(--beige)',
      tag: 'HIGH CENTRALITY',
      title: 'Protect the billing core',
      desc: '128 symbols depend on BillingService. Add contract tests before the next refactor.',
      action: 'Inspect symbol',
      onClick: onOpenGraph,
    },
    {
      num: '02',
      numColor: 'var(--pastel-blue)',
      tag: 'COUPLING HOTSPOT',
      title: 'Untangle the auth boundary',
      desc: '7 circular dependencies connect auth and users. Introduce a shared interface.',
      action: 'Explore dependency chain',
      onClick: onOpenGraph,
    },
    {
      num: '03',
      numColor: 'var(--pastel-pink)',
      tag: 'TEST COVERAGE GAP',
      title: 'Cover the refund path',
      desc: '3 impacted routes have no integration tests. Start with POST /api/refunds.',
      action: 'Review missing tests',
      onClick: onAnalyzePR,
    },
  ];

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
          {/* Card 1: Beige */}
          <div className="reposcope-telemetry-card reposcope-telemetry-card--beige">
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">Indexed symbols</span>
              <span className="reposcope-telemetry-card__idx">01</span>
            </div>
            <div className="reposcope-telemetry-card__value">24,891</div>
            <div className="reposcope-telemetry-card__sub">Across 1,204 source files</div>
          </div>

          {/* Card 2: Pastel Blue */}
          <div className="reposcope-telemetry-card reposcope-telemetry-card--blue">
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">AST call edges</span>
              <span className="reposcope-telemetry-card__idx">02</span>
            </div>
            <div className="reposcope-telemetry-card__value">86,402</div>
            <div className="reposcope-telemetry-card__sub">3.5 dependencies per symbol</div>
          </div>

          {/* Card 3: Pastel Pink */}
          <div className="reposcope-telemetry-card reposcope-telemetry-card--pink">
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">PR blast radius</span>
              <span className="reposcope-telemetry-card__idx">03</span>
            </div>
            <div className="reposcope-telemetry-card__value">12.8%</div>
            <div className="reposcope-telemetry-card__sub">Median · last 30 pull requests</div>
          </div>

          {/* Card 4: Pastel Green */}
          <div className="reposcope-telemetry-card reposcope-telemetry-card--green">
            <div className="reposcope-telemetry-card__header">
              <span className="reposcope-telemetry-card__label">Pipeline health</span>
              <span className="reposcope-telemetry-card__idx">04</span>
            </div>
            <div className="reposcope-telemetry-card__value reposcope-telemetry-card__value--text">
              All systems go
            </div>
            <div className="reposcope-telemetry-card__sub">4 / 4 ingestion stages complete</div>
          </div>
        </div>
      </section>

      {/* Middle Row: Architecture Map & Assistant */}
      <div className="reposcope-overview-middle-row">
        <ArchitectureMap
          onOpenFullGraph={onOpenGraph}
          onSelectModule={(mod) => {
            console.log('Selected architecture module:', mod);
          }}
        />
        <ArchitectureAssistant
          onCitationClick={() => {
            onOpenGraph();
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
          {recommendations.map((rec) => (
            <div key={rec.num} className="reposcope-recommendation-card">
              <div>
                <div className="reposcope-recommendation-card__top">
                  <span
                    className="reposcope-recommendation-card__num"
                    style={{ backgroundColor: rec.numColor }}
                  >
                    {rec.num}
                  </span>
                  <span className="reposcope-recommendation-card__tag">
                    {rec.tag}
                  </span>
                </div>
                <h3 className="reposcope-recommendation-card__title">
                  {rec.title}
                </h3>
                <p className="reposcope-recommendation-card__desc">
                  {rec.desc}
                </p>
              </div>

              <button
                type="button"
                className="reposcope-recommendation-card__action"
                onClick={rec.onClick}
              >
                <span>{rec.action}</span>
                <ExternalLink size={13} strokeWidth={1.75} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
export default RepositoryOverview;

