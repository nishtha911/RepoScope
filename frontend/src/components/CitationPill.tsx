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
