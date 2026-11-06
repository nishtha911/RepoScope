"""Heuristic feature computation for codebase findings.

Computes multi-dimensional features (impact, likelihood, effort, confidence)
from AST symbol metrics, graph fan-in, and detector evidence.
"""
from pydantic import BaseModel, ConfigDict, Field

from reposcope.contracts.finding import Finding
from reposcope.contracts.symbol import Symbol
from reposcope.recommendations.detectors import (
    CandidateEvidence,
    CandidateSymbol,
)


class FindingFeatures(BaseModel):
    """Structured feature vector computed for a codebase finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol_id: int | None = None
    category: str = Field(min_length=1)

    # Core scoring dimensions
    impact: float = Field(ge=0.0, allow_inf_nan=False)
    likelihood: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    effort: float = Field(gt=0.0, allow_inf_nan=False)
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    # Detailed domain metrics (for rationales and ranking analysis)
    fan_in: int = 0
    cyclomatic_complexity: int | None = None
    line_count: int | None = None
    is_endpoint: bool = False
    affected_callers_count: int = 0
    missing_docstring: bool = False


def extract_features(
    finding: Finding,
    evidence: CandidateEvidence | None = None,
    symbol_context: CandidateSymbol | Symbol | None = None,
) -> FindingFeatures:
    """Extract and compute impact, likelihood, effort, and confidence for a finding.

    Handles UNTESTED_HOTSPOT, COMPLEXITY_HOTSPOT, API_DOC_GAP, and custom categories.
    """
    category = finding.category
    sid = finding.symbol_id

    # Resolve symbol metrics if CandidateSymbol was provided
    complexity: int | None = None
    line_count: int | None = None
    if isinstance(symbol_context, CandidateSymbol):
        complexity = symbol_context.cyclomatic_complexity
        if symbol_context.symbol.start_line and symbol_context.symbol.end_line:
            line_count = symbol_context.symbol.end_line - symbol_context.symbol.start_line + 1
    elif isinstance(symbol_context, Symbol):
        if symbol_context.start_line and symbol_context.end_line:
            line_count = symbol_context.end_line - symbol_context.start_line + 1

    # Extract evidence-measured facts
    measured_val = evidence.measured_value if evidence else None
    related_ids = evidence.related_symbol_ids if evidence else ()

    if category == "UNTESTED_HOTSPOT":
        # Fan-in is the number of incoming non-test callers
        fan_in = measured_val if measured_val is not None else len(related_ids)
        if fan_in < 1:
            fan_in = max(len(related_ids), 5)

        # Impact: Higher fan-in means broader potential blast radius across callers
        base_impact = 5.0
        fan_in_bonus = min(5.0, (fan_in - 5) * 0.5)
        impact = round(base_impact + max(0.0, fan_in_bonus), 4)

        # Likelihood: Frequently called untested code has high regression escape risk
        base_likelihood = 0.70
        caller_factor = min(0.20, fan_in * 0.02)
        complexity_factor = 0.05 if (complexity or 0) >= 10 else 0.0
        likelihood = round(min(0.95, base_likelihood + caller_factor + complexity_factor), 4)

        # Effort: Writing unit tests depends on function size and cyclomatic branches
        base_effort = 1.0
        branch_effort = min(3.0, (complexity or 4) * 0.15)
        length_effort = min(2.0, (line_count or 20) * 0.02)
        effort = round(base_effort + branch_effort + length_effort, 4)

        # Confidence: High confidence when emitted by complete static test-link index
        confidence = 0.95

        return FindingFeatures(
            symbol_id=sid,
            category=category,
            impact=impact,
            likelihood=likelihood,
            effort=effort,
            confidence=confidence,
            fan_in=fan_in,
            cyclomatic_complexity=complexity,
            line_count=line_count,
            affected_callers_count=len(related_ids),
        )

    elif category == "COMPLEXITY_HOTSPOT":
        measured_complexity = (
            measured_val
            if measured_val is not None
            else (complexity if complexity is not None else 10)
        )

        # Impact: High cyclomatic complexity correlates with high maintenance and defect risks
        base_impact = 4.0
        complexity_scale = min(6.0, max(0.0, (measured_complexity - 10) * 0.4))
        impact = round(base_impact + complexity_scale, 4)

        # Likelihood: Probability of logic defect increases with decision branching
        base_likelihood = 0.55
        complexity_risk = min(0.40, max(0.0, (measured_complexity - 10) * 0.03))
        likelihood = round(min(0.95, base_likelihood + complexity_risk), 4)

        # Effort: Refactoring high-complexity routines requires careful structural redesign
        base_effort = 2.0
        refactor_effort = min(6.0, max(0.0, (measured_complexity - 10) * 0.3))
        effort = round(base_effort + refactor_effort, 4)

        # Confidence: Measured directly from deterministic AST tree
        confidence = 0.95

        return FindingFeatures(
            symbol_id=sid,
            category=category,
            impact=impact,
            likelihood=likelihood,
            effort=effort,
            confidence=confidence,
            cyclomatic_complexity=measured_complexity,
            line_count=line_count,
        )

    elif category == "API_DOC_GAP":
        # Impact: Missing endpoint docs harms developer onboarding & client contract guarantees
        impact = 4.5

        # Likelihood: Without docstring, endpoint misuse / incorrect client request is moderately likely
        likelihood = 0.65

        # Effort: Writing a clear docstring is low effort (high ROI quick-win)
        effort = 1.0

        # Confidence: Deterministic docstring presence verification
        confidence = 0.90

        return FindingFeatures(
            symbol_id=sid,
            category=category,
            impact=impact,
            likelihood=likelihood,
            effort=effort,
            confidence=confidence,
            is_endpoint=True,
            missing_docstring=True,
            affected_callers_count=len(related_ids),
        )

    # Default fallback for unknown or generic findings
    return FindingFeatures(
        symbol_id=sid,
        category=category,
        impact=3.0,
        likelihood=0.50,
        effort=2.0,
        confidence=0.80,
    )

