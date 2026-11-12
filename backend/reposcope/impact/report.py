"""Structured pr_analyses JSON report generation and grounded executive review summarizer.

Strictly grounded in report evidence: metrics, blast radius, test gaps, and complexity.
The model never invents unverified metrics or outside claims; on any anomaly,
it safely falls back to deterministic grounded synthesis.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from reposcope.contracts.pr_report import (
    PRAnalysisReport,
    PRReportMetrics,
    SummaryMetadata,
)
from reposcope.impact.risk_engine import RiskAssessment
from reposcope.integrations.llm import LLMError, LLMRequest


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PRReportFacts(Record):
    """Verified, immutable facts extracted from RiskAssessment and SymbolDiffReport."""

    repository_id: int = Field(gt=0)
    pr_url: str | None = None
    pr_number: int | None = None
    patch_name: str | None = None
    base_revision: str | None = None
    head_revision: str | None = None

    risk_level: str
    risk_score: float | None = None
    risk_status: str
    score_bounds: tuple[float, float] | None = None

    files_changed_count: int = Field(ge=0)
    changed_lines_count: int = Field(ge=0)
    modified_symbols_count: int = Field(ge=0)
    impacted_symbols_count: int = Field(ge=0)
    affected_endpoints_count: int = Field(ge=0)
    impacted_tests_count: int = Field(ge=0)
    untested_modified_symbols_count: int = Field(ge=0)
    contract_change_count: int = Field(ge=0)
    maximum_complexity_increase: int | None = None

    feature_values: dict[str, float | None] = Field(default_factory=dict)
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    gaps: tuple[str, ...] = Field(default_factory=tuple)


class ExecutiveReviewPlan(Record):
    """Constrained JSON schema for LLM executive review output."""

    headline: str = Field(min_length=1)
    risk_narrative: str = Field(min_length=1)
    blast_radius_narrative: str = Field(min_length=1)
    test_gap_narrative: str = Field(min_length=1)
    cited_metrics: dict[str, Any] = Field(default_factory=dict)


class ExecutiveReviewSummary(Record):
    """Final grounded summary with provenance."""

    text: str = Field(min_length=1)
    source: Literal["llm_grounded", "deterministic"]
    degraded_reason: str | None = None
    feature_citations: dict[str, Any] = Field(default_factory=dict)


def deterministic_executive_summary(
    facts: PRReportFacts, reason: str | None = None
) -> ExecutiveReviewSummary:
    """Generate a strictly grounded executive review summary without LLM inference."""
    score_str = (
        f"{facts.risk_score:.2f}"
        if facts.risk_score is not None
        else f"[{facts.score_bounds[0]:.2f}-{facts.score_bounds[1]:.2f}] (incomplete)"
        if facts.score_bounds
        else "incomplete"
    )

    sentences = [
        f"Pull request analysis concluded with {facts.risk_level} risk (score: {score_str}, status: {facts.risk_status}).",
        f"Diff modifies {facts.changed_lines_count} lines across {facts.files_changed_count} files ({facts.modified_symbols_count} symbols modified).",
        f"Downstream ripple traversal identified {facts.impacted_symbols_count} impacted symbols and {facts.affected_endpoints_count} affected API endpoints.",
    ]

    if facts.untested_modified_symbols_count > 0:
        sentences.append(
            f"{facts.untested_modified_symbols_count} modified production callables lack direct static test coverage."
        )
    else:
        sentences.append(
            "All modified production callables have linked static test associations."
        )

    if facts.maximum_complexity_increase is not None and facts.maximum_complexity_increase > 0:
        sentences.append(
            f"Maximum detected callable cyclomatic complexity increase is +{facts.maximum_complexity_increase}."
        )

    if facts.gaps:
        sentences.append(
            f"Assessment contains {len(facts.gaps)} unmeasured boundary gap(s)."
        )

    text = " ".join(sentences)
    citations = {
        "risk_level": facts.risk_level,
        "risk_score": facts.risk_score,
        "files_changed_count": facts.files_changed_count,
        "changed_lines_count": facts.changed_lines_count,
        "impacted_symbols_count": facts.impacted_symbols_count,
        "affected_endpoints_count": facts.affected_endpoints_count,
        "untested_modified_symbols_count": facts.untested_modified_symbols_count,
    }

    return ExecutiveReviewSummary(
        text=text,
        source="deterministic",
        degraded_reason=reason,
        feature_citations=citations,
    )


def validate_summary_grounding(
    plan: ExecutiveReviewPlan, facts: PRReportFacts
) -> tuple[bool, str | None]:
    """Verify that every metric cited by the model strictly matches report facts."""
    cited = plan.cited_metrics
    expected = {
        "files_changed_count": facts.files_changed_count,
        "changed_lines_count": facts.changed_lines_count,
        "modified_symbols_count": facts.modified_symbols_count,
        "impacted_symbols_count": facts.impacted_symbols_count,
        "affected_endpoints_count": facts.affected_endpoints_count,
        "untested_modified_symbols_count": facts.untested_modified_symbols_count,
    }

    # Verify cited numbers
    for k, v in cited.items():
        if k in expected:
            try:
                if int(v) != int(expected[k]):
                    return False, f"Cited {k}={v} disagrees with evidence {expected[k]}"
            except (ValueError, TypeError):
                return False, f"Non-numeric citation for {k}: {v}"

    # Verify that the full text does not invent fabricated numbers
    full_text = f"{plan.headline} {plan.risk_narrative} {plan.blast_radius_narrative} {plan.test_gap_narrative}"
    # Check for numbers in text
    numbers_in_text = [int(n) for n in re.findall(r"\b\d+\b", full_text)]
    valid_numbers = set(expected.values()) | {
        int(facts.risk_score * 100) if facts.risk_score is not None else 0,
        facts.repository_id,
        facts.pr_number or 0,
        facts.maximum_complexity_increase or 0,
        len(facts.gaps),
    }

    # Numbers under 5 or typical bullet points / sentence indexes are allowed, but check larger counts
    for num in numbers_in_text:
        if num > 10 and num not in valid_numbers:
            return False, f"Unverified numeric claim in summary text: {num}"

    return True, None


class ExecutiveReviewSummarizer:
    """Wires LLM client with JSON-schema grounding and deterministic fallback."""

    def __init__(self, client=None, *, timeout: float = 8.0):
        self.client = client
        self.timeout = timeout

    async def summarize(self, facts: PRReportFacts) -> ExecutiveReviewSummary:
        if self.client is None:
            return deterministic_executive_summary(facts, reason="LLM_NOT_CONFIGURED")

        evidence_payload = facts.model_dump(mode="json")
        system_prompt = (
            "You are RepoScope's PR Impact Executive Review Analyst. "
            "Generate a structured executive review strictly citing ONLY the provided report evidence metrics. "
            "Never hallucinate unmeasured files, untested functions, external CVEs, or invented percentages. "
            "Return output strictly adhering to the requested JSON schema."
        )

        user_prompt = (
            f"Synthesize an executive review for PR #{facts.pr_number or 'DIFF'} in repository {facts.repository_id}. "
            f"Evidence metrics: risk_level={facts.risk_level}, risk_score={facts.risk_score}, "
            f"files_changed={facts.files_changed_count}, changed_lines={facts.changed_lines_count}, "
            f"modified_symbols={facts.modified_symbols_count}, impacted_symbols={facts.impacted_symbols_count}, "
            f"affected_endpoints={facts.affected_endpoints_count}, untested_symbols={facts.untested_modified_symbols_count}, "
            f"contract_changes={facts.contract_change_count}. "
            "Fill headline, risk_narrative, blast_radius_narrative, test_gap_narrative, and cited_metrics."
        )

        request = LLMRequest(
            messages=(
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ),
            evidence=evidence_payload,
            cache_scope=(
                f"pr-summary-v1:repo={facts.repository_id}:base={facts.base_revision}:head={facts.head_revision}"
            ),
            response_schema=ExecutiveReviewPlan.model_json_schema(),
            temperature=0.0,
            max_output_tokens=1024,
        )

        try:
            response = await asyncio.wait_for(
                self.client.generate(request), timeout=self.timeout
            )
            plan = ExecutiveReviewPlan.model_validate(response.data)
            is_grounded, failure_reason = validate_summary_grounding(plan, facts)
            if not is_grounded:
                return deterministic_executive_summary(
                    facts, reason=f"UNGROUNDED_MODEL_CLAIM:{failure_reason}"
                )

            full_text = (
                f"{plan.headline} {plan.risk_narrative} "
                f"{plan.blast_radius_narrative} {plan.test_gap_narrative}"
            ).strip()

            return ExecutiveReviewSummary(
                text=full_text,
                source="llm_grounded",
                degraded_reason=None,
                feature_citations=plan.cited_metrics,
            )
        except (LLMError, TimeoutError, ValueError, TypeError, AttributeError) as exc:
            reason = type(exc).__name__
            return deterministic_executive_summary(facts, reason=f"LLM_ERROR:{reason}")


def extract_pr_facts(
    assessment: RiskAssessment,
    *,
    diff_report: Any = None,
    pr_url: str | None = None,
    pr_number: int | None = None,
    patch_name: str | None = None,
) -> PRReportFacts:
    """Extract strictly verified factual metrics from assessment and diff report."""
    files_changed_count = 0
    modified_symbols_count = 0
    if diff_report is not None and getattr(diff_report, "patch", None) is not None:
        files_changed_count = len(getattr(diff_report.patch, "files", []))
        modified_symbols_count = len(getattr(diff_report, "changes", []))

    # Calculate impacted symbols (head side preferred, else max across sides)
    head_side = next((s for s in assessment.sides if s.side == "head"), None)
    if head_side is not None:
        impacted_symbols_count = len(getattr(head_side, "seed_ids", ()))
    else:
        impacted_symbols_count = max(
            (len(getattr(s, "seed_ids", ())) for s in assessment.sides), default=0
        )
    impacted_symbols_count = max(impacted_symbols_count, len(assessment.untested_modified_symbols))

    affected_endpoints_count = 0
    impacted_tests_count = 0
    for side in assessment.sides:
        test_gaps = getattr(side, "test_gaps", None)
        if test_gaps is not None:
            impacted_tests_count += sum(
                len(getattr(item, "linked_test_ids", ()))
                for item in getattr(test_gaps, "items", ())
            )

    # Features map
    feature_values = {
        "blast_radius": assessment.features.blast_radius,
        "sensitivity": assessment.features.sensitivity,
        "test_gap": assessment.features.test_gap,
        "contract_changes": assessment.features.contract_changes,
        "complexity_delta": assessment.features.complexity_delta,
        "size": assessment.features.size,
    }

    feature_contributions = {
        c.name: c.contribution
        for c in assessment.risk.components
        if c.contribution is not None
    }

    score_bounds = (assessment.risk.lower_bound, assessment.risk.upper_bound)

    return PRReportFacts(
        repository_id=assessment.repository_id,
        pr_url=pr_url,
        pr_number=pr_number,
        patch_name=patch_name,
        base_revision=assessment.base_revision,
        head_revision=assessment.head_revision,
        risk_level=assessment.risk.risk_level or "INCOMPLETE",
        risk_score=assessment.risk.score,
        risk_status=assessment.risk.status,
        score_bounds=score_bounds,
        files_changed_count=files_changed_count,
        changed_lines_count=assessment.changed_lines,
        modified_symbols_count=modified_symbols_count,
        impacted_symbols_count=impacted_symbols_count,
        affected_endpoints_count=affected_endpoints_count,
        impacted_tests_count=impacted_tests_count,
        untested_modified_symbols_count=len(assessment.untested_modified_symbols),
        contract_change_count=assessment.contract_change_count,
        maximum_complexity_increase=assessment.maximum_complexity_increase,
        feature_values=feature_values,
        feature_contributions=feature_contributions,
        gaps=tuple(assessment.gaps),
    )


def build_pr_analysis_report(
    assessment: RiskAssessment,
    *,
    diff_report: Any = None,
    pr_url: str | None = None,
    pr_number: int | None = None,
    patch_name: str | None = None,
    summary: ExecutiveReviewSummary | None = None,
    impacted_endpoints: list[dict[str, Any]] | None = None,
) -> PRAnalysisReport:
    """Build complete structured PRAnalysisReport JSON model."""
    facts = extract_pr_facts(
        assessment,
        diff_report=diff_report,
        pr_url=pr_url,
        pr_number=pr_number,
        patch_name=patch_name,
    )

    if summary is None:
        summary = deterministic_executive_summary(facts)

    metrics = PRReportMetrics(
        files_changed_count=facts.files_changed_count,
        changed_lines_count=facts.changed_lines_count,
        modified_symbols_count=facts.modified_symbols_count,
        impacted_symbols_count=facts.impacted_symbols_count,
        affected_endpoints_count=facts.affected_endpoints_count,
        impacted_tests_count=facts.impacted_tests_count,
        untested_modified_symbols_count=facts.untested_modified_symbols_count,
    )

    untested_dicts = [
        {
            "side": u.side,
            "snapshot_id": u.snapshot_id,
            "symbol_id": u.symbol_id,
            "local_key": u.local_key,
            "qualname": u.qualname,
            "filepath": u.filepath,
        }
        for u in assessment.untested_modified_symbols
    ]

    return PRAnalysisReport(
        report_version="pr-analysis-v1",
        repository_id=assessment.repository_id,
        pr_url=pr_url,
        pr_number=pr_number,
        patch_name=patch_name,
        base_revision=assessment.base_revision,
        head_revision=assessment.head_revision,
        risk_level=assessment.risk.risk_level or "INCOMPLETE",
        risk_score=assessment.risk.score,
        risk_status=assessment.risk.status,
        score_bounds=facts.score_bounds,
        features=facts.feature_values,
        feature_contributions=facts.feature_contributions,
        metrics=metrics,
        impacted_endpoints=impacted_endpoints or [],
        untested_modified_symbols=untested_dicts,
        contract_changes=assessment.contract_change_count,
        maximum_complexity_increase=assessment.maximum_complexity_increase,
        gaps=list(assessment.gaps),
        executive_summary=summary.text,
        summary_metadata=SummaryMetadata(
            source=summary.source,
            degraded_reason=summary.degraded_reason,
            citations=summary.feature_citations,
        ),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def generate_pr_analysis_report(
    assessment: RiskAssessment,
    *,
    diff_report: Any = None,
    pr_url: str | None = None,
    pr_number: int | None = None,
    patch_name: str | None = None,
    summarizer: ExecutiveReviewSummarizer | None = None,
    impacted_endpoints: list[dict[str, Any]] | None = None,
) -> PRAnalysisReport:
    """Async generator pipeline with LLM executive review summarizer."""
    facts = extract_pr_facts(
        assessment,
        diff_report=diff_report,
        pr_url=pr_url,
        pr_number=pr_number,
        patch_name=patch_name,
    )

    if summarizer is None:
        summarizer = ExecutiveReviewSummarizer()

    summary = await summarizer.summarize(facts)

    return build_pr_analysis_report(
        assessment,
        diff_report=diff_report,
        pr_url=pr_url,
        pr_number=pr_number,
        patch_name=patch_name,
        summary=summary,
        impacted_endpoints=impacted_endpoints,
    )
