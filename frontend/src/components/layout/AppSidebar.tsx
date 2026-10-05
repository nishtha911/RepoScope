import {
  Activity,
  Boxes,
  GitPullRequest,
  MessageSquareText,
  Search,
} from 'lucide-react'

export type View = 'explorer' | 'search' | 'chat' | 'impact'

const navigation: { id: View; label: string; icon: typeof Boxes }[] = [
  { id: 'explorer', label: 'Explorer', icon: Boxes },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'chat', label: 'Code chat', icon: MessageSquareText },
  { id: 'impact', label: 'PR impact', icon: GitPullRequest },
]

interface AppSidebarProps {
  activeView: View
  onNavigate: (view: View) => void
}

export function AppSidebar({ activeView, onNavigate }: AppSidebarProps) {
  return (
    <aside className="sidebar">
      <a className="brand" href="#workspace" aria-label="RepoScope home">
        <span className="brand-mark"><Activity size={19} strokeWidth={2.5} /></span>
        <span>repo<span className="brand-light">scope</span></span>
      </a>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="side-nav" aria-label="Main navigation">
        {navigation.map(({ id, label, icon: Icon }) => (
          <button
            className={`nav-item ${activeView === id ? 'active' : ''}`}
            key={id}
            onClick={() => onNavigate(id)}
            title={label}
            type="button"
          >
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <span className="connection-dot" />
        <span>Local workspace</span>
      </div>
    </aside>
  )
}