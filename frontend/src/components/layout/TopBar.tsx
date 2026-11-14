import React from 'react';
import { Search, ExternalLink } from 'lucide-react';
import type { NavTab } from './Sidebar';

interface TopBarProps {
  activeTab: NavTab;
  repositoryName: string;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onSearchSubmit: () => void;
  searchLatencyMs?: number | null;
}

export const TopBar: React.FC<TopBarProps> = ({
  activeTab,
  repositoryName,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  searchLatencyMs,
}) => {
  const tabTitles: Record<NavTab, string> = {
    OVERVIEW: 'Overview',
    SEARCH: 'Code search',
    GRAPH: 'Dependency graph',
    PR_IMPACT: 'PR impact',
    RAG: 'Ask RepoScope',
    RECOMMENDATIONS: 'Recommendations',
  };

  const currentTitle = tabTitles[activeTab] || 'Overview';

  return (
    <header className="reposcope-topbar">
      {/* Breadcrumbs */}
      <nav aria-label="Breadcrumbs" className="reposcope-topbar__breadcrumbs">
        <span className="reposcope-topbar__crumb">Workspace</span>
        <span className="reposcope-topbar__separator">/</span>
        <span className="reposcope-topbar__crumb">{repositoryName}</span>
        <span className="reposcope-topbar__separator">/</span>
        <span className="reposcope-topbar__crumb reposcope-topbar__crumb--active">
          {currentTitle}
        </span>
      </nav>

      {/* Right Controls */}
      <div className="reposcope-topbar__actions">
        {/* Search Bar */}
        <div className="reposcope-topbar__search-wrap">
          <Search size={15} strokeWidth={1.75} className="reposcope-topbar__search-icon" />
          <input
            id="header-global-search"
            type="search"
            className="reposcope-topbar__search-input"
            placeholder="Search symbols, endpoints, docs..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onSearchSubmit();
              }
            }}
          />
          {searchLatencyMs !== null && searchLatencyMs !== undefined ? (
            <span className="reposcope-topbar__latency-badge">
              ⚡ {searchLatencyMs}ms
            </span>
          ) : (
            <kbd className="reposcope-topbar__shortcut-badge">⌘ K</kbd>
          )}
        </div>

        {/* Documentation Link */}
        <a
          href="https://github.com/nishtha911/RepoScope/tree/main/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="reposcope-topbar__docs-link"
        >
          <span>Docs</span>
          <ExternalLink size={13} strokeWidth={1.75} />
        </a>

        {/* Organization Badge */}
        <span className="reposcope-topbar__org-badge">LIVE</span>
      </div>
    </header>
  );
};
export default TopBar;
