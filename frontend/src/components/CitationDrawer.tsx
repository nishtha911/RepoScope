import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import CodeViewer from './CodeViewer';
import { parseEvidencePack } from '../types/evidence';
import type { CitationSelection, EvidenceEntry } from '../types/evidence';
import './CitationDrawer.css';

interface Props {
  selection: CitationSelection | null;
  onClose: () => void;
  dialogId?: string;
  isFixture?: boolean;
}
export default function CitationDrawer({ selection, onClose, dialogId, isFixture = false }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const heading = useId();
  const generatedId = useId();
  const open = selection !== null;
  useEffect(() => {
    const element = dialog.current;
    if (!open || !element) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    closeButton.current?.focus();
    return () => {
      if (element.open) element.close();
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  if (!selection) return null;
  let entry: EvidenceEntry | undefined;
  let problem = '';
  try {
    const pack = parseEvidencePack(selection.pack);
    entry = pack.entries.find(item => item.source.evidence_id === selection.evidenceId);
    if (!entry) problem = 'This citation is not present in this answer’s Evidence Pack. No fallback source is shown.';
  } catch {
    problem = 'The Evidence Pack is invalid or inconsistent. Source display is blocked.';
  }
  const pack = selection.pack;
  return createPortal(
    <dialog ref={dialog} id={dialogId ?? generatedId} className="citation-drawer"
      aria-labelledby={heading} aria-modal="true" onCancel={event => { event.preventDefault(); onClose(); }}
      onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="citation-drawer__panel">
        <header className="citation-drawer__header">
          <div><p className="citation-drawer__eyebrow">SOURCE EVIDENCE</p>
            <h2 id={heading}>Citation [{selection.evidenceId}]</h2></div>
          <button ref={closeButton} type="button" onClick={onClose} className="citation-drawer__close"
            aria-label="Close citation drawer">Close ×</button>
        </header>
        {isFixture && <p className="citation-drawer__notice">SYNTHETIC FIXTURE — not live repository or chat data.</p>}
        {problem ? <p role="alert" className="citation-drawer__notice">{problem}</p> : entry && <>
          <dl className="citation-drawer__metadata">
            <dt>File</dt><dd>{entry.source.file_path}</dd>
            <dt>Cited lines</dt><dd>{entry.source.start_line}–{entry.source.end_line} (inclusive)</dd>
            <dt>Symbol</dt><dd>{entry.qualname ?? entry.name} · {entry.kind}</dd>
            <dt>Repository / snapshot</dt><dd>{pack.repository_id} / {pack.snapshot_id}</dd>
            <dt>Commit</dt><dd>{pack.commit_sha ?? 'Not supplied'}</dd>
            <dt>Answer</dt><dd>{selection.answerId}</dd>
            <dt>Retrieval origin</dt><dd>{entry.origin === 'seed' ? 'Direct retrieval seed' : 'Graph-expanded context'}</dd>
            <dt>Fused retrieval score</dt><dd>{entry.fused_score === null ? 'Not supplied' : String(entry.fused_score)} (not a confidence percentage)</dd>
          </dl>
          {entry.signature !== null && <><h3>Stored signature</h3><pre className="citation-drawer__signature">{entry.signature}</pre></>}
          <h3>Relationship evidence</h3>
          {entry.paths.length === 0 ? <p>Direct retrieval; no graph relationship path. Path confidence: not applicable.</p> : <>
            <p>Confidence belongs to the whole path, not each individual edge or the answer’s correctness.</p>
            <ol className="citation-drawer__paths">{entry.paths.map((path, index) => <li key={index}>
              <h4>Path {index + 1}: {path.edge_kinds.join(' → ')}</h4>
              <p>Path confidence: {String(path.confidence)} ({Number((path.confidence * 100).toFixed(2))}%)</p>
              <p>Seed symbol: {path.seed_symbol_id}</p>
              <ol>{path.edge_ids.map((edgeId, hop) => <li key={`${hop}-${edgeId}`}>
                {path.symbol_ids[hop]} {path.directions[hop] === 'incoming' ? '←' : '→'} {path.symbol_ids[hop + 1]}
                {' · '}{path.edge_kinds[hop]} · {path.directions[hop]} traversal · stored edge #{edgeId}
              </li>)}</ol>
            </li>)}</ol>
          </>}
          <h3>Cited source excerpt</h3>
          <p>This is the source stored with this Evidence Pack, not a freshly fetched full file.</p>
          <CodeViewer filePath={entry.source.file_path}
            code={entry.source.text.replace(/\r\n?/g, '\n').replace(/\n$/, '')}
            startLine={entry.source.start_line} highlightStart={entry.source.start_line}
            highlightEnd={entry.source.end_line} isFixture={isFixture} />
          {(pack.truncated || pack.gaps.length > 0) && <details className="citation-drawer__gaps">
            <summary>Evidence gaps and limits ({pack.gaps.length})</summary>
            {pack.truncated && <p>Context truncated: {pack.truncation_reasons.join(', ')}</p>}
            <ul>{pack.gaps.map((gap, index) => <li key={index}>[GAP] {gap}</li>)}</ul>
          </details>}
        </>}
      </section>
    </dialog>, document.body,
  );
}
