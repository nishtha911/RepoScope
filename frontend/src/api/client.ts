import type { HealthResponse, Repository } from '../types/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const getHealth = () => request<HealthResponse>('/api/health')

export const listRepositories = () =>
  request<Repository[]>('/api/v1/repos')

export const createRepository = (fullName: string, remoteUrl: string) =>
  request<Repository>('/api/v1/repos', {
    method: 'POST',
    body: JSON.stringify({ full_name: fullName, remote_url: remoteUrl }),
  })