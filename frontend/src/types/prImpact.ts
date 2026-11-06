export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface PRImpactReport {
  pr_url?: string | null;
  patch_name?: string | null;
  risk_level: RiskLevel;
  risk_score: number;
  files_changed_count: number;
  impacted_symbols_count: number;
  affected_endpoints_count: number;
  impacted_tests_count: number;
  summary: string;
}

export interface PRAnalysisHistoryItem extends PRImpactReport {
  id: string;
  title: string;
  analyzed_at: number;
  input_type: 'pr_url' | 'patch';
}

export interface PRImpactRequestPayload {
  pr_url?: string | null;
  patch?: string | null;
}

