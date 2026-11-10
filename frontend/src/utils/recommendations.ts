import type { FindingCategory, ImpactLevel } from '../types/recommendations';

export interface CategoryMeta {
  key: string;
  label: string;
  shortTag: string;
  className: string;
  icon: string;
}

export function getCategoryMeta(category: FindingCategory): CategoryMeta {
  const norm = (category || '').trim().toUpperCase();

  if (norm.includes('UNTESTED')) {
    return {
      key: 'UNTESTED_HOTSPOT',
      label: 'Untested Hotspot',
      shortTag: 'UNTESTED',
      className: 'rec-cat-tag--untested',
      icon: '🧪',
    };
  }

  if (norm.includes('COMPLEXITY')) {
    return {
      key: 'COMPLEXITY_HOTSPOT',
      label: 'Complexity Hotspot',
      shortTag: 'COMPLEXITY',
      className: 'rec-cat-tag--complexity',
      icon: '⚡',
    };
  }

  if (norm.includes('DOC') || norm.includes('API')) {
    return {
      key: 'API_DOC_GAP',
      label: 'API Doc Gap',
      shortTag: 'DOC GAP',
      className: 'rec-cat-tag--docgap',
      icon: '📄',
    };
  }

  return {
    key: norm,
    label: norm.replace(/_/g, ' '),
    shortTag: norm.split('_')[0] || 'FINDING',
    className: 'rec-cat-tag--default',
    icon: '🔍',
  };
}

export function getImpactLevel(impact?: number, score?: number | null): ImpactLevel {
  const val = typeof impact === 'number' ? impact : typeof score === 'number' ? score : 0.5;

  if (val >= 0.85) return 'CRITICAL';
  if (val >= 0.7) return 'HIGH';
  if (val >= 0.5) return 'MEDIUM';
  return 'LOW';
}

export function getImpactBadgeClass(level: ImpactLevel): string {
  switch (level) {
    case 'CRITICAL':
      return 'rec-impact-badge--critical';
    case 'HIGH':
      return 'rec-impact-badge--high';
    case 'MEDIUM':
      return 'rec-impact-badge--medium';
    case 'LOW':
    default:
      return 'rec-impact-badge--low';
  }
}

export function formatScore(score?: number | null): string {
  if (typeof score !== 'number' || isNaN(score)) return '0.00';
  return score.toFixed(2);
}
