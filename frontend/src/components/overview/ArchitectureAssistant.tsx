import React, { useState } from 'react';
import { ArrowUp } from 'lucide-react';

interface ArchitectureAssistantProps {
  onCitationClick?: (filePath: string, range: string) => void;
}

export const ArchitectureAssistant: React.FC<ArchitectureAssistantProps> = ({
  onCitationClick,
}) => {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([
    {
      question: 'Where is payment authorization handled?',
      answer:
        'Payment authorization starts in authorizePayment() and calls the Stripe adapter through the billing service.',
      citation: {
        index: '01',
        path: 'src/billing/authorize.ts',
        range: 'L42-78',
        confidence: '98%',
      },
    },
  ]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    const newQ = question.trim();
    setQuestion('');

    // Responsive interaction: add answer grounded with citation
    setHistory((prev) => [
      ...prev,
      {
        question: newQ,
        answer: `Analysis grounded in AST call graph for "${newQ}". Direct references resolve through the core service registry and API routes.`,
        citation: {
          index: `0${prev.length + 1}`,
          path: 'src/api/gateway/router.ts',
          range: 'L14-52',
          confidence: '95%',
        },
      },
    ]);
  };

  const activeEntry = history[history.length - 1];

  return (
    <div className="reposcope-assistant-panel">
      <div>
        <span className="reposcope-assistant-panel__tag">ASK REPOSCOPE</span>
        <h2 className="reposcope-assistant-panel__title">Architecture, explained.</h2>

        {/* Question bubble */}
        <p className="reposcope-assistant-panel__prompt">
          {activeEntry.question}
        </p>

        {/* Grounded Answer */}
        <p className="reposcope-assistant-panel__answer">
          {activeEntry.answer.split('authorizePayment()').map((part, i, arr) => (
            <React.Fragment key={i}>
              {part}
              {i < arr.length - 1 && (
                <code className="reposcope-assistant-panel__inline-code">
                  authorizePayment()
                </code>
              )}
            </React.Fragment>
          ))}
        </p>

        {/* Source Citation */}
        <div
          className="reposcope-assistant-panel__citation"
          onClick={() =>
            onCitationClick?.(
              activeEntry.citation.path,
              activeEntry.citation.range
            )
          }
          role="button"
          tabIndex={0}
        >
          <div className="reposcope-assistant-panel__citation-path">
            <span className="reposcope-assistant-panel__citation-idx">
              {activeEntry.citation.index}
            </span>
            <span>{activeEntry.citation.path}</span>
          </div>
          <div className="reposcope-assistant-panel__citation-meta">
            {activeEntry.citation.range} · {activeEntry.citation.confidence} confidence
          </div>
        </div>
      </div>

      {/* Input box */}
      <form onSubmit={handleSubmit} className="reposcope-assistant-panel__form">
        <input
          type="text"
          className="reposcope-assistant-panel__input"
          placeholder="Ask about this codebase..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          type="submit"
          className="reposcope-assistant-panel__submit"
          aria-label="Send question"
        >
          <ArrowUp size={16} strokeWidth={2.2} />
        </button>
      </form>
    </div>
  );
};
export default ArchitectureAssistant;

