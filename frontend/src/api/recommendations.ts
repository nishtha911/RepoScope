import { apiRequest } from './client';
import type { RecommendationsResponse } from '../types/recommendations';

export function getRecommendations(repoId: number, limit = 10, signal?: AbortSignal) {
  return apiRequest<RecommendationsResponse>(
    `/repos/${repoId}/recommendations?k=${limit}`,
    { signal },
  );
}
