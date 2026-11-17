export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export class ApiError extends Error {
  readonly status: number;
  readonly retryAfterSeconds: number | null;

  constructor(message: string, status: number, retryAfterSeconds: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
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
    const retryHeader = Number(response.headers.get('Retry-After'));
    const details =
      typeof body === 'object' && body !== null && 'error' in body &&
      typeof body.error === 'object' && body.error !== null &&
      'details' in body.error && typeof body.error.details === 'object' &&
      body.error.details !== null && 'retry_after' in body.error.details
        ? Number(body.error.details.retry_after)
        : NaN;
    const retryAfterSeconds =
      response.status === 429 && Number.isFinite(retryHeader) && retryHeader > 0
        ? Math.ceil(retryHeader)
        : response.status === 429 && Number.isFinite(details) && details > 0
          ? Math.ceil(details)
          : null;
    throw new ApiError(message, response.status, retryAfterSeconds);
  }
  return body as T;
}
