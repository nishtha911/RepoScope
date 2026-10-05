import { useEffect, useState, type FormEvent } from 'react'
import { ArrowUpRight, FolderGit2, GitBranch, Plus, RefreshCw } from 'lucide-react'
import { createRepository, getHealth, listRepositories } from '../../api/client'
import type { Repository } from '../../types/api'

export function ExplorerPage() {
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [apiOnline, setApiOnline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [remoteUrl, setRemoteUrl] = useState('')

  async function refresh() {
    setLoading(true)
    try {
      await getHealth()
      setApiOnline(true)
    } catch {
      setApiOnline(false)
      setMessage('Could not reach the API. Start the backend to connect a repository.')
    }

    try {
      setRepositories(await listRepositories())
      setMessage((current) => current.startsWith('Could not reach') ? '' : current)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load repositories.')
    }
    setLoading(false)
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanedUrl = remoteUrl.trim().replace(/\.git$/, '')
    const parts = new URL(cleanedUrl).pathname.split('/').filter(Boolean)
    const fullName = parts.slice(-2).join('/')
    if (parts.length < 2) {
      setMessage('Enter a repository URL with an owner and repository name.')
      return
    }

    setSubmitting(true)
    setMessage('')
    try {
      const repository = await createRepository(fullName, remoteUrl.trim())
      setRepositories((current) => [...current, repository])
      setRemoteUrl('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Repository could not be added.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <div className="eyebrow">CODE INTELLIGENCE</div>
          <h1>Repository explorer</h1>
          <p>Connect a codebase to map its symbols, relationships, and change impact.</p>
        </div>
        <div className={`api-status ${apiOnline ? 'online' : ''}`}>
          <span className="status-dot" /> API {apiOnline ? 'connected' : 'offline'}
        </div>
      </section>

      <section className="repo-section" aria-labelledby="repositories-heading">
        <div className="section-heading">
          <div>
            <h2 id="repositories-heading">Repositories</h2>
            <span className="section-count">{repositories.length.toString().padStart(2, '0')}</span>
          </div>
          <button className="icon-button" type="button" onClick={() => void refresh()} title="Refresh repositories" aria-label="Refresh repositories">
            <RefreshCw size={16} />
          </button>
        </div>

        {repositories.length > 0 ? (
          <div className="repo-list">
            {repositories.map((repo) => (
              <article className="repo-row" key={repo.id}>
                <span className="repo-icon"><FolderGit2 size={19} /></span>
                <div className="repo-name"><strong>{repo.full_name}</strong><span>{repo.remote_url}</span></div>
                <span className="branch-label"><GitBranch size={13} />{repo.default_branch ?? 'default branch'}</span>
                <button className="icon-button" type="button" title={`Open ${repo.full_name}`} aria-label={`Open ${repo.full_name}`}><ArrowUpRight size={16} /></button>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon"><FolderGit2 size={25} strokeWidth={1.5} /></div>
            <h3>{loading ? 'Checking your workspace' : 'No repositories connected'}</h3>
            <p>{loading ? 'Looking for the RepoScope API...' : 'Add a Git repository to start building its code graph.'}</p>
            {!loading && <span className="empty-rule" />}
          </div>
        )}
      </section>

      <section className="connect-section" aria-labelledby="connect-heading">
        <div className="connect-title">
          <span className="connect-number">01</span>
          <div><h2 id="connect-heading">Connect a repository</h2><p>Public Git remote URL</p></div>
        </div>
        <form className="connect-form" onSubmit={handleSubmit}>
          <label className="url-input-wrap">
            <span className="input-prefix">git</span>
            <input
              type="url"
              value={remoteUrl}
              onChange={(event) => setRemoteUrl(event.target.value)}
              placeholder="https://github.com/owner/repository"
              aria-label="Git repository URL"
              required
            />
          </label>
          <button className="primary-button" disabled={submitting || !apiOnline} type="submit">
            <Plus size={16} /> {submitting ? 'Connecting' : 'Add repository'}
          </button>
        </form>
        {message && <p className="form-message" role="status">{message}</p>}
      </section>

      <div className="footnote"><span className="footnote-mark">i</span> Repository indexing and graph analysis will be available as those services are implemented.</div>
    </div>
  )
}