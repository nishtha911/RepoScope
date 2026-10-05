export interface Repository {
  id: number
  full_name: string
  remote_url: string
  default_branch: string | null
  commit_sha: string | null
}

export interface HealthResponse {
  status: string
  service: string
}