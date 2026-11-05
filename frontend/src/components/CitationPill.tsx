import { isEvidenceId } from '../types/evidence';
import './CitationDrawer.css';
interface Props {
  evidenceId: string;
  onSelect: (id: string) => void;
  expanded?: boolean;
  controls?: string;
}
export default function CitationPill({ evidenceId, onSelect, expanded = false, controls }: Props) {
  return <button type="button" className="citation-pill" disabled={!isEvidenceId(evidenceId)}
    aria-label={`Open citation ${evidenceId}`} aria-haspopup="dialog"
    aria-expanded={expanded} aria-controls={controls}
    onClick={event => { event.currentTarget.focus(); onSelect(evidenceId); }}>[{evidenceId}]</button>;
}
import React, { useState, useRef, useEffect } from 'react';
import type { CitationEvidence } from '../types/chat';
import './CitationPill.css';

interface Props {
  evidenceId: string;
  evidence?: CitationEvidence;
  onSelectSymbol?: (symbolId: number) => void;
}

export const CitationPill: React.FC<Props> = ({
  evidenceId,
  evidence,
  onSelectSymbol,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  const copyPath = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (evidence) {
      void navigator.clipboard.writeText(
        `${evidence.file_path}:${evidence.start_line}-${evidence.end_line}`,
      );
    }
  };

  return (
    <span
      className="citation-pill-container"
      ref={containerRef}
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        className={`citation-pill ${isOpen ? 'citation-pill--active' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-label={`Citation [${evidenceId}] - ${evidence ? evidence.name : 'view source chunk'}`}
        title={evidence ? `${evidence.name} (${evidence.file_path}:${evidence.start_line})` : `Citation [${evidenceId}]`}
      >
        <span>[{evidenceId}]</span>
        <span className="citation-pill__arrow" aria-hidden="true">
          ▼
        </span>
      </button>

      {isOpen && (
        <div
          className="citation-popover"
          role="region"
          aria-label={`Citation details for [${evidenceId}]`}
        >
          <div className="citation-popover__header">
            <div className="citation-popover__title-wrap">
              <span className="citation-popover__id-badge">[{evidenceId}]</span>
              {evidence?.kind && (
                <span className="citation-popover__kind-badge">
                  {evidence.kind}
                </span>
              )}
            </div>

            <button
              type="button"
              className="citation-popover__close-btn"
              onClick={() => setIsOpen(false)}
              aria-label="Close citation details"
            >
              ✕
            </button>
          </div>

          {evidence ? (
            <>
              <div className="citation-popover__symbol-name">
                {evidence.name}
              </div>

              <div className="citation-popover__file-meta">
                <span>
                  {evidence.file_path}:{evidence.start_line}-{evidence.end_line}
                </span>
                {evidence.fused_score !== undefined && evidence.fused_score !== null && (
                  <span className="citation-popover__score">
                    SCORE: {evidence.fused_score.toFixed(3)}
                  </span>
                )}
              </div>

              <pre className="citation-popover__snippet">
                <code>{evidence.snippet}</code>
              </pre>

              <div className="citation-popover__actions">
                <button
                  type="button"
                  className="citation-popover__action-btn"
                  onClick={copyPath}
                  title="Copy file path and line numbers"
                >
                  COPY PATH
                </button>

                {evidence.symbol_id && onSelectSymbol && (
                  <button
                    type="button"
                    className="citation-popover__action-btn"
                    onClick={() => {
                      setIsOpen(false);
                      onSelectSymbol(evidence.symbol_id!);
                    }}
                  >
                    INSPECT SYMBOL →
                  </button>
                )}
              </div>
            </>
          ) : (
            <div>
              <p style={{ fontSize: '0.8rem', color: '#64748b', margin: '4px 0' }}>
                Source chunk <strong>[{evidenceId}]</strong> was referenced in context.
              </p>
            </div>
          )}
        </div>
      )}
    </span>
  );
};

export default CitationPill;
