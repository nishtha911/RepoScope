"""Offline Q&A orchestration tests with real LLMClient and mocked HTTP."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import httpx
import pytest

from reposcope.integrations.llm import LLMClient, LLMUnavailable, ProviderConfig
from reposcope.integrations.llm_cache import MemoryLLMCache
from reposcope.rag import qa_service as qa
from reposcope.rag.evidence_pack import EvidenceCandidate, build_evidence_pack
from reposcope.rag.validator import CitationValidationError
from reposcope.retrieval.vector import EmbeddingIndexMismatchError

SOURCE = "def get_hmm():\n    return 'hmmm...'\n"


@pytest.fixture
def pack():
    candidate = EvidenceCandidate(repository_id=33, snapshot_id=9, file_id=11,
        file_path="sample/core.py", symbol_id=75, chunk_id=101,
        start_line=5, end_line=6, text=SOURCE, name="get_hmm", qualname="get_hmm",
        kind="function", signature="def get_hmm():", origin="seed", order=0)
    return build_evidence_pack([candidate], repository_id=33, snapshot_id=9,
        commit_sha="d469f2f5e0a472be2c7d95ff90ed46e975810dc8")


@pytest.fixture
def draft():
    return {"claims": [{"text": "get_hmm returns the string 'hmmm...'.", "citations": [
        {"evidence_id": "E1", "quote": "return 'hmmm...'"}]}],
        "gaps": [], "insufficient_evidence": False}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Test must configure fake preparation and mocked provider HTTP")
    monkeypatch.setattr(qa, "prepare_question_context", forbidden)
    monkeypatch.setattr(qa, "_make_llm_client", forbidden)


def prepare(monkeypatch, pack):
    mock = Mock(return_value=qa.PreparedQuestion(pack, 10, 2))
    monkeypatch.setattr(qa, "prepare_question_context", mock)
    return mock


def envelope(draft):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": json.dumps(draft)}]}}]}


def scenario(monkeypatch, pack, handler, callback):
    prepare(monkeypatch, pack)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            monkeypatch.setattr(qa, "_make_llm_client", lambda cache: LLMClient(
                [ProviderConfig("gemini", "unit-test-model", "synthetic-not-real-key")],
                cache=cache, http_client=http, max_attempts=1, allow_fallback=False,
                total_timeout=5, request_timeout=2))
            return await callback()
    return asyncio.run(run())


def test_answer_has_server_owned_citations_and_logs_no_source(monkeypatch, pack, draft, capsys):
    calls = []
    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["generationConfig"]["maxOutputTokens"] == 2048
        assert body["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
        return httpx.Response(200, json=envelope(draft))
    async def run():
        return await qa.answer_question(object(), 33, "What does get_hmm return?", cache=MemoryLLMCache())
    result = scenario(monkeypatch, pack, handler, run)
    assert result.response.answer.endswith("[E1]")
    assert result.response.evidence[0].symbol_id == 75
    assert result.response.timings is None and not result.cache_hit
    assert len(calls) == 1
    output = capsys.readouterr().out
    assert '"llm_cache_hit": false' in output
    assert "return 'hmmm...'" not in output and "synthetic-not-real-key" not in output


def test_identical_question_reuses_generation_cache(monkeypatch, pack, draft):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(draft))
    async def run():
        cache = MemoryLLMCache()
        first = await qa.answer_question(object(), 33, "question", cache=cache)
        second = await qa.answer_question(object(), 33, "question", cache=cache)
        return first, second
    first, second = scenario(monkeypatch, pack, handler, run)
    assert not first.cache_hit and second.cache_hit and len(calls) == 1
    assert first.response.answer == second.response.answer
    assert qa.prepare_question_context.call_count == 2


def test_changed_question_invalidates_generation_cache(monkeypatch, pack, draft):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(draft))
    async def run():
        cache = MemoryLLMCache()
        await qa.answer_question(object(), 33, "first question", cache=cache)
        return await qa.answer_question(object(), 33, "second question", cache=cache)
    result = scenario(monkeypatch, pack, handler, run)
    assert not result.cache_hit and len(calls) == 2


def test_changed_source_changes_cache_key(monkeypatch, pack, draft):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(draft))
    async def run():
        cache = MemoryLLMCache()
        await qa.answer_question(object(), 33, "question", cache=cache)
        changed = pack.model_copy(update={"gaps": ("Additional source coverage limitation",)})
        prepare(monkeypatch, changed)
        return await qa.answer_question(object(), 33, "question", cache=cache)
    result = scenario(monkeypatch, pack, handler, run)
    assert not result.cache_hit and len(calls) == 2


def test_cache_hit_is_revalidated(monkeypatch, pack, draft):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(draft))
    original = qa.validate_answer
    validations = []
    def validate(data, evidence):
        validations.append(True)
        return original(data, evidence)
    monkeypatch.setattr(qa, "validate_answer", validate)
    async def run():
        cache = MemoryLLMCache()
        await qa.answer_question(object(), 33, "question", cache=cache)
        await qa.answer_question(object(), 33, "question", cache=cache)
    scenario(monkeypatch, pack, handler, run)
    assert len(calls) == 1 and len(validations) == 2


def test_bad_citations_are_not_returned_or_cached(monkeypatch, pack, draft):
    bad = deepcopy(draft)
    bad["claims"][0]["citations"][0]["evidence_id"] = "E999"
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(bad if len(calls) == 1 else draft))
    async def run():
        cache = MemoryLLMCache()
        with pytest.raises(CitationValidationError):
            await qa.answer_question(object(), 33, "question", cache=cache)
        return await qa.answer_question(object(), 33, "question", cache=cache)
    result = scenario(monkeypatch, pack, handler, run)
    assert len(calls) == 2 and not result.cache_hit


def test_no_evidence_refuses_without_generation_or_configuration(monkeypatch):
    pack = build_evidence_pack([], repository_id=33, snapshot_id=9, commit_sha="a" * 40)
    prepare(monkeypatch, pack)
    result = asyncio.run(qa.answer_question(object(), 33, "question", cache=MemoryLLMCache()))
    assert "insufficient" in result.response.answer
    assert not result.response.evidence and result.response.gaps
    assert result.provider is None


def test_model_can_refuse_when_evidence_does_not_answer(monkeypatch, pack):
    refusal = {"claims": [], "gaps": ["Retrieved source does not establish this behavior"],
               "insufficient_evidence": True}
    async def run():
        return await qa.answer_question(object(), 33, "unknown behavior?", cache=MemoryLLMCache())
    result = scenario(monkeypatch, pack, lambda _: httpx.Response(200, json=envelope(refusal)), run)
    assert not result.response.evidence and result.response.gaps
    assert "insufficient" in result.response.answer


def test_provider_quota_failure_is_not_hidden(monkeypatch, pack):
    async def run():
        with pytest.raises(LLMUnavailable):
            await qa.answer_question(object(), 33, "question", cache=MemoryLLMCache())
    scenario(monkeypatch, pack, lambda _: httpx.Response(429), run)


@pytest.mark.parametrize("question", ["", " ", "x" * 4097, None])
def test_invalid_question_fails_before_preparation(question):
    with pytest.raises(qa.QuestionInputError):
        asyncio.run(qa.answer_question(object(), 33, question))


def test_foreign_repository_pack_is_rejected_before_generation(monkeypatch, pack):
    foreign = pack.model_copy(update={"repository_id": 34})
    prepare(monkeypatch, foreign)
    with pytest.raises(qa.QuestionContextError):
        asyncio.run(qa.answer_question(object(), 33, "question"))


def test_cached_schema_scope_contains_provenance_and_validator(pack):
    request = qa._request("question", pack)
    scope = json.loads(request.cache_scope)
    assert scope["repository_id"] == 33 and scope["snapshot_id"] == 9
    assert scope["commit_sha"] == pack.commit_sha and scope["validator"] == qa.VALIDATOR_VERSION
    assert request.task == "synthesis" and request.evidence["pack_sha256"]
    assert "Do not put [E1]" in request.messages[0]["content"]


def test_context_transaction_closes_and_uses_bounded_options(monkeypatch):
    # Access the real function from a clean module load; the autouse fixture
    # intentionally replaces the public function to keep other tests offline.
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("qa_context_unit_copy", Path(qa.__file__))
    module = importlib.util.module_from_spec(spec)
    import sys
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = None
    factory = Mock(return_value=session)
    with pytest.raises(module.QuestionNotFoundError):
        module.prepare_question_context(factory, 33, "question")
    session.connection.assert_called_once_with(execution_options={"isolation_level": "REPEATABLE READ"})
    assert str(session.execute.call_args_list[0].args[0]) == "SET TRANSACTION READ ONLY"
    session.__exit__.assert_called_once()
    session.commit.assert_not_called()
