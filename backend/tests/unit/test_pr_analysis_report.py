"""Unit tests for structured pr_analyses JSON report and grounded executive review summarizer."""
import asyncio
from dataclasses import replace
import importlib.util
from pathlib import Path
import pytest
import networkx as nx

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from reposcope.contracts.pr_report import PRAnalysisReport
from reposcope.contracts.diff import (
    DiffHunk,
    DiffLine,
    DiffPatch,
    FileDiff,
    SymbolChange,
    SymbolDiffReport,
    SymbolVersion,
)
from reposcope.impact.blast_radius import blast_radius
from reposcope.impact.risk_engine import RiskSnapshot, assess_pr_risk
from reposcope.impact.report import (
    PRReportFacts,
    ExecutiveReviewPlan,
    ExecutiveReviewSummarizer,
    extract_pr_facts,
    deterministic_executive_summary,
    validate_summary_grounding,
    build_pr_analysis_report,
    generate_pr_analysis_report,
)
from reposcope.models.repository import Repository
from reposcope.models.pr_analysis import (
    PRAnalysisRecord,
    save_pr_analysis,
    get_pr_analysis,
)


def version(key, kind="function"):
    return SymbolVersion(
        path="app.py",
        local_key=key,
        name="f",
        qualname="f",
        kind=kind,
        start_line=1,
        end_line=2,
        content_start_line=1,
        content_end_line=2,
    )


def sample_diff_report():
    before = version("old")
    after = version("new")
    file = FileDiff(
        base_path="app.py",
        head_path="app.py",
        status="MODIFIED",
        hunks=(
            DiffHunk(
                base_start=2,
                base_count=1,
                head_start=2,
                head_count=1,
                lines=(
                    DiffLine(kind="-", text=" return 1\n", base_line=2),
                    DiffLine(kind="+", text=" return 2\n", head_line=2),
                ),
            ),
        ),
    )
    return SymbolDiffReport(
        patch=DiffPatch(files=(file,)),
        changes=(
            SymbolChange(
                classification="BODY_CHANGED",
                base_symbol=before,
                head_symbol=after,
            ),
        ),
        base_revision="a" * 40,
        head_revision="b" * 40,
    )


def sample_context(side, linked=False):
    snap = 10 if side == "base" else 20
    g = nx.MultiDiGraph(
        repository_id=1,
        snapshot_id=snap,
        commit_sha=("a" if side == "base" else "b") * 40,
    )
    g.add_node(
        1,
        repository_id=1,
        snapshot_id=snap,
        file_id=1,
        file_path="app.py",
        name="f",
        qualname="f",
        kind="function",
        start_line=1,
        end_line=2,
    )
    g.add_node(
        2,
        repository_id=1,
        snapshot_id=snap,
        file_id=2,
        file_path="test_app.py",
        name="test_f",
        qualname="test_f",
        kind="function",
        start_line=1,
        end_line=2,
    )
    if linked:
        g.add_edge(1, 2, key=1, edge_id=1, kind="TESTED_BY", confidence=1)
    return RiskSnapshot(
        g,
        blast_radius(g, 1, snap, [1]),
        {"old" if side == "base" else "new": 1},
        symbol_roles={1: "production", 2: "test"},
        test_links_complete=True,
        sensitive_symbol_ids=(),
        sensitivity_complete=True,
    )


def sample_assessment(linked=False):
    diff = sample_diff_report()
    contexts = {
        "base": sample_context("base", linked=linked),
        "head": sample_context("head", linked=linked),
    }
    return assess_pr_risk(
        diff,
        1,
        contexts,
        base_complexities={"old": 2},
        head_complexities={"new": 4},
    )


def test_extract_pr_facts():
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)
    facts = extract_pr_facts(
        assessment,
        diff_report=diff,
        pr_url="https://github.com/owner/repo/pull/42",
        pr_number=42,
    )

    assert facts.repository_id == 1
    assert facts.pr_number == 42
    assert facts.pr_url == "https://github.com/owner/repo/pull/42"
    assert facts.files_changed_count == 1
    assert facts.changed_lines_count == 2
    assert facts.modified_symbols_count == 1
    assert facts.risk_status == "COMPLETE"
    assert facts.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert facts.untested_modified_symbols_count == 1
    assert facts.maximum_complexity_increase == 2


def test_deterministic_executive_summary_is_grounded():
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)
    facts = extract_pr_facts(assessment, diff_report=diff, pr_number=42)

    summary = deterministic_executive_summary(facts)
    assert summary.source == "deterministic"
    assert "Pull request analysis concluded" in summary.text
    assert f"diff modifies {facts.changed_lines_count} lines across {facts.files_changed_count} files" in summary.text.lower()
    assert f"{facts.untested_modified_symbols_count} modified production callables lack direct static test coverage" in summary.text
    assert "maximum detected callable cyclomatic complexity increase is +2" in summary.text.lower()
    assert summary.feature_citations["files_changed_count"] == 1
    assert summary.feature_citations["changed_lines_count"] == 2


def test_validate_summary_grounding_rejects_hallucinations():
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)
    facts = extract_pr_facts(assessment, diff_report=diff, pr_number=42)

    # Valid plan
    valid_plan = ExecutiveReviewPlan(
        headline="PR #42 impact assessment.",
        risk_narrative="Risk level evaluated as LOW.",
        blast_radius_narrative="Modified 1 file and 2 changed lines.",
        test_gap_narrative="1 untested modified callable detected.",
        cited_metrics={
            "files_changed_count": 1,
            "changed_lines_count": 2,
            "modified_symbols_count": 1,
            "impacted_symbols_count": 1,
            "affected_endpoints_count": 0,
            "untested_modified_symbols_count": 1,
        },
    )
    ok, err = validate_summary_grounding(valid_plan, facts)
    assert ok is True
    assert err is None

    # Invalid metric citation
    invalid_plan = ExecutiveReviewPlan(
        headline="PR impact.",
        risk_narrative="Risk level LOW.",
        blast_radius_narrative="Touches files.",
        test_gap_narrative="Test status.",
        cited_metrics={"files_changed_count": 99},  # Disagrees with facts (1)
    )
    ok, err = validate_summary_grounding(invalid_plan, facts)
    assert ok is False
    assert "disagrees with evidence" in err.lower()

    # Hallucinated number in text narrative
    hallucinated_plan = ExecutiveReviewPlan(
        headline="PR touches 500 files.",  # Fabricated 500
        risk_narrative="Severe danger.",
        blast_radius_narrative="Critical.",
        test_gap_narrative="None.",
        cited_metrics={"files_changed_count": 1},
    )
    ok, err = validate_summary_grounding(hallucinated_plan, facts)
    assert ok is False
    assert "unverified numeric claim" in err.lower()


def test_executive_review_summarizer_deterministic_fallback():
    summarizer = ExecutiveReviewSummarizer(client=None)
    diff = sample_diff_report()
    assessment = sample_assessment(linked=True)
    facts = extract_pr_facts(assessment, diff_report=diff, pr_number=10)

    summary = asyncio.run(summarizer.summarize(facts))
    assert summary.source == "deterministic"
    assert summary.degraded_reason == "LLM_NOT_CONFIGURED"
    assert "All modified production callables have linked static test associations." in summary.text


def test_executive_review_summarizer_with_mock_llm():
    class MockLLMResponse:
        def __init__(self, data):
            self.data = data

    class MockLLMClient:
        async def generate(self, request):
            return MockLLMResponse(
                {
                    "headline": "PR #42 Executive Review.",
                    "risk_narrative": "Deterministic risk evaluated as LOW.",
                    "blast_radius_narrative": "Changes touch 1 file and 2 lines.",
                    "test_gap_narrative": "1 symbol lacks static test coverage.",
                    "cited_metrics": {
                        "files_changed_count": 1,
                        "changed_lines_count": 2,
                        "modified_symbols_count": 1,
                        "impacted_symbols_count": 1,
                        "affected_endpoints_count": 0,
                        "untested_modified_symbols_count": 1,
                    },
                }
            )

    summarizer = ExecutiveReviewSummarizer(client=MockLLMClient())
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)
    facts = extract_pr_facts(assessment, diff_report=diff, pr_number=42)

    summary = asyncio.run(summarizer.summarize(facts))
    assert summary.source == "llm_grounded"
    assert summary.degraded_reason is None
    assert "PR #42 Executive Review." in summary.text
    assert summary.feature_citations["files_changed_count"] == 1


def test_executive_review_summarizer_degrades_on_hallucinated_llm_output():
    class MockHallucinatingClient:
        async def generate(self, request):
            class Resp:
                data = {
                    "headline": "PR touches 999 files.",
                    "risk_narrative": "Extreme risk.",
                    "blast_radius_narrative": "Widespread failure.",
                    "test_gap_narrative": "None.",
                    "cited_metrics": {"files_changed_count": 999},
                }
            return Resp()

    summarizer = ExecutiveReviewSummarizer(client=MockHallucinatingClient())
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)
    facts = extract_pr_facts(assessment, diff_report=diff, pr_number=42)

    summary = asyncio.run(summarizer.summarize(facts))
    assert summary.source == "deterministic"
    assert "UNGROUNDED_MODEL_CLAIM" in summary.degraded_reason


def test_build_pr_analysis_report_json_roundtrip():
    diff = sample_diff_report()
    assessment = sample_assessment(linked=False)

    report = build_pr_analysis_report(
        assessment,
        diff_report=diff,
        pr_url="https://github.com/owner/repo/pull/42",
        pr_number=42,
    )

    assert report.report_version == "pr-analysis-v1"
    assert report.repository_id == 1
    assert report.pr_number == 42
    assert report.metrics.files_changed_count == 1
    assert report.metrics.changed_lines_count == 2
    assert len(report.untested_modified_symbols) == 1
    assert report.untested_modified_symbols[0]["symbol_id"] == 1

    # Verify JSON roundtrip
    json_str = report.model_dump_json()
    reconstructed = PRAnalysisReport.model_validate_json(json_str)
    assert reconstructed.repository_id == report.repository_id
    assert reconstructed.executive_summary == report.executive_summary
    assert reconstructed.metrics == report.metrics


def test_sqlite_persistence_and_retrieval():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        Repository.__table__.create(conn)
        PRAnalysisRecord.__table__.create(conn)

    with Session(engine) as session:
        repo = Repository(id=1, full_name="owner/repo", remote_url="https://github.com/owner/repo")
        session.add(repo)
        session.commit()

        diff = sample_diff_report()
        assessment = sample_assessment(linked=False)
        report = build_pr_analysis_report(
            assessment,
            diff_report=diff,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_number=42,
        )

        record = save_pr_analysis(session, report)
        session.commit()

        assert record.id > 0
        assert record.pr_number == 42
        assert record.repository_id == 1
        assert record.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert record.report_json["metrics"]["files_changed_count"] == 1

        # Query back
        fetched = get_pr_analysis(session, 1, pr_number=42)
        assert fetched is not None
        assert fetched.id == record.id
        assert fetched.summary == record.summary
        assert fetched.report_json["report_version"] == "pr-analysis-v1"

        # Query by ID
        by_id = get_pr_analysis(session, 1, analysis_id=record.id)
        assert by_id is not None
        assert by_id.id == record.id

    engine.dispose()
