import React from 'react';
import {
  LayoutGrid,
  Search,
  GitBranch,
  GitPullRequest,
  MessageSquare,
  Sparkles,
  ChevronDown,
} from 'lucide-react';
import type { Repository } from '../../api/repositories';

export type NavTab =
  | 'OVERVIEW'
  | 'SEARCH'
  | 'GRAPH'
  | 'PR_IMPACT'
  | 'RAG'
  | 'RECOMMENDATIONS';

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  repository: Repository;
  onChangeRepository: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  repository,
  onChangeRepository,
}) => {
  const navItems = [
    {
      id: 'OVERVIEW' as NavTab,
      label: 'Overview',
      icon: LayoutGrid,
    },
    {
      id: 'SEARCH' as NavTab,
      label: 'Code search',
      icon: Search,
    },
    {
      id: 'GRAPH' as NavTab,
      label: 'Dependency graph',
      icon: GitBranch,
    },
    {
      id: 'PR_IMPACT' as NavTab,
      label: 'PR impact',
      icon: GitPullRequest,
    },
    {
      id: 'RAG' as NavTab,
      label: 'Ask RepoScope',
      icon: MessageSquare,
    },
    {
      id: 'RECOMMENDATIONS' as NavTab,
      label: 'Recommendations',
      icon: Sparkles,
    },
  ];

  return (
    <aside className="reposcope-sidebar" aria-label="Main Navigation">
      <div className="reposcope-sidebar__top">
        {/* Brand Header */}
        <div className="reposcope-sidebar__brand">
          <div className="reposcope-sidebar__brand-logo-wrap">
            <img
              src="/image.png"
              alt="RepoScope Logo"
              className="reposcope-sidebar__brand-logo"
            />
          </div>
          <div className="reposcope-sidebar__brand-text">
            <span className="reposcope-sidebar__brand-title">RepoScope</span>
            <span className="reposcope-sidebar__brand-subtitle">
              CODEBASE INTELLIGENCE
            </span>
          </div>
        </div>

        {/* Repository Selector */}
        <button
          type="button"
          className="reposcope-sidebar__repo-box"
          onClick={onChangeRepository}
          aria-label="Change repository"
        >
          <div className="reposcope-sidebar__repo-info">
            <span className="reposcope-sidebar__repo-name">{repository.name}</span>
            <span className="reposcope-sidebar__repo-visibility">
              {repository.status}
            </span>
          </div>
          <ChevronDown size={14} className="reposcope-sidebar__repo-chevron" />
        </button>

        {/* Workspace Navigation */}
        <div className="reposcope-sidebar__nav-section">
          <span className="reposcope-sidebar__nav-heading">WORKSPACE</span>
          <nav className="reposcope-sidebar__nav-list">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`reposcope-sidebar__nav-item ${
                    isActive ? 'reposcope-sidebar__nav-item--active' : ''
                  }`}
                  onClick={() => onTabChange(item.id)}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon size={16} strokeWidth={1.75} className="reposcope-sidebar__nav-icon" />
                  <span className="reposcope-sidebar__nav-label">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="reposcope-sidebar__bottom">
        {/* Index Status Card */}
        <div className="reposcope-sidebar__index-card" aria-live="polite">
          <div className="reposcope-sidebar__index-header">
            <span
              className={`reposcope-sidebar__status-dot reposcope-sidebar__status-dot--${repository.status}`}
              aria-hidden="true"
            />
            <span className="reposcope-sidebar__index-status">
              {repository.status === 'ready' ? 'Index up to date' : `Index ${repository.status}`}
            </span>
          </div>
          <p className="reposcope-sidebar__index-synced">
            {repository.file_count ?? 0} files · {repository.symbol_count ?? 0} symbols
          </p>
          <div className="reposcope-sidebar__index-commit">
            <span>{repository.default_branch} · {repository.head_sha?.slice(0, 7) ?? 'pending'}</span>
            <div className="reposcope-sidebar__index-bar" />
          </div>
        </div>

        <div className="reposcope-sidebar__org-label">
          LIVE REPOSITORY WORKSPACE
        </div>
      </div>
    </aside>
  );
};
export default Sidebar;

