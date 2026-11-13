export interface Repository {
  id: number;
  url: string;
  name: string;
  default_branch: string;
  status: 'pending' | 'indexing' | 'ready' | 'failed';
  head_sha: string | null;
  snapshot_id: number | null;
  file_count: number | null;
  symbol_count: number | null;
}

const apiUrl = (apiBase: string, path: string) =>
  `${apiBase.replace(/\/$/, '')}${path}`;

export async function fetchRepository(
  repoId: number,
  apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
): Promise<Repository> {
  const response = await fetch(apiUrl(apiBase, `/repos/${repoId}`));
  const body = (await response.json().catch(() => null)) as
    | Repository
    | { error?: { message?: string }; detail?: string }
    | null;
  if (!response.ok) {
    const message =
      body && 'error' in body && body.error?.message
        ? body.error.message
        : body && 'detail' in body && body.detail
          ? body.detail
          : `Repository request failed (HTTP ${response.status}).`;
    throw new Error(message);
  }
  if (!body || !('id' in body) || typeof body.id !== 'number' || !body.name) {
    throw new Error('The server returned an invalid repository response.');
  }
  return body;
}
