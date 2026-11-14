import { apiRequest } from './client';

export interface Repository {
  id: number;
  url: string;
  name: string;
  default_branch: string;
  status: string;
  head_sha: string | null;
  snapshot_id: number | null;
  file_count: number | null;
  symbol_count: number | null;
}

export interface RegisterRepositoryResponse {
  repo_id: number;
  status: 'pending';
  message: string;
}

export function getRepository(repoId: number, signal?: AbortSignal) {
  return apiRequest<Repository>(`/repos/${repoId}`, { signal });
}

export function registerRepository(url: string) {
  return apiRequest<RegisterRepositoryResponse>('/repos', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}
