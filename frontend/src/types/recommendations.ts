export type FindingCategory =
  | 'UNTESTED_HOTSPOT'
  | 'COMPLEXITY_HOTSPOT'
  | 'API_DOC_GAP'
  | string;

export type ImpactLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type RationaleSource = 'llm_constrained' | 'deterministic';

export interface FeatureCitation {
  feature: string;
  value: number;
}

export interface ComputedFeatures {
  impact?: number;
  likelihood?: number;
  effort?: number;
  confidence?: number;
  score?: number;
  applied_effort?: number;
  category_multiplier?: number;
  measured_fan_in?: number;
  measured_complexity?: number;
  measured_documentation_gap?: number;
  [key: string]: unknown;
}

export interface RecommendationItem {
  id: number;
  snapshot_id: number;
  symbol_id: number | null;
  file_id: number | null;
  category: FindingCategory;
  title: string;
  description: string;
  score: number | null;
  confidence: number | null;
  rationale: string | null;
  rationale_source: RationaleSource | null;
  rationale_degraded_reason: string | null;
  feature_citations: FeatureCitation[];
  computed_features: ComputedFeatures;
  detector_evidence: Record<string, unknown>;
  // UI enrichment fields
  qualname?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
}

export interface RecommendationsResponse {
  recommendations: RecommendationItem[];
  repo_id: number | null;
  snapshot_id: number | null;
  commit_sha: string | null;
  run_id: number | null;
  gaps: Array<Record<string, unknown>>;
}
