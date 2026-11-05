import { useState } from 'react';
import CitationInspector from './CitationInspector';
import { citationPreviewPack } from '../fixtures/citations';
import './CitationDrawer.css';

/** Additive offline demo. This does not claim to implement live chat/streaming. */
export default function CitationPreview() {
  const [expanded, setExpanded] = useState(false);
  return <section className="citation-preview" aria-labelledby="citation-preview-heading">
    <div className="citation-preview__top">
      <div><h2 id="citation-preview-heading">CITATION DRAWER — OFFLINE PREVIEW</h2>
        <p>Synthetic evidence only. Your existing dashboard and API features are unchanged.</p></div>
      <button type="button" className="citation-preview__toggle" aria-expanded={expanded}
        aria-controls="citation-preview-body" onClick={() => setExpanded(value => !value)}>
        {expanded ? 'Hide citation preview' : 'Show citation preview'}
      </button>
    </div>
    {expanded && <div id="citation-preview-body" className="citation-preview__body">
      <CitationInspector answerId="synthetic-answer-1" pack={citationPreviewPack} isFixture>
        {cite => <p>Example answer: the handler delegates to the user service {cite('E1')}.
          The service constructs a User instance {cite('E2')}.
          Click either pill to inspect its stored source and provenance.</p>}
      </CitationInspector>
    </div>}
  </section>;
}
