import { useState, useEffect } from 'react';
import Sidebar, { type NavTab } from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import RepositoryOverview from './components/overview/RepositoryOverview';
import PRImpactScreen from './components/pr-impact/PRImpactScreen';

// Preserved existing detailed workspace modules
import GlobalSearch from './components/GlobalSearch';
import SymbolDetail from './components/SymbolDetail';
import CodebaseChat from './components/CodebaseChat';
import RecommendationsBoard from './components/RecommendationsBoard';

import './App.css';

const API_BASE = 'http://localhost:8000/api';

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('OVERVIEW');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLatencyMs, setSearchLatencyMs] = useState<number | null>(null);
  const [inspectedSymbolId, setInspectedSymbolId] = useState<number>(101);

  // Global hotkeys: ⌘K or / to search, 1-6 for tab navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (
        e.key === '/' &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        e.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (
        !e.metaKey &&
        !e.ctrlKey &&
        !e.altKey &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        if (e.key === '1') setActiveTab('OVERVIEW');
        if (e.key === '2') setActiveTab('SEARCH');
        if (e.key === '3') setActiveTab('GRAPH');
        if (e.key === '4') setActiveTab('PR_IMPACT');
        if (e.key === '5') setActiveTab('RAG');
        if (e.key === '6') setActiveTab('RECOMMENDATIONS');
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="reposcope-app">
      {/* 228px Left Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        prCount={3}
      />

      {/* Main Workspace Area */}
      <div className="reposcope-main-wrapper">
        {/* 78px Top Bar */}
        <TopBar
          activeTab={activeTab}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onSearchSubmit={() => setActiveTab('SEARCH')}
          searchLatencyMs={searchLatencyMs}
        />

        {/* Dynamic Content View */}
        <main className="reposcope-content">
          {activeTab === 'OVERVIEW' && (
            <RepositoryOverview
              onAnalyzePR={() => setActiveTab('PR_IMPACT')}
              onOpenGraph={() => setActiveTab('GRAPH')}
              onOpenRecommendations={() => setActiveTab('RECOMMENDATIONS')}
            />
          )}

          {activeTab === 'PR_IMPACT' && (
            <PRImpactScreen
              onExploreGraph={() => setActiveTab('GRAPH')}
            />
          )}

          {activeTab === 'SEARCH' && (
            <div style={{ backgroundColor: 'var(--surface)', border: '1px solid var(--border)', padding: '28px' }}>
              <GlobalSearch
                repoId={1}
                repoName="acme/platform"
                query={searchQuery}
                onQueryChange={setSearchQuery}
                apiBase={API_BASE}
                offlinePreview={true}
                onSelectSymbol={(symbolId) => {
                  setInspectedSymbolId(symbolId);
                  setActiveTab('GRAPH');
                }}
                onLatencyChange={setSearchLatencyMs}
              />
            </div>
          )}

          {activeTab === 'GRAPH' && (
            <SymbolDetail
              symbolId={inspectedSymbolId}
              repoId={1}
              repoName="acme/platform"
              offlinePreview={true}
              apiBase={API_BASE}
              onSelectSymbol={(id) => setInspectedSymbolId(id)}
              onBackToOverview={() => setActiveTab('OVERVIEW')}
            />
          )}

          {activeTab === 'RAG' && (
            <CodebaseChat
              repoId={1}
              repoName="acme/platform"
              apiBase={API_BASE}
              offlinePreview={true}
              onSelectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}

          {activeTab === 'RECOMMENDATIONS' && (
            <RecommendationsBoard
              repoId={1}
              repoName="acme/platform"
              apiBase={API_BASE}
              offlinePreview={true}
              onInspectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}
