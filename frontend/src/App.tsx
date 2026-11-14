import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, LoaderCircle, Plus, RefreshCw } from 'lucide-react';
import Sidebar, { type NavTab } from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import RepositoryOverview from './components/overview/RepositoryOverview';
import PRImpactScreen from './components/pr-impact/PRImpactScreen';
import GlobalSearch from './components/GlobalSearch';
import SymbolDetail from './components/SymbolDetail';
import CodebaseChat from './components/CodebaseChat';
import RecommendationsBoard from './components/RecommendationsBoard';
import { getRepository, registerRepository } from './api/repositories';
import { ApiError } from './api/client';
import './App.css';

const STORAGE_KEY = 'reposcope.selectedRepositoryId';

function readStoredRepositoryId(): number | null {
  const value = Number(window.localStorage.getItem(STORAGE_KEY));
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function RepositorySetup({
  onRegistered,
}: {
  onRegistered: (repoId: number) => void;
}) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await registerRepository(url.trim());
      window.localStorage.setItem(STORAGE_KEY, String(result.repo_id));
      onRegistered(result.repo_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Repository registration failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="reposcope-setup">
      <div className="reposcope-setup__card">
        <span className="reposcope-eyebrow">REPOSCOPE // WORKSPACE SETUP</span>
        <h1 className="reposcope-page-title">Connect a repository.</h1>
        <p className="reposcope-page-subtitle">
          Enter a public GitHub repository URL. RepoScope will index it and expose the live
          graph, search, Q&A, recommendations, and PR analysis workflows.
        </p>
        <form className="reposcope-setup__form" onSubmit={handleSubmit}>
          <label htmlFor="repository-url">GitHub repository URL</label>
          <input
            id="repository-url"
            className="bauhaus-input"
            type="url"
            required
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://github.com/owner/repository"
          />
          {error && <p className="reposcope-form-error" role="alert">{error}</p>}
          <button className="bauhaus-btn-invert" type="submit" disabled={isSubmitting}>
            {isSubmitting ? <LoaderCircle className="reposcope-spin" size={16} /> : <Plus size={16} />}
            {isSubmitting ? 'CONNECTING…' : 'CONNECT REPOSITORY'}
          </button>
        </form>
      </div>
    </main>
  );
}

function RepositoryLoading({ message }: { message: string }) {
  return (
    <main className="reposcope-setup">
      <div className="reposcope-setup__card reposcope-setup__card--loading">
        <LoaderCircle className="reposcope-spin" size={24} />
        <p>{message}</p>
      </div>
    </main>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('OVERVIEW');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLatencyMs, setSearchLatencyMs] = useState<number | null>(null);
  const [inspectedSymbolId, setInspectedSymbolId] = useState<number | null>(null);
  const [repositoryId, setRepositoryId] = useState<number | null>(() => readStoredRepositoryId());

  const repositoryQuery = useQuery({
    queryKey: ['repository', repositoryId],
    queryFn: ({ signal }) => getRepository(repositoryId!, signal),
    enabled: repositoryId !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'queued' || status === 'running' ? 3000 : false;
    },
  });

  const repository = repositoryQuery.data;
  const apiError = repositoryQuery.error;

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (
        event.key === '/' &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        event.preventDefault();
        document.getElementById('header-global-search')?.focus();
      } else if (
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        const tabs: Record<string, NavTab> = {
          '1': 'OVERVIEW',
          '2': 'SEARCH',
          '3': 'GRAPH',
          '4': 'PR_IMPACT',
          '5': 'RAG',
          '6': 'RECOMMENDATIONS',
        };
        if (tabs[event.key]) setActiveTab(tabs[event.key]);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const repoName = useMemo(() => repository?.name ?? 'Repository', [repository]);

  if (repositoryId === null) {
    return <RepositorySetup onRegistered={setRepositoryId} />;
  }

  if (repositoryQuery.isPending) {
    return <RepositoryLoading message="Loading repository workspace…" />;
  }

  if (repositoryQuery.isError || !repository) {
    return (
      <main className="reposcope-setup">
        <div className="reposcope-setup__card">
          <span className="reposcope-eyebrow">WORKSPACE UNAVAILABLE</span>
          <h1 className="reposcope-page-title">Could not load this repository.</h1>
          <p className="reposcope-page-subtitle">
            {apiError instanceof ApiError ? apiError.message : 'The API did not return repository data.'}
          </p>
          <div className="reposcope-setup__actions">
            <button type="button" className="bauhaus-btn-invert" onClick={() => void repositoryQuery.refetch()}>
              <RefreshCw size={15} /> RETRY
            </button>
            <button
              type="button"
              className="bauhaus-btn"
              onClick={() => {
                window.localStorage.removeItem(STORAGE_KEY);
                setRepositoryId(null);
              }}
            >
              CHOOSE ANOTHER REPOSITORY
            </button>
          </div>
        </div>
      </main>
    );
  }

  const changeRepository = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setRepositoryId(null);
  };

  return (
    <div className="reposcope-app">
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        repository={repository}
        onChangeRepository={changeRepository}
      />
      <div className="reposcope-main-wrapper">
        <TopBar
          activeTab={activeTab}
          repositoryName={repoName}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onSearchSubmit={() => setActiveTab('SEARCH')}
          searchLatencyMs={searchLatencyMs}
        />
        <main className="reposcope-content">
          {activeTab === 'OVERVIEW' && (
            <RepositoryOverview
              repository={repository}
              onAnalyzePR={() => setActiveTab('PR_IMPACT')}
              onOpenGraph={(symbolId) => {
                if (symbolId) setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
              onOpenRecommendations={() => setActiveTab('RECOMMENDATIONS')}
              onOpenSearch={() => setActiveTab('SEARCH')}
            />
          )}
          {activeTab === 'PR_IMPACT' && (
            <PRImpactScreen
              repoId={repository.id}
              onExploreGraph={(symbolId) => {
                if (symbolId) setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}
          {activeTab === 'SEARCH' && (
            <GlobalSearch
              repoId={repository.id}
              repoName={repoName}
              query={searchQuery}
              onQueryChange={setSearchQuery}
              onSelectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
              onLatencyChange={setSearchLatencyMs}
            />
          )}
          {activeTab === 'GRAPH' && (
            <SymbolDetail
              symbolId={inspectedSymbolId ?? 0}
              repoId={repository.id}
              repoName={repoName}
              onSelectSymbol={setInspectedSymbolId}
              onBackToOverview={() => setActiveTab('OVERVIEW')}
            />
          )}
          {activeTab === 'RAG' && (
            <CodebaseChat
              repoId={repository.id}
              repoName={repoName}
              onSelectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}
          {activeTab === 'RECOMMENDATIONS' && (
            <RecommendationsBoard
              repoId={repository.id}
              repoName={repoName}
              onInspectSymbol={(symbolId) => {
                setInspectedSymbolId(symbolId);
                setActiveTab('GRAPH');
              }}
            />
          )}
        </main>
      </div>
      <button
        type="button"
        className="reposcope-mobile-repo-button"
        onClick={changeRepository}
        aria-label="Change repository"
      >
        <ArrowRight size={16} />
      </button>
    </div>
  );
}
