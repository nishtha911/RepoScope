import { Command, Search } from 'lucide-react'

interface AppHeaderProps {
  title: string
}

export function AppHeader({ title }: AppHeaderProps) {
  return (
    <header className="topbar">
      <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{title}</strong></div>
      <label className="global-search">
        <Search size={15} aria-hidden="true" />
        <input aria-label="Search workspace" placeholder="Find a symbol or file..." />
        <kbd><Command size={11} /> K</kbd>
      </label>
      <div className="avatar" aria-label="Local user">R</div>
    </header>
  )
}