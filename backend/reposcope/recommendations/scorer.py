"""Heuristic feature scorer for codebase recommendations.

Computes multi-feature priority scores using the formula:
    score = (impact * likelihood) / effort * confidence

Implements Day 12 Track 2 heuristic scoring and ranking of detected candidates.
"""
import math
from typing import Sequence
from pydantic import BaseModel, ConfigDict, Field

from reposcope.contracts.finding import Finding
from reposcope.contracts.symbol import Symbol
from reposcope.recommendations.detectors import (
    CandidateDataset,
    CandidateEvidence,
    CandidateGap,
    CandidateReport,
    CandidateSymbol,
)
from reposcope.recommendations.features import (
    FindingFeatures,
    extract_features,
)


def compute_priority_score(
    impact: float,
    likelihood: float,
    effort: float,
    confidence: float,
    *,
    category_multiplier: float = 1.0,
    round_digits: int | None = 4,
) -> float:
    """Calculate the priority score: (impact * likelihood) / effort * confidence.

    Args:
        impact: Severity or scope of positive change (>= 0).
        likelihood: Probability of defect or benefit realization (0.0 <= likelihood <= 1.0).
        effort: Estimated effort or cost to address (> 0).
        confidence: Measurement / detection confidence (0.0 <= confidence <= 1.0).
        category_multiplier: Prior feedback weight multiplier (> 0).
        round_digits: Number of decimal places to round result, or None.

    Returns:
        Priority score as a non-negative float.

    Raises:
        ValueError: If effort <= 0, likelihood or confidence not in [0, 1],
                    impact < 0, or any value is NaN/infinite.
    """
    for name, val in [
        ("impact", impact),
        ("likelihood", likelihood),
        ("effort", effort),
        ("confidence", confidence),
        ("category_multiplier", category_multiplier),
    ]:
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"{name} must be a finite number, got {val}")

    if effort <= 0.0:
        raise ValueError(f"effort must be strictly positive, got {effort}")
    if impact < 0.0:
        raise ValueError(f"impact cannot be negative, got {impact}")
    if not (0.0 <= likelihood <= 1.0):
        raise ValueError(f"likelihood must be between 0.0 and 1.0, got {likelihood}")
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")
    if category_multiplier <= 0.0:
        raise ValueError(f"category_multiplier must be positive, got {category_multiplier}")

    raw_score = ((impact * likelihood) / effort) * confidence * category_multiplier
    score = max(0.0, raw_score)

    if round_digits is not None:
        return round(score, round_digits)
    return score


class ScorerConfig(BaseModel):
    """Configuration for the heuristic feature scorer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_multipliers: dict[str, float] = Field(default_factory=dict)
    min_effort: float = Field(default=0.5, gt=0)
    round_digits: int = Field(default=4, ge=0, le=10)


class ScoredCandidateReport(BaseModel):
    """Candidate report enriched with heuristic priority scores and feature records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_id: int = Field(gt=0)
    snapshot_id: int = Field(gt=0)
    findings: tuple[Finding, ...]
    evidence: tuple[CandidateEvidence, ...]
    gaps: tuple[CandidateGap, ...]
    features: tuple[FindingFeatures, ...]


class HeuristicScorer:
    """Computes features and ranks codebase findings using deterministic heuristics."""

    def __init__(self, config: ScorerConfig | None = None):
        self.config = config or ScorerConfig()

    def score_finding(
        self,
        finding: Finding,
        evidence: CandidateEvidence | None = None,
        symbol_context: CandidateSymbol | Symbol | None = None,
    ) -> tuple[Finding, FindingFeatures]:
        """Compute features and assign priority score and confidence to a finding."""
        features = extract_features(
            finding=finding,
            evidence=evidence,
            symbol_context=symbol_context,
        )

        effort = max(self.config.min_effort, features.effort)
        multiplier = self.config.category_multipliers.get(finding.category, 1.0)

        score = compute_priority_score(
            impact=features.impact,
            likelihood=features.likelihood,
            effort=effort,
            confidence=features.confidence,
            category_multiplier=multiplier,
            round_digits=self.config.round_digits,
        )

        scored_finding = finding.model_copy(
            update={
                "score": score,
                "confidence": features.confidence,
            }
        )

        return scored_finding, features

    def score_report(
        self,
        report: CandidateReport,
        dataset: CandidateDataset | None = None,
    ) -> ScoredCandidateReport:
        """Score all findings in a CandidateReport and return ranked report.

        Findings are sorted by priority score descending. Secondary sort
        is symbol_id ascending for strict determinism.
        """
        # Index symbols by ID if dataset was provided
        symbol_lookup: dict[int, CandidateSymbol] = {}
        if dataset:
            symbol_lookup = {cs.symbol.id: cs for cs in dataset.symbols if cs.symbol.id is not None}

        # Index evidence by (category, symbol_id)
        evidence_lookup: dict[tuple[str, int | None], CandidateEvidence] = {}
        for ev in report.evidence:
            evidence_lookup[(ev.category, ev.symbol_id)] = ev

        scored_pairs: list[tuple[Finding, FindingFeatures, CandidateEvidence | None]] = []

        for idx, finding in enumerate(report.findings):
            # Attempt to locate matching evidence
            ev = evidence_lookup.get((finding.category, finding.symbol_id))
            if ev is None and idx < len(report.evidence):
                ev = report.evidence[idx]

            sym = symbol_lookup.get(finding.symbol_id) if finding.symbol_id else None

            scored_f, feats = self.score_finding(
                finding=finding,
                evidence=ev,
                symbol_context=sym,
            )
            scored_pairs.append((scored_f, feats, ev))

        # Sort descending by priority score; tie-break by symbol_id asc, category asc
        scored_pairs.sort(
            key=lambda item: (
                -(item[0].score if item[0].score is not None else -1.0),
                item[0].symbol_id if item[0].symbol_id is not None else 0,
                item[0].category,
            )
        )

        sorted_findings = tuple(item[0] for item in scored_pairs)
        sorted_features = tuple(item[1] for item in scored_pairs)
        sorted_evidence = tuple(
            item[2] for item in scored_pairs if item[2] is not None
        )

        return ScoredCandidateReport(
            repo_id=report.repo_id,
            snapshot_id=report.snapshot_id,
            findings=sorted_findings,
            evidence=sorted_evidence,
            gaps=report.gaps,
            features=sorted_features,
        )

    def rank_findings(self, findings: Sequence[Finding]) -> list[Finding]:
        """Rank an arbitrary sequence of findings by score descending."""
        scored = [f if f.score is not None else self.score_finding(f)[0] for f in findings]
        return sorted(
            scored,
            key=lambda f: (
                -(f.score if f.score is not None else -1.0),
                f.symbol_id if f.symbol_id is not None else 0,
                f.category,
            ),
        )

