import React, { useState } from 'react';
import { ChevronDown, ExternalLink } from 'lucide-react';

interface ArchitectureMapProps {
  onOpenFullGraph?: () => void;
  onSelectModule?: (moduleName: string) => void;
}

export const ArchitectureMap: React.FC<ArchitectureMapProps> = ({
  onOpenFullGraph,
  onSelectModule,
}) => {
  const [selectedModule, setSelectedModule] = useState<string | null>('Billing service');

  const modules = [
    {
      id: 'api-gateway',
      name: 'API gateway',
      meta: '18 endpoints',
      color: 'var(--beige)',
      x: 35,
      y: 95,
      width: 140,
      height: 60,
    },
    {
      id: 'auth',
      name: 'Authentication',
      meta: '42 symbols',
      color: 'var(--pastel-blue)',
      x: 235,
      y: 25,
      width: 145,
      height: 60,
    },
    {
      id: 'billing',
      name: 'Billing service',
      meta: '128 symbols · hotspot',
      color: 'var(--pastel-pink)',
      x: 235,
      y: 100,
      width: 155,
      height: 60,
    },
    {
      id: 'data-layer',
      name: 'Data layer',
      meta: '86 symbols',
      color: 'var(--pastel-green)',
      x: 235,
      y: 175,
      width: 145,
      height: 60,
    },
    {
      id: 'notifications',
      name: 'Notifications',
      meta: '34 symbols',
      color: '#FFFFFF',
      x: 440,
      y: 40,
      width: 145,
      height: 60,
    },
    {
      id: 'payment-provider',
      name: 'Payment provider',
      meta: '12 symbols',
      color: '#FFFFFF',
      x: 440,
      y: 140,
      width: 155,
      height: 60,
    },
  ];

  // Bezier curve connector generator
  const curves = [
    // API Gateway (right 175, 125) -> Authentication (left 235, 55)
    { d: 'M 175 125 C 205 125, 205 55, 235 55' },
    // API Gateway (right 175, 125) -> Billing service (left 235, 130)
    { d: 'M 175 125 C 205 125, 205 130, 235 130' },
    // API Gateway (right 175, 125) -> Data layer (left 235, 205)
    { d: 'M 175 125 C 205 125, 205 205, 235 205' },
    // Authentication (right 380, 55) -> Notifications (left 440, 70)
    { d: 'M 380 55 C 410 55, 410 70, 440 70' },
    // Billing service (right 390, 130) -> Payment provider (left 440, 170)
    { d: 'M 390 130 C 415 130, 415 170, 440 170' },
    // Data layer (right 380, 205) -> Payment provider (left 440, 170)
    { d: 'M 380 205 C 415 205, 415 170, 440 170' },
  ];

  return (
    <div className="reposcope-arch-card">
      {/* Header */}
      <div className="reposcope-arch-card__header">
        <div>
          <h2 className="reposcope-arch-card__title">Architecture map</h2>
          <p className="reposcope-arch-card__subtitle">
            Explore the shape of your system.
          </p>
        </div>
        <button type="button" className="reposcope-arch-card__view-btn">
          <span>Module view</span>
          <ChevronDown size={13} strokeWidth={2} />
        </button>
      </div>

      {/* Interactive Map Canvas */}
      <div className="reposcope-arch-card__canvas-wrap">
        <svg
          viewBox="0 0 630 260"
          className="reposcope-arch-card__svg"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Dependency Curves */}
          <g className="reposcope-arch-card__edges">
            {curves.map((curve, idx) => (
              <path
                key={idx}
                d={curve.d}
                fill="none"
                stroke="#94968F"
                strokeWidth="1.25"
                strokeLinecap="round"
              />
            ))}
          </g>

          {/* Module Nodes */}
          {modules.map((m) => {
            const isSelected = selectedModule === m.name;
            return (
              <g
                key={m.id}
                className="reposcope-arch-card__node-group"
                onClick={() => {
                  setSelectedModule(m.name);
                  onSelectModule?.(m.name);
                }}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  x={m.x}
                  y={m.y}
                  width={m.width}
                  height={m.height}
                  fill={m.color}
                  stroke={isSelected ? 'var(--ink)' : 'var(--border)'}
                  strokeWidth={isSelected ? '2' : '1'}
                />
                <text
                  x={m.x + 12}
                  y={m.y + 24}
                  fontFamily="var(--font-sans)"
                  fontSize="12.5"
                  fontWeight="600"
                  fill="var(--ink)"
                >
                  {m.name}
                </text>
                <text
                  x={m.x + 12}
                  y={m.y + 44}
                  fontFamily="var(--font-sans)"
                  fontSize="10.5"
                  fontWeight="400"
                  fill="var(--muted)"
                >
                  {m.meta}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend & Action Footer */}
      <div className="reposcope-arch-card__footer">
        <div className="reposcope-arch-card__legend">
          <div className="reposcope-arch-card__legend-item">
            <span className="reposcope-arch-card__legend-dot" />
            <span>Module</span>
          </div>
          <div className="reposcope-arch-card__legend-item">
            <span className="reposcope-arch-card__legend-line" />
            <span>Call dependency</span>
          </div>
        </div>

        <button
          type="button"
          className="reposcope-arch-card__full-link"
          onClick={onOpenFullGraph}
        >
          <span>Open full graph</span>
          <ExternalLink size={13} strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
};
export default ArchitectureMap;

