import { apiRequest } from './client';
import type { PRImpactReport, PRImpactRequestPayload, PRFeedbackStatus } from '../types/prImpact';

export function analyzePr(repoId: number, payload: PRImpactRequestPayload) {
  return apiRequest<PRImpactReport>(`/repos/${repoId}/pr-impact`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function submitPrFeedback(
  repoId: number,
  analysisKey: string,
  action: Exclude<PRFeedbackStatus, 'pending'>,
) {
  return apiRequest<{ status: 'ok'; id: number; action: string }>(
    `/repos/${repoId}/pr-impact/feedback?analysis_key=${encodeURIComponent(analysisKey)}`,
    {
      method: 'POST',
      body: JSON.stringify({ action }),
    },
  );
}

export function submitRecommendationFeedback(
  recommendationId: number,
  action: Exclude<PRFeedbackStatus, 'pending'>,
) {
  return apiRequest<{ status: 'ok'; id: number; action: string }>(
    `/recs/${recommendationId}/feedback`,
    {
      method: 'POST',
      body: JSON.stringify({ action }),
    },
  );
}
