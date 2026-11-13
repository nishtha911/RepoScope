import React from 'react';
import {
  LayoutGrid,
  Search,
  GitBranch,
  GitPullRequest,
  MessageSquare,
  Sparkles,
  Settings,
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
  prCount?: number;
  repository?: Repository;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  prCount,
  repository,
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
      badge: prCount,
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
        <div className="reposcope-sidebar__repo-box">
          <div className="reposcope-sidebar__repo-info">
            <span className="reposcope-sidebar__repo-name">{repository?.name ?? 'Repository'}</span>
            <span className="reposcope-sidebar__repo-visibility">
              {repository?.status ?? 'not connected'}
            </span>
          </div>
          <ChevronDown size={14} className="reposcope-sidebar__repo-chevron" />
        </div>

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
                  {item.badge !== undefined && (
                    <span className="reposcope-sidebar__nav-badge">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="reposcope-sidebar__bottom">
        {/* Index Status Card */}
        <div className="reposcope-sidebar__index-card">
          <div className="reposcope-sidebar__index-header">
            <span className="reposcope-sidebar__status-dot" aria-hidden="true" />
            <span className="reposcope-sidebar__index-status">
              {repository?.status === 'ready' ? 'Index up to date' : `Index ${repository?.status ?? 'unavailable'}`}
            </span>
          </div>
          <p className="reposcope-sidebar__index-synced">
            {repository?.head_sha ? `Commit ${repository.head_sha.slice(0, 7)}` : 'No indexed snapshot'}
          </p>
          <div className="reposcope-sidebar__index-commit">
            <span>{repository ? `${repository.default_branch} · ${repository.head_sha?.slice(0, 7) ?? 'pending'}` : 'No repository'}</span>
            <div className="reposcope-sidebar__index-bar" />
          </div>
        </div>

        {/* Workspace Settings */}
        <button
          type="button"
          className="reposcope-sidebar__settings-btn"
          onClick={() => onTabChange('OVERVIEW')}
        >
          <Settings size={15} strokeWidth={1.75} />
          <span>Workspace settings</span>
        </button>

        {/* Org Label */}
        <div className="reposcope-sidebar__org-label">
          {repository?.name ?? 'REPOSITORY WORKSPACE'}
        </div>
      </div>
    </aside>
  );
};
export default Sidebar;
