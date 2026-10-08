import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from reposcope.contracts.api import ErrorResponse
from reposcope.main import (
    HTTP_ERROR_CODES, http_exception_handler, unhandled_exception_handler,
)


@pytest.mark.parametrize("status,code", [
    (400, "BAD_REQUEST"), (401, "UNAUTHORIZED"), (403, "FORBIDDEN"),
    (404, "NOT_FOUND"), (405, "METHOD_NOT_ALLOWED"), (409, "CONFLICT"),
    (422, "VALIDATION_ERROR"), (429, "RATE_LIMITED"),
    (500, "INTERNAL_ERROR"), (501, "NOT_IMPLEMENTED"),
])
def test_documented_http_error_mapping(status, code):
    assert HTTP_ERROR_CODES[status] == code
    probe = FastAPI()
    probe.add_exception_handler(StarletteHTTPException, http_exception_handler)

    @probe.get("/error")
    def fail():
        raise HTTPException(status_code=status, detail="Expected test error")

    r = TestClient(probe, raise_server_exceptions=False).get("/error")
    assert r.status_code == status
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == code
    assert body.error.status == status
    assert body.error.message == "Expected test error"


def test_unhandled_error_remains_generic():
    probe = FastAPI()
    probe.add_exception_handler(Exception, unhandled_exception_handler)

    @probe.get("/error")
    def fail():
        raise RuntimeError("secret internal implementation detail")

    r = TestClient(probe, raise_server_exceptions=False).get("/error")
    assert r.status_code == 500
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == "INTERNAL_ERROR"
    assert "secret" not in body.error.message


def test_documented_error_codes_match_handler_mapping():
    root = Path(__file__).resolve().parents[3]
    document = (root / "docs/api-contract.md").read_text(encoding="utf-8")
    section = document.split("Standard error codes:", 1)[1].split("---", 1)[0]
    rows = re.findall(r"- `([A-Z_]+)` \(([0-9]+)\)", section)
    assert rows
    for code, status in rows:
        assert HTTP_ERROR_CODES[int(status)] == code


def test_documented_qa_example_has_no_missing_evidence():
    root = Path(__file__).resolve().parents[3]
    document = (root / "docs/api-contract.md").read_text(encoding="utf-8")
    examples = [json.loads(block) for block in re.findall(r"```json\s*(.*?)```", document, re.S)]
    answers = [item for item in examples if "answer" in item]
    assert answers
    for item in answers:
        cited = set(re.findall(r"\[(E[1-9][0-9]*)\]", item["answer"]))
        supplied = {evidence["evidence_id"] for evidence in item["evidence"]}
        assert cited and cited <= supplied
