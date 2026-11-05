import pytest
from pydantic import ValidationError

from reposcope.contracts.test_linking import (
    TestLink,
    TestLinkingResult,
)


def test_direct_link_accepts_one_call_hop():
    link = TestLink(
        implementation_key="implementation",
        test_key="test",
        rule="direct_call",
        confidence=1.0,
        call_path=("test", "implementation"),
        reference_keys=("call-site-1",),
    )

    assert link.call_path == ("test", "implementation")


def test_two_hop_link_retains_intermediate_symbol():
    link = TestLink(
        implementation_key="implementation",
        test_key="test",
        rule="two_hop_call",
        confidence=0.8,
        call_path=("test", "helper", "implementation"),
        reference_keys=("call-site-1", "call-site-2"),
    )

    assert link.call_path[1] == "helper"
    assert len(link.reference_keys) == 2


def test_naming_link_has_no_call_evidence():
    link = TestLink(
        implementation_key="implementation",
        test_key="test",
        rule="name_match",
        confidence=0.5,
    )

    assert link.call_path == ()
    assert link.reference_keys == ()


def test_naming_link_rejects_claimed_call_path():
    with pytest.raises(ValidationError, match="Naming-only"):
        TestLink(
            implementation_key="implementation",
            test_key="test",
            rule="name_match",
            confidence=0.5,
            call_path=("test", "implementation"),
        )


def test_two_hop_link_rejects_missing_reference():
    with pytest.raises(ValidationError, match="reference key"):
        TestLink(
            implementation_key="implementation",
            test_key="test",
            rule="two_hop_call",
            confidence=0.8,
            call_path=("test", "helper", "implementation"),
            reference_keys=("call-site-1",),
        )


def test_link_rejects_self_link():
    with pytest.raises(ValidationError, match="itself"):
        TestLink(
            implementation_key="test",
            test_key="test",
            rule="name_match",
            confidence=0.5,
        )


def test_link_rejects_reversed_call_path():
    with pytest.raises(ValidationError, match="start at the test"):
        TestLink(
            implementation_key="implementation",
            test_key="test",
            rule="direct_call",
            confidence=1.0,
            call_path=("implementation", "test"),
            reference_keys=("call-site-1",),
        )


def test_empty_result():
    result = TestLinkingResult()

    assert result.links == ()
    assert result.edges == ()
    assert result.gaps == ()