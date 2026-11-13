import type { FC } from 'react';
import './Footer.css';

export type Tab = 'OVERVIEW' | 'GRAPH' | 'PR_IMPACT' | 'RAG' | 'RECOMMENDATIONS';

interface Props {
  offlinePreview: boolean;
  apiHealth?: { status: string; v: string };
  isHealthError?: boolean;
  // kept for compatibility — footer no longer renders navigation
  activeTab?: Tab;
  onTabChange?: (tab: Tab) => void;
}

const Footer: FC<Props> = ({ offlinePreview, apiHealth, isHealthError = false }) => {
  const statusDot = offlinePreview
    ? 'footer__dot footer__dot--offline'
    : isHealthError
      ? 'footer__dot footer__dot--error'
      : 'footer__dot footer__dot--online';

  const statusText = offlinePreview
    ? 'Offline Preview'
    : isHealthError
      ? 'Server Unreachable'
      : `API v${apiHealth?.v ?? '1.0'} · Connected`;

  return (
    <footer className="site-footer" role="contentinfo">
      <div className="site-footer__inner">
        {/* Left — Brand */}
        <div className="site-footer__brand">
          <span className="site-footer__logo">REPOSCOPE</span>
          <span className="site-footer__copy">© 2026 · MIT License</span>
        </div>

        {/* Right — Status */}
        <div className="site-footer__status">
          <span className={statusDot} aria-hidden="true" />
          <span className="site-footer__status-text">{statusText}</span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
