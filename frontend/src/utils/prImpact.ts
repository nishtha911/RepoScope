import type { RiskLevel } from '../types/prImpact';

export function normalizeRiskLevel(risk: RiskLevel | string): 'Low' | 'Medium' | 'High' | 'Critical' {
  const normalized = risk.trim().toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'high') return 'High';
  if (normalized === 'medium' || normalized === 'med') return 'Medium';
  return 'Low';
}

export function getRiskBadgeClass(risk: RiskLevel | string): string {
  const level = normalizeRiskLevel(risk);
  switch (level) {
    case 'Critical':
      return 'pr-risk-badge--critical';
    case 'High':
      return 'pr-risk-badge--high';
    case 'Medium':
      return 'pr-risk-badge--medium';
    case 'Low':
    default:
      return 'pr-risk-badge--low';
  }
}

