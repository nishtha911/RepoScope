import pytest
from pydantic import ValidationError

from reposcope.contracts.pr_report import PRImpactReport
from reposcope.contracts.repository import Repository


def test_repository_contract_valid():
    repo = Repository(
        id=1,
        url="https://github.com/fastapi/fastapi",
        name="fastapi/fastapi",
        default_branch="main",
        status="ready",
        head_sha="a" * 40,
    )
    assert repo.id == 1
    assert str(repo.url) == "https://github.com/fastapi/fastapi"
    assert repo.name == "fastapi/fastapi"
    assert repo.status == "ready"


def test_repository_contract_invalid_name():
    with pytest.raises(ValidationError):
        Repository(
            url="https://github.com/fastapi/fastapi",
            name="invalidname",
        )


def test_pr_impact_report_valid():
    report = PRImpactReport(
        pr_url="https://github.com/fastapi/fastapi/pull/123",
        risk_level="LOW",
        risk_score=0.12,
        files_changed_count=2,
        impacted_symbols_count=5,
        affected_endpoints_count=1,
        impacted_tests_count=3,
        summary="Minor change",
    )
    assert report.risk_level == "LOW"
    assert report.risk_score == 0.12


def test_pr_impact_report_invalid_risk_level():
    with pytest.raises(ValidationError):
        PRImpactReport(
            pr_url="https://github.com/fastapi/fastapi/pull/123",
            risk_level="VERY_HIGH",
            risk_score=0.12,
            files_changed_count=2,
            impacted_symbols_count=5,
            affected_endpoints_count=1,
            impacted_tests_count=3,
        )
