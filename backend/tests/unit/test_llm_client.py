"""Mocked HTTP only. No provider credentials, network, DB or paid calls."""
import asyncio
from dataclasses import replace
import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from reposcope.integrations.llm import (
    LLMClient, ProviderConfig, LLMRequest, LLMError, LLMOutputError,
    LLMUnavailable, LLMBlockedError, LLMConfigurationError, _retry_after,
)
from reposcope.integrations.llm_cache import MemoryLLMCache

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}
KEY = "test-secret-not-a-real-key"


def config(provider="gemini", **options):
    return ProviderConfig(provider, provider + "-mock-model", KEY, **options)


def request(**options):
    base = LLMRequest(messages=({"role": "system", "content": "Answer only from evidence"},
        {"role": "user", "content": "What does work do?"}), evidence={"E1": "def work(): pass"},
        cache_scope="tenant:1/repo:2/snapshot:3", response_schema=SCHEMA)
    return replace(base, **options)


def envelope(provider, text='{"answer":"works [E1]"}', finish=None):
    if provider == "gemini":
        return {"candidates": [{"finishReason": finish or "STOP", "content": {"parts": [{"text": text}]}}]}
    return {"choices": [{"finish_reason": finish or "stop", "message": {"content": text}}]}


def run(handler, operation, providers=None, **options):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with LLMClient(providers or [config()], http_client=http, **options) as client:
                return await operation(client)
    return asyncio.run(scenario())


def test_gemini_schema_headers_messages_and_cache():
    calls = []
    def handler(req):
        calls.append(req)
        body = json.loads(req.content)
        assert req.headers["x-goog-api-key"] == KEY
        assert KEY not in str(req.url)
        assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["maxOutputTokens"] == 4096
        assert "systemInstruction" in body
        assert "UNTRUSTED_DATA" in body["contents"][-1]["parts"][0]["text"]
        return httpx.Response(200, json=envelope("gemini"))
    async def operation(client):
        first = await client.generate(request())
        first.data["answer"] = "mutated externally"
        second = await client.generate(request())
        assert not first.cached and second.cached
        assert second.attempts == 0
        assert second.data == {"answer": "works [E1]"}
        assert len(second.cache_key) == 64
    run(handler, operation)
    assert len(calls) == 1


def test_classification_routes_to_groq_with_schema():
    def handler(req):
        assert req.url.host == "api.groq.com"
        assert req.headers["authorization"] == "Bearer " + KEY
        body = json.loads(req.content)
        assert body["response_format"]["json_schema"]["schema"] == SCHEMA
        assert body["response_format"]["json_schema"]["strict"] is False
        assert body["max_completion_tokens"] == 4096
        return httpx.Response(200, json=envelope("groq"))
    async def operation(client):
        result = await client.generate(request(task="classification"))
        assert result.provider == "groq" and not result.fallback_used
    run(handler, operation, providers=[config("gemini"), config("groq")])


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_status_retries_then_succeeds(status):
    calls, delays = [], []
    def handler(req):
        calls.append(req)
        return httpx.Response(status) if len(calls) == 1 else httpx.Response(200, json=envelope("gemini"))
    async def sleep(delay):
        delays.append(delay)
    async def operation(client):
        assert (await client.generate(request())).attempts == 2
    run(handler, operation, sleep=sleep, jitter=lambda: 0)
    assert len(calls) == 2 and delays == [0.5]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_status_not_retried_or_fallen_back(status):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": KEY + " private prompt"})
    async def operation(client):
        with pytest.raises(LLMError) as error:
            await client.generate(request())
        assert KEY not in str(error.value) and "private prompt" not in str(error.value)
    run(handler, operation, providers=[config(), config("groq")], allow_fallback=True)
    assert len(calls) == 1


def test_retry_after_is_respected():
    calls, delays = [], []
    def handler(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": "3"}) if len(calls) == 1 else httpx.Response(200, json=envelope("gemini"))
    async def sleep(delay):
        delays.append(delay)
    run(handler, lambda client: client.generate(request()), sleep=sleep, jitter=lambda: 0)
    assert delays == [3.0]


def test_retry_after_above_budget_not_shortened():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": "100"})
    async def operation(client):
        with pytest.raises(LLMUnavailable):
            await client.generate(request())
    run(handler, operation)
    assert len(calls) == 1


def test_exponential_backoff_is_bounded():
    delays = []
    async def sleep(delay):
        delays.append(delay)
    async def operation(client):
        with pytest.raises(LLMUnavailable):
            await client.generate(request())
    run(lambda req: httpx.Response(503), operation, sleep=sleep, jitter=lambda: 0,
        max_attempts=4, base_delay=1, max_delay=2)
    assert delays == [1, 2, 2]


def test_fallback_after_primary_exhaustion_preserves_evidence():
    hosts, evidence_sent = [], []
    def handler(req):
        hosts.append(req.url.host)
        body = json.loads(req.content)
        if req.url.host == "generativelanguage.googleapis.com":
            evidence_sent.append(body["contents"][-1]["parts"][0]["text"])
            return httpx.Response(503)
        evidence_sent.append(body["messages"][-1]["content"])
        return httpx.Response(200, json=envelope("groq"))
    async def operation(client):
        first = await client.generate(request())
        assert first.provider == "groq" and first.fallback_used and first.attempts == 3
        second = await client.generate(request())
        assert second.cached and second.fallback_used
    async def sleep(delay):
        pass
    run(handler, operation, providers=[config(), config("groq")], allow_fallback=True, max_attempts=2, sleep=sleep)
    assert len(hosts) == 3
    assert len(set(evidence_sent)) == 1


def test_fallback_disabled_by_default():
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(503)
    async def operation(client):
        with pytest.raises(LLMUnavailable):
            await client.generate(request())
    run(handler, operation, providers=[config(), config("groq")], max_attempts=1)
    assert calls == ["generativelanguage.googleapis.com"]


def test_transport_failure_retried():
    calls = []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            raise httpx.ConnectError("secret " + KEY, request=req)
        return httpx.Response(200, json=envelope("gemini"))
    async def sleep(delay):
        pass
    result = run(handler, lambda c: c.generate(request()), sleep=sleep)
    assert result.attempts == 2


@pytest.mark.parametrize("text", ["not JSON", '{"answer":1}', '{}',
    '{"answer":"a","extra":1}', '{"answer":"a","answer":"b"}', '{"answer":NaN}'])
def test_invalid_outputs_are_not_cached_retried_or_fallen_back(text):
    calls = []
    cache = MemoryLLMCache()
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=envelope("gemini", text))
    async def operation(client):
        for _ in range(2):
            with pytest.raises(LLMOutputError):
                await client.generate(request())
    run(handler, operation, providers=[config(), config("groq")], allow_fallback=True, cache=cache)
    assert len(calls) == 2


@pytest.mark.parametrize("provider,finish", [("gemini", "MAX_TOKENS"), ("groq", "length")])
def test_truncated_outputs_rejected(provider, finish):
    async def operation(client):
        with pytest.raises(LLMOutputError, match="incomplete"):
            await client.generate(request(task="synthesis" if provider == "gemini" else "classification"))
    run(lambda req: httpx.Response(200, json=envelope(provider, finish=finish)), operation, providers=[config(provider)])


@pytest.mark.parametrize("provider,finish", [("gemini", "SAFETY"), ("groq", "content_filter")])
def test_safety_blocks_fail_closed(provider, finish):
    async def operation(client):
        with pytest.raises(LLMBlockedError):
            await client.generate(request(task="synthesis" if provider == "gemini" else "classification"))
    run(lambda req: httpx.Response(200, json=envelope(provider, finish=finish)), operation, providers=[config(provider)])


def test_total_timeout_is_bounded():
    async def handler(req):
        await asyncio.sleep(1)
        return httpx.Response(200, json=envelope("gemini"))
    async def operation(client):
        with pytest.raises(LLMUnavailable, match="total timeout"):
            await client.generate(request())
    run(handler, operation, total_timeout=0.01)


def test_cancellation_propagates():
    async def handler(req):
        raise asyncio.CancelledError()
    async def operation(client):
        with pytest.raises(asyncio.CancelledError):
            await client.generate(request())
    run(handler, operation)


@pytest.mark.parametrize("change", [
    {"cache_scope": "tenant:OTHER/repo:2/snapshot:3"},
    {"cache_scope": "tenant:1/repo:2/snapshot:4"},
    {"evidence": {"E1": "changed source"}},
    {"temperature": 0.5}, {"max_output_tokens": 123},
    {"messages": ({"role": "user", "content": "different question"},)},
])
def test_cache_key_changes_with_inputs(change):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=envelope("gemini"))
    async def operation(client):
        a = await client.generate(request())
        b = await client.generate(request(**change))
        assert a.cache_key != b.cache_key and not b.cached
    run(handler, operation)
    assert len(calls) == 2


def test_cache_key_changes_with_schema_and_model():
    async def operation(client):
        a = await client.generate(request())
        extended = dict(SCHEMA, title="version two")
        b = await client.generate(request(response_schema=extended))
        assert a.cache_key != b.cache_key
        client.providers["gemini"] = replace(config(), model="new-model")
        c = await client.generate(request())
        assert c.cache_key != a.cache_key
    run(lambda req: httpx.Response(200, json=envelope("gemini")), operation)


def test_context_limit_rejects_before_network():
    async def operation(client):
        with pytest.raises(LLMConfigurationError, match="fits"):
            await client.generate(request())
    run(lambda req: pytest.fail("No request allowed"), operation, providers=[config(input_char_limit=1)])


def test_fallback_never_silently_trims_context():
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(503)
    async def operation(client):
        with pytest.raises(LLMUnavailable):
            await client.generate(request())
    run(handler, operation, providers=[config(), config("groq", input_char_limit=1)], allow_fallback=True, max_attempts=1)
    assert calls == ["generativelanguage.googleapis.com"]


def test_strict_groq_payload_and_preflight():
    def handler(req):
        assert json.loads(req.content)["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json=envelope("groq"))
    async def operation(client):
        await client.generate(request(task="classification"))
        bad = {"type": "object", "properties": {"answer": {"type": "string"}}}
        with pytest.raises(LLMConfigurationError, match="closed"):
            await client.generate(request(task="classification", response_schema=bad))
    run(handler, operation, providers=[config("groq", strict_schema=True)])


@pytest.mark.parametrize("schema", [{"$ref":"https://example.invalid/schema"},
    {"$id":"https://example.invalid/base"}, {"$ref":"#/$defs/missing"}, {"type":"made-up"}])
def test_invalid_or_external_schema_rejected_before_network(schema):
    async def operation(client):
        with pytest.raises(ValueError):
            await client.generate(request(response_schema=schema))
    run(lambda req: pytest.fail("No network"), operation)


def test_local_schema_refs_supported():
    schema = {"$defs": {"answer": SCHEMA}, "$ref": "#/$defs/answer"}
    run(lambda req: httpx.Response(200, json=envelope("gemini")),
        lambda c: c.generate(request(response_schema=schema)))


def test_from_env_no_import_time_config_or_secret_repr():
    client = LLMClient.from_env(environ={"GEMINI_API_KEY": KEY, "GEMINI_MODEL":"configured-model"})
    assert KEY not in repr(client.providers["gemini"])
    assert client._http is None
    asyncio.run(client.aclose())


@pytest.mark.parametrize("env", [{}, {"GEMINI_API_KEY": KEY},
    {"GROQ_MODEL":"configured-model"}, {"LLM_ALLOW_FALLBACK":"maybe"}])
def test_invalid_environment_fails_without_network(env):
    with pytest.raises(LLMConfigurationError):
        LLMClient.from_env(environ=env)


def test_explicit_fallback_can_use_only_secondary_config():
    result = run(lambda req: httpx.Response(200, json=envelope("groq")),
        lambda c: c.generate(request()), providers=[config("groq")], allow_fallback=True)
    assert result.provider == "groq" and result.fallback_used


def test_injected_http_client_remains_caller_owned():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=envelope("gemini")))) as http:
            client = LLMClient([config()], http_client=http)
            await client.generate(request())
            await client.aclose()
            assert not http.is_closed
            with pytest.raises(LLMConfigurationError, match="closed"):
                await client.generate(request())
    asyncio.run(scenario())


def test_retry_after_parsing():
    assert _retry_after("3") == 3
    assert _retry_after("invalid") is None
    assert _retry_after("NaN") is None
    assert _retry_after("Thu, 01 Jan 1970 00:00:00 GMT") == 0


def test_provider_path_validation():
    for model in ("../secret", "https://evil.invalid", "model?key=value", "a/b"):
        with pytest.raises(ValueError):
            ProviderConfig("gemini", model, KEY)


def test_adapter_preserves_prompt_and_scopes_pack(monkeypatch):
    import hashlib
    messages = [{"role":"system","content":"Existing security policy"}, {"role":"user","content":"Existing spotlighted source [E1]"}]
    monkeypatch.setitem(sys.modules, "reposcope.rag.prompts", SimpleNamespace(build_spotlighted_messages=lambda question, pack: messages))
    monkeypatch.setitem(sys.modules, "reposcope.rag.evidence_pack", SimpleNamespace(serialize_evidence_pack=lambda pack: "canonical evidence"))
    captured = []
    pack = SimpleNamespace(repository_id=2, snapshot_id=3, commit_sha="a"*40)
    async def operation(client):
        async def generate(req):
            captured.append(req)
            return "mocked"
        client.generate = generate
        assert await client.generate_from_evidence("question", pack, response_schema=SCHEMA, cache_scope="tenant:1") == "mocked"
    run(lambda req: pytest.fail("Adapter should not call network"), operation)
    value = captured[0]
    assert value.messages == tuple(messages)
    assert json.loads(value.cache_scope)["snapshot_id"] == 3
    assert value.evidence["pack_sha256"] == hashlib.sha256(b"canonical evidence").hexdigest()


@pytest.mark.parametrize("payload", [{}, {"candidates": []}, {"candidates":[{"finishReason":"STOP","content":{"parts":[]}}]}])
def test_malformed_or_empty_provider_envelope_rejected(payload):
    async def operation(client):
        with pytest.raises(LLMOutputError):
            await client.generate(request())
    run(lambda req: httpx.Response(200, json=payload), operation)


def test_gemini_prompt_block_rejected():
    async def operation(client):
        with pytest.raises(LLMBlockedError):
            await client.generate(request())
    run(lambda req: httpx.Response(200, json={"promptFeedback":{"blockReason":"SAFETY"}}), operation)


def test_groq_refusal_rejected():
    payload = {"choices":[{"finish_reason":"stop","message":{"refusal":"refused","content":""}}]}
    async def operation(client):
        with pytest.raises(LLMBlockedError):
            await client.generate(request(task="classification"))
    run(lambda req: httpx.Response(200, json=payload), operation, providers=[config("groq")])


def test_no_redirect_following_with_credentials():
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(302, headers={"Location":"https://example.invalid/steal"})
    async def operation(client):
        with pytest.raises(LLMError):
            await client.generate(request())
    run(handler, operation)
    assert calls == ["generativelanguage.googleapis.com"]


def test_provider_response_size_limit():
    async def operation(client):
        with pytest.raises(LLMOutputError, match="safety limit"):
            await client.generate(request())
    run(lambda req: httpx.Response(200, content=b"x"*2_000_001), operation)


def test_nonfinite_evidence_rejected_before_network():
    async def operation(client):
        with pytest.raises(ValueError):
            await client.generate(request(evidence={"value":float("nan")}))
    run(lambda req: pytest.fail("No network"), operation)


def test_blank_adapter_scope_rejected_before_imports():
    async def operation(client):
        with pytest.raises(ValueError, match="cache_scope"):
            await client.generate_from_evidence("question", object(), response_schema=SCHEMA, cache_scope=" ")
    run(lambda req: pytest.fail("No network"), operation)
