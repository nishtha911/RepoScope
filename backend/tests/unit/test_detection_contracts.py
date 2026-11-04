import pytest
from pydantic import ValidationError

from reposcope.contracts.detection import (
    DetectedEndpoint,
    DetectionEvidence,
    DetectionResult,
    make_endpoint_key,
)


def make_evidence(expression='app.get("/users")'):
    return DetectionEvidence(
        file_path="api.py",
        start_line=5,
        end_line=5,
        start_byte=100,
        end_byte=100 + len(expression.encode("utf-8")),
        expression=expression,
        rule_id="fastapi.route_decorator",
    )


def test_endpoint_key_is_deterministic_and_method_specific():
    first = make_endpoint_key("api.py", 100, "GET")

    assert first == make_endpoint_key("api.py", 100, "GET")
    assert first != make_endpoint_key("api.py", 100, "POST")
    assert first != make_endpoint_key("other.py", 100, "GET")


def test_endpoint_accepts_matching_identity():
    endpoint = DetectedEndpoint(
        key=make_endpoint_key("api.py", 100, "GET"),
        module_key="existing-module-key",
        handler_key="existing-handler-key",
        framework="fastapi",
        receiver="app",
        method="GET",
        path="/users",
        evidence=make_evidence(),
    )

    assert endpoint.path == "/users"
    assert endpoint.method == "GET"


def test_endpoint_rejects_mismatched_identity():
    with pytest.raises(ValidationError, match="Endpoint key"):
        DetectedEndpoint(
            key=make_endpoint_key("api.py", 100, "POST"),
            module_key="existing-module-key",
            handler_key="existing-handler-key",
            framework="fastapi",
            receiver="app",
            method="GET",
            path="/users",
            evidence=make_evidence(),
        )


def test_evidence_uses_utf8_byte_length():
    evidence = make_evidence('app.get("/café")')

    assert evidence.end_byte - evidence.start_byte == len(
        evidence.expression.encode("utf-8")
    )


def test_evidence_rejects_wrong_byte_length():
    with pytest.raises(ValidationError, match="byte length"):
        DetectionEvidence(
            file_path="api.py",
            start_line=1,
            end_line=1,
            start_byte=0,
            end_byte=1,
            expression='app.get("/users")',
            rule_id="fastapi.route_decorator",
        )


def test_empty_detection_result():
    result = DetectionResult()

    assert result.endpoints == ()
    assert result.models == ()
    assert result.edges == ()
    assert result.gaps == ()