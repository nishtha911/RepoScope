import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import type { CitationSelection, EvidencePack } from '../types/evidence';
import CitationPill from './CitationPill';
import CitationDrawer from './CitationDrawer';

interface Props {
  answerId: string;
  pack: EvidencePack;
  isFixture?: boolean;
  children: (renderCitation: (evidenceId: string) => ReactNode) => ReactNode;
}

interface InspectorState {
  answerId: string;
  pack: EvidencePack;
  evidenceId: string | null;
}

/** One instance per answer. Never resolve E1 against a global/latest pack. */
export default function CitationInspector({ answerId, pack, isFixture = false, children }: Props) {
  const [state, setState] = useState<InspectorState>(() => ({
    answerId,
    pack,
    evidenceId: null,
  }));
  const dialogId = useId();

  // Guarded adjustment of this component's own state. React retries rendering
  // before committing children, so a changed scope never displays stale code.
  if (state.answerId !== answerId || state.pack !== pack) {
    setState({ answerId, pack, evidenceId: null });
  }

  const active: CitationSelection | null =
    state.answerId === answerId && state.pack === pack && state.evidenceId !== null
      ? { answerId, pack, evidenceId: state.evidenceId }
      : null;

  return <>
    {children(evidenceId => <CitationPill evidenceId={evidenceId} controls={dialogId}
      expanded={active?.evidenceId === evidenceId}
      onSelect={id => setState({ answerId, pack, evidenceId: id })} />)}
    <CitationDrawer selection={active} dialogId={dialogId} isFixture={isFixture}
      onClose={() => setState({ answerId, pack, evidenceId: null })} />
  </>;
}
