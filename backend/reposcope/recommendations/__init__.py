"""Codebase recommendations and heuristic priority scoring package."""
from reposcope.recommendations.detectors import (
    CandidateDataset,
    CandidateEvidence,
    CandidateGap,
    CandidateReport,
    CandidateSymbol,
    DetectorConfig,
    detect_candidates,
)
from reposcope.recommendations.features import (
    FindingFeatures,
    extract_features,
)
from reposcope.recommendations.scorer import (
    HeuristicScorer,
    ScoredCandidateReport,
    ScorerConfig,
    compute_priority_score,
)

__all__ = [
    "CandidateDataset",
    "CandidateEvidence",
    "CandidateGap",
    "CandidateReport",
    "CandidateSymbol",
    "DetectorConfig",
    "FindingFeatures",
    "HeuristicScorer",
    "ScoredCandidateReport",
    "ScorerConfig",
    "compute_priority_score",
    "detect_candidates",
    "extract_features",
]
