import { useState } from 'react';

import CodeViewer from './CodeViewer';
import ErrorBoundary from './ErrorBoundary';
import { codePreview } from '../fixtures/codePreview';

export default function CodeViewerDemo() {
  const [showCode, setShowCode] = useState(true);

  return (
    <section
      aria-labelledby="code-viewer-demo-heading"
      style={{
        margin: '24px 32px',
        padding: '24px',
        border: 'var(--border-thin)',
        backgroundColor: '#ffffff',
        color: '#000000',
      }}
    >
      <h2
        id="code-viewer-demo-heading"
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '1.05rem',
          fontWeight: 800,
          letterSpacing: '0.08em',
          marginBottom: '8px',
        }}
      >
        DAY 5 — OFFLINE CODE VIEWER DEMO
      </h2>

      <p
        style={{
          color: 'var(--text-secondary)',
          fontSize: '0.85rem',
          marginBottom: '16px',
        }}
      >
        Local fixture only. This preview does not fetch data from the
        backend or verify repository source.
      </p>

      <button
        type="button"
        className="bauhaus-btn-invert"
        onClick={() => setShowCode((previous) => !previous)}
      >
        {showCode ? 'Show empty state' : 'Show fixture code'}
      </button>

      <ErrorBoundary>
        <CodeViewer
          code={showCode ? codePreview.code : null}
          filePath={codePreview.filePath}
          language={codePreview.language}
          startLine={codePreview.startLine}
          highlightStart={codePreview.highlightStart}
          highlightEnd={codePreview.highlightEnd}
          isFixture
        />
      </ErrorBoundary>
    </section>
  );
}
