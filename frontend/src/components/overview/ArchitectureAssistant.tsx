import React, { useState } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

interface ArchitectureAssistantProps {
  onCitationClick?: (filePath: string, range: string) => void;
  apiBase?: string;
  repoId?: number;
}

interface QAPair {
  question: string;
  answer: string;
  citation: {
    index: string;
    path: string;
    range: string;
    confidence: string;
  };
}

export const ArchitectureAssistant: React.FC<ArchitectureAssistantProps> = ({
  onCitationClick,
  apiBase = 'http://localhost:8000/api',
  repoId = 1,
}) => {
  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<QAPair[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;

    const newQ = question.trim();
    setQuestion('');
    setIsLoading(true);

    try {
      setError(null);
      const response = await fetch(`${apiBase}/repos/${repoId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: newQ }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(
          data?.error?.message ?? data?.detail ?? `Request failed (HTTP ${response.status}).`,
        );
      }
      const data = await response.json();
      const primaryCitation = data.evidence?.[0];
      if (!primaryCitation) {
        throw new Error('The server returned no evidence for this answer.');
      }

      setHistory((prev) => [
        ...prev,
        {
          question: newQ,
          answer: data.answer,
          citation: {
            index: `0${prev.length + 1}`,
            path: primaryCitation.file_path,
            range: `L${primaryCitation.start_line}-${primaryCitation.end_line}`,
            confidence: '—',
          },
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to answer the question.');
    } finally {
      setIsLoading(false);
    }
  };

  const activeEntry = history[history.length - 1];

  return (
    <div className="reposcope-assistant-panel">
      <div>
        <span className="reposcope-assistant-panel__tag">ASK REPOSCOPE</span>
        <h2 className="reposcope-assistant-panel__title">Architecture, explained.</h2>

        {/* Question bubble */}
        <p className="reposcope-assistant-panel__prompt">
          {activeEntry?.question ?? 'Ask a question about the indexed repository.'}
        </p>

        {/* Grounded Answer */}
        <p className="reposcope-assistant-panel__answer">
          {(activeEntry?.answer ?? 'Answers appear here after a live repository query.').split(/(authorizePayment\(\)|createCheckout\(\)|issueRefund\(\)|verifySessionToken\(\))/g).map((part, i) => {
            if (
              part === 'authorizePayment()' ||
              part === 'createCheckout()' ||
              part === 'issueRefund()' ||
              part === 'verifySessionToken()'
            ) {
              return (
                <code key={i} className="reposcope-assistant-panel__inline-code">
                  {part}
                </code>
              );
            }
            return <React.Fragment key={i}>{part}</React.Fragment>;
          })}
        </p>

        {/* Source Citation */}
        <div
          className="reposcope-assistant-panel__citation"
          onClick={() =>
            activeEntry && onCitationClick?.(activeEntry.citation.path, activeEntry.citation.range)
          }
          role="button"
          tabIndex={0}
          title="Click to view source location in code viewer"
        >
          <div className="reposcope-assistant-panel__citation-path">
            <span className="reposcope-assistant-panel__citation-idx">
              {activeEntry.citation.index}
            </span>
            <span>{activeEntry?.citation.path ?? 'No evidence selected'}</span>
          </div>
          <div className="reposcope-assistant-panel__citation-meta">
            {activeEntry?.citation.range ?? '—'} · {activeEntry?.citation.confidence ?? '—'} confidence
          </div>
          {error && <p role="alert" className="reposcope-content-state">{error}</p>}
        </div>
      </div>

      {/* Input box */}
      <form onSubmit={handleSubmit} className="reposcope-assistant-panel__form">
        <input
          type="text"
          className="reposcope-assistant-panel__input"
          placeholder={isLoading ? 'Analyzing AST dependencies...' : 'Ask about this codebase...'}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isLoading}
        />
        <button
          type="submit"
          className="reposcope-assistant-panel__submit"
          aria-label="Send question"
          disabled={isLoading || !question.trim()}
        >
          {isLoading ? (
            <Loader2 size={16} className="reposcope-spin" />
          ) : (
            <ArrowUp size={16} strokeWidth={2.2} />
          )}
        </button>
      </form>
    </div>
  );
};

export default ArchitectureAssistant;
