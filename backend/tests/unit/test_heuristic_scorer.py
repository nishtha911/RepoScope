"""Unit tests for Day 12 heuristic feature scorer and priority calculation."""
import math
import pytest
from pydantic import ValidationError

from reposcope.contracts.edge import Edge
from reposcope.contracts.finding import Finding
from reposcope.contracts.symbol import Symbol
from reposcope.recommendations.detectors import (
    CandidateDataset,
    CandidateEvidence,
    CandidateSymbol,
    detect_candidates,
)
from reposcope.recommendations.features import (
    FindingFeatures,
    extract_features,
)
from reposcope.recommendations.scorer import (
    HeuristicScorer,
    ScorerConfig,
    compute_priority_score,
)


# Helper builders
def make_finding(category: str = "UNTESTED_HOTSPOT", symbol_id: int = 1) -> Finding:
    return Finding(
        snapshot_id=1,
        symbol_id=symbol_id,
        file_id=1,
        category=category,
        title=f"Sample title for {category}",
        description=f"Sample description for {category}",
    )


def make_symbol(
    symbol_id: int = 1,
    kind: str = "function",
    complexity: int | None = None,
    start_line: int = 1,
    end_line: int = 25,
) -> CandidateSymbol:
    return CandidateSymbol(
        symbol=Symbol(
            id=symbol_id,
            file_id=1,
            name=f"sym_{symbol_id}",
            kind=kind,
            start_line=start_line,
            end_line=end_line,
        ),
        filepath="app/main.py",
        is_test=False,
        cyclomatic_complexity=complexity,
        complexity_policy="python_v1" if complexity is not None else None,
        documentation_known=True,
    )


class TestPriorityScoreFormula:
    """Tests for score = (impact * likelihood) / effort * confidence."""

    def test_basic_formula_calculation(self):
        # (10.0 * 0.8) / 2.0 * 0.9 = 8.0 / 2.0 * 0.9 = 4.0 * 0.9 = 3.6
        score = compute_priority_score(
            impact=10.0,
            likelihood=0.8,
            effort=2.0,
            confidence=0.9,
        )
        assert score == pytest.approx(3.6, rel=1e-4)

    def test_zero_impact_yields_zero_score(self):
        score = compute_priority_score(
            impact=0.0,
            likelihood=0.8,
            effort=2.0,
            confidence=0.9,
        )
        assert score == 0.0

    def test_zero_confidence_yields_zero_score(self):
        score = compute_priority_score(
            impact=8.0,
            likelihood=0.8,
            effort=2.0,
            confidence=0.0,
        )
        assert score == 0.0

    def test_category_multiplier_scales_proportionally(self):
        base_score = compute_priority_score(
            impact=5.0,
            likelihood=0.7,
            effort=1.5,
            confidence=0.9,
            category_multiplier=1.0,
        )
        boosted = compute_priority_score(
            impact=5.0,
            likelihood=0.7,
            effort=1.5,
            confidence=0.9,
            category_multiplier=1.5,
        )
        assert boosted == pytest.approx(base_score * 1.5, rel=1e-4)

    def test_effort_must_be_strictly_positive(self):
        with pytest.raises(ValueError, match="effort must be strictly positive"):
            compute_priority_score(impact=5.0, likelihood=0.8, effort=0.0, confidence=0.9)

        with pytest.raises(ValueError, match="effort must be strictly positive"):
            compute_priority_score(impact=5.0, likelihood=0.8, effort=-1.5, confidence=0.9)

    def test_negative_impact_raises(self):
        with pytest.raises(ValueError, match="impact cannot be negative"):
            compute_priority_score(impact=-1.0, likelihood=0.5, effort=1.0, confidence=0.9)

    @pytest.mark.parametrize("invalid_likelihood", [-0.1, 1.01, 2.5])
    def test_invalid_likelihood_raises(self, invalid_likelihood):
        with pytest.raises(ValueError, match="likelihood must be between 0.0 and 1.0"):
            compute_priority_score(impact=5.0, likelihood=invalid_likelihood, effort=1.0, confidence=0.9)

    @pytest.mark.parametrize("invalid_confidence", [-0.01, 1.05, 10.0])
    def test_invalid_confidence_raises(self, invalid_confidence):
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            compute_priority_score(impact=5.0, likelihood=0.8, effort=1.0, confidence=invalid_confidence)

    @pytest.mark.parametrize("val", [float("nan"), float("inf"), float("-inf")])
    def test_nan_or_inf_raises(self, val):
        with pytest.raises(ValueError, match="must be a finite number"):
            compute_priority_score(impact=val, likelihood=0.5, effort=1.0, confidence=0.9)


class TestFeatureExtraction:
    """Tests for extract_features across finding categories."""

    def test_untested_hotspot_features(self):
        finding = make_finding(category="UNTESTED_HOTSPOT", symbol_id=101)
        evidence = CandidateEvidence(
            category="UNTESTED_HOTSPOT",
            symbol_id=101,
            measured_value=8,
            related_symbol_ids=(1, 2, 3, 4, 5, 6, 7, 8),
        )
        sym = make_symbol(symbol_id=101, complexity=12, start_line=1, end_line=50)

        feats = extract_features(finding, evidence=evidence, symbol_context=sym)
        assert feats.category == "UNTESTED_HOTSPOT"
        assert feats.fan_in == 8
        assert feats.cyclomatic_complexity == 12
        assert feats.impact > 5.0  # Increased due to fan-in > 5
        assert 0.7 <= feats.likelihood <= 0.95
        assert feats.effort >= 1.0
        assert feats.confidence == 0.95

    def test_complexity_hotspot_features(self):
        finding = make_finding(category="COMPLEXITY_HOTSPOT", symbol_id=202)
        evidence = CandidateEvidence(
            category="COMPLEXITY_HOTSPOT",
            symbol_id=202,
            measured_value=20,
            threshold=10,
        )

        feats = extract_features(finding, evidence=evidence)
        assert feats.category == "COMPLEXITY_HOTSPOT"
        assert feats.cyclomatic_complexity == 20
        # High complexity yields higher impact and effort
        assert feats.impact >= 8.0
        assert feats.effort >= 5.0
        assert feats.confidence == 0.95

    def test_api_doc_gap_features(self):
        finding = make_finding(category="API_DOC_GAP", symbol_id=303)
        evidence = CandidateEvidence(
            category="API_DOC_GAP",
            symbol_id=303,
            related_symbol_ids=(101,),
        )

        feats = extract_features(finding, evidence=evidence)
        assert feats.category == "API_DOC_GAP"
        assert feats.is_endpoint is True
        assert feats.missing_docstring is True
        assert feats.effort == 1.0  # Quick win
        assert feats.confidence == 0.90

    def test_fallback_features_for_unknown_category(self):
        finding = make_finding(category="CUSTOM_CODE_SMELL", symbol_id=404)
        feats = extract_features(finding)
        assert feats.category == "CUSTOM_CODE_SMELL"
        assert feats.impact > 0
        assert feats.effort > 0
        assert 0 <= feats.confidence <= 1


class TestHeuristicScorer:
    """Tests for HeuristicScorer scoring and ranking."""

    def test_score_single_finding_populates_contract(self):
        scorer = HeuristicScorer()
        finding = make_finding(category="UNTESTED_HOTSPOT", symbol_id=10)
        evidence = CandidateEvidence(
            category="UNTESTED_HOTSPOT",
            symbol_id=10,
            measured_value=6,
            related_symbol_ids=(1, 2, 3, 4, 5, 6),
        )

        scored_finding, features = scorer.score_finding(finding, evidence=evidence)

        # Scored finding contract validity
        assert scored_finding.score is not None
        assert scored_finding.score > 0
        assert scored_finding.confidence is not None
        assert 0 <= scored_finding.confidence <= 1
        assert scored_finding.id == finding.id
        assert scored_finding.category == finding.category

        # Confirm Finding model validation succeeds
        Finding.model_validate(scored_finding.model_dump())

    def test_category_multiplier_config_applies(self):
        scorer_neutral = HeuristicScorer(ScorerConfig())
        scorer_boosted = HeuristicScorer(
            ScorerConfig(category_multipliers={"API_DOC_GAP": 1.5})
        )

        finding = make_finding(category="API_DOC_GAP", symbol_id=20)
        scored_neutral, _ = scorer_neutral.score_finding(finding)
        scored_boosted, _ = scorer_boosted.score_finding(finding)

        assert scored_neutral.score is not None
        assert scored_boosted.score is not None
        assert scored_boosted.score == pytest.approx(scored_neutral.score * 1.5, rel=1e-4)

    def test_rank_findings_sorts_descending_by_score(self):
        scorer = HeuristicScorer()
        f1 = make_finding(category="UNTESTED_HOTSPOT", symbol_id=1)
        f2 = make_finding(category="API_DOC_GAP", symbol_id=2)
        f3 = make_finding(category="COMPLEXITY_HOTSPOT", symbol_id=3)

        ev1 = CandidateEvidence(category="UNTESTED_HOTSPOT", symbol_id=1, measured_value=25)
        ev2 = CandidateEvidence(category="API_DOC_GAP", symbol_id=2)
        ev3 = CandidateEvidence(category="COMPLEXITY_HOTSPOT", symbol_id=3, measured_value=11)

        scored1, _ = scorer.score_finding(f1, ev1)
        scored2, _ = scorer.score_finding(f2, ev2)
        scored3, _ = scorer.score_finding(f3, ev3)

        ranked = scorer.rank_findings([scored2, scored1, scored3])
        scores = [f.score for f in ranked]
        assert scores == sorted(scores, reverse=True)


class TestScorerCandidateReportIntegration:
    """Integration test: detect_candidates -> score_report -> ranked results."""

    def test_end_to_end_scoring_of_detector_output(self):
        # Build candidate dataset with a mix of UNTESTED_HOTSPOT, COMPLEXITY_HOTSPOT, API_DOC_GAP
        symbols = [
            # Hotspot function called by 6 callers
            CandidateSymbol(
                symbol=Symbol(id=1, file_id=1, name="core_calc", kind="function", start_line=1, end_line=30),
                filepath="core.py", is_test=False, cyclomatic_complexity=5,
                complexity_policy="python_v1", documentation_known=True,
            ),
            # Callers
            *[
                CandidateSymbol(
                    symbol=Symbol(id=i, file_id=1, name=f"caller_{i}", kind="function", start_line=i*10, end_line=i*10+5),
                    filepath="core.py", is_test=False, documentation_known=True,
                )
                for i in range(2, 8)
            ],
            # High complexity function
            CandidateSymbol(
                symbol=Symbol(id=20, file_id=1, name="complex_method", kind="method", start_line=100, end_line=180),
                filepath="core.py", is_test=False, cyclomatic_complexity=22,
                complexity_policy="python_v1", documentation_known=True,
            ),
            # Endpoint with missing docstring
            CandidateSymbol(
                symbol=Symbol(id=30, file_id=2, name="get_users", kind="endpoint", start_line=200, end_line=205),
                filepath="api.py", is_test=False, documentation_known=True,
            ),
            # Handler for endpoint with no docstring
            CandidateSymbol(
                symbol=Symbol(id=31, file_id=2, name="handle_get_users", kind="function", start_line=206, end_line=220),
                filepath="api.py", is_test=False, docstring="", documentation_known=True,
            ),
        ]

        edges = [
            # 6 calls to core_calc
            *[Edge(source_symbol_id=i, target_symbol_id=1, kind="CALLS", confidence=1.0) for i in range(2, 8)],
            # Endpoint calls handler
            Edge(source_symbol_id=30, target_symbol_id=31, kind="CALLS", confidence=1.0),
        ]

        dataset = CandidateDataset(
            repo_id=10,
            snapshot_id=42,
            symbols=tuple(symbols),
            edges=tuple(edges),
            test_links_complete=True,
        )

        # 1. Run Day 11 candidate detection
        report = detect_candidates(dataset)
        assert len(report.findings) >= 3
        # Before scoring, scores are None
        for f in report.findings:
            assert f.score is None

        # 2. Run Day 12 heuristic feature scoring
        scorer = HeuristicScorer()
        scored_report = scorer.score_report(report, dataset=dataset)

        assert scored_report.repo_id == 10
        assert scored_report.snapshot_id == 42
        assert len(scored_report.findings) == len(report.findings)
        assert len(scored_report.features) == len(report.findings)

        # All findings must have valid scores and confidences
        for f in scored_report.findings:
            assert f.score is not None
            assert f.score > 0
            assert f.confidence is not None
            assert 0 <= f.confidence <= 1

        # Findings must be sorted strictly descending by priority score
        scores = [f.score for f in scored_report.findings]
        assert scores == sorted(scores, reverse=True)

        # Features contain corresponding details
        for feat in scored_report.features:
            assert feat.impact > 0
            assert feat.likelihood > 0
            assert feat.effort > 0
            assert feat.confidence > 0
