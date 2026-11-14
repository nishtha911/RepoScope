export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof body === 'object' && body !== null && 'error' in body &&
      typeof body.error === 'object' && body.error !== null &&
      'message' in body.error && typeof body.error.message === 'string'
        ? body.error.message
        : typeof body === 'object' && body !== null && 'detail' in body &&
            typeof body.detail === 'string'
          ? body.detail
          : `Request failed (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}
