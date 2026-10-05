import { useState } from 'react'
import { AppHeader } from './components/layout/AppHeader'
import { AppSidebar, type View } from './components/layout/AppSidebar'
import { ChatPage } from './features/chat/ChatPage'
import { ExplorerPage } from './features/explorer/ExplorerPage'
import { PrImpactPage } from './features/pr-impact/PrImpactPage'
import { SearchPage } from './features/search/SearchPage'
import './App.css'
import './workspace.css'

const titles: Record<View, string> = {
  explorer: 'Explorer',
  search: 'Search',
  chat: 'Code chat',
  impact: 'PR impact',
}

function App() {
  const [activeView, setActiveView] = useState<View>('explorer')

  return (
    <div className="app-shell">
      <AppSidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="main-area">
        <AppHeader title={titles[activeView]} />
        {activeView === 'explorer' && <ExplorerPage />}
        {activeView === 'search' && <SearchPage />}
        {activeView === 'chat' && <ChatPage />}
        {activeView === 'impact' && <PrImpactPage />}
      </main>
    </div>
  )
}

export default App