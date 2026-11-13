import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import Sidebar, { type NavTab } from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import RepositoryOverview from './components/overview/RepositoryOverview';
import PRImpactScreen from './components/pr-impact/PRImpactScreen';

// Detailed workspace modules
import GlobalSearch from './components/GlobalSearch';
import SymbolDetail from './components/SymbolDetail';
import CodebaseChat from './components/CodebaseChat';
import RecommendationsBoard from './components/RecommendationsBoard';
import { fetchRepository } from './api/repositories';

import './App.css';

const API_BASE = 'http://localhost:8000/api';

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('OVERVIEW');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLatencyMs, setSearchLatencyMs] = useState<number | null>(null);
  const [inspectedSymbolId, setInspectedSymbolId] = useState<number | null>(null);
  const repositoryQuery = useQuery({
    queryKey: ['repository', 1, API_BASE],
    queryFn: () => fetchRepository(1, API_BASE),
    retry: false,
    staleTime: 30_000,
  });
  const repository = repositoryQuery.data;

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
        repository={repository}
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
          repositoryName={repository?.name}
        />

        {/* Dynamic Content View */}
        <main className="reposcope-content">
          {repositoryQuery.isPending && (
            <div className="reposcope-content-state">Loading repository data...</div>
          )}
          {repositoryQuery.isError && (
            <div className="reposcope-content-state" role="alert">
              Unable to load repository data: {repositoryQuery.error.message}
            </div>
          )}
          {repository && activeTab === 'OVERVIEW' && (
            <RepositoryOverview
              onAnalyzePR={() => setActiveTab('PR_IMPACT')}
              onOpenGraph={(symbolId) => {
                if (symbolId) setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
              onOpenSearch={(query) => {
                if (query) setSearchQuery(query);
                setActiveTab('SEARCH');
              }}
              onOpenRecommendations={() => setActiveTab('RECOMMENDATIONS')}
              repository={repository}
              apiBase={API_BASE}
            />
          )}

          {repository && activeTab === 'PR_IMPACT' && (
            <PRImpactScreen
              apiBase={API_BASE}
              repoId={repository.id}
              repoName={repository.name}
              onExploreGraph={(symbolIdentifier) => {
                if (typeof symbolIdentifier === 'number') {
                  setInspectedSymbolId(symbolIdentifier);
                } else if (symbolIdentifier) {
                  const symMap: Record<string, number> = {
                    authorizePayment: 101,
                    createCheckout: 204,
                    issueRefund: 101,
                    verifyToken: 204,
                    processStripeWebhook: 101,
                    resolve_calls: 101,
                    scan: 204,
                    authenticateRequest: 204,
                    verifySessionToken: 204,
                  };
                  if (symMap[symbolIdentifier]) {
                    setInspectedSymbolId(symMap[symbolIdentifier]);
                  }
                }
                setActiveTab('GRAPH');
              }}
              onReviewRecommendations={() => setActiveTab('RECOMMENDATIONS')}
            />
          )}

          {repository && activeTab === 'SEARCH' && (
            <div style={{ backgroundColor: 'var(--surface)', border: '1px solid var(--border)', padding: '28px' }}>
              <GlobalSearch
                repoId={repository.id}
                repoName={repository.name}
                query={searchQuery}
                onQueryChange={setSearchQuery}
                apiBase={API_BASE}
                onSelectSymbol={(symbolId) => {
                  setInspectedSymbolId(symbolId);
                  setActiveTab('GRAPH');
                }}
                onLatencyChange={setSearchLatencyMs}
              />
            </div>
          )}

          {repository && activeTab === 'GRAPH' && inspectedSymbolId === null && (
            <div className="reposcope-content-state">
              Select a symbol from Code search or another live analysis result to inspect its graph.
            </div>
          )}
          {repository && activeTab === 'GRAPH' && inspectedSymbolId !== null && (
            <SymbolDetail
              symbolId={inspectedSymbolId}
              repoId={repository.id}
              repoName={repository.name}
              apiBase={API_BASE}
              onSelectSymbol={(id) => setInspectedSymbolId(id)}
              onBackToOverview={() => setActiveTab('OVERVIEW')}
            />
          )}

          {repository && activeTab === 'RAG' && (
            <CodebaseChat
              repoId={repository.id}
              repoName={repository.name}
              apiBase={API_BASE}
              onSelectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}

          {repository && activeTab === 'RECOMMENDATIONS' && (
            <RecommendationsBoard
              repoId={repository.id}
              repoName={repository.name}
              apiBase={API_BASE}
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
