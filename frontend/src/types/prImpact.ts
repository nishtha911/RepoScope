export type RiskLevel =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'CRITICAL'
  | 'Low'
  | 'Medium'
  | 'High'
  | 'Critical';

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
  feedback?: PRFeedbackStatus;
  impacted_endpoints?: AffectedEndpointItem[];
  impacted_tests?: ImpactedTestItem[];
  missing_tests?: MissingTestItem[];
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

export interface ImpactedTestItem {
  id: string;
  test_name: string;
  file_path: string;
  confidence: number; // e.g. 0.95 or 1.0
}

export interface MissingTestItem {
  symbol_id?: number;
  symbol_name: string;
  file_path: string;
  reason: string; // e.g. "No direct static test association found"
}

export interface AffectedEndpointItem {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  route: string;
  handler_name: string;
  confidence: number;
}

export type PRFeedbackStatus = 'pending' | 'accepted' | 'dismissed';
