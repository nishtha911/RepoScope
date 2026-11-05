# Day 10 Track 2: Unified LLM client

## Scope and status

`reposcope.integrations.llm.LLMClient` is an async provider client. It does not
perform retrieval, authorize repository access, connect the Ask API, or replace
the Day 9 citation/symbol/negative-claim validator. That validator must run on
every response, including cache hits, before the application returns an answer.
Schema-valid JSON can still contain hallucinated claims.

No API call, DB access, dotenv load, or environment validation occurs on import.
No database migration is needed. `httpx` is already a project dependency;
`jsonschema>=4.23,<5` is added for local structured-output validation.

## Configuration

Read environment via `LLMClient.from_env()`. The application is responsible for
loading its root `.env` (if desired); this module deliberately does not import
the DB-coupled application config. Never commit real credentials.

Variables:

| Variable | Purpose |
| --- | --- |
| GEMINI_API_KEY | Secret supplied by your deployment |
| GEMINI_MODEL | Explicit model ID available to your account |
| GEMINI_INPUT_CHAR_LIMIT | Character budget; default 120000 |
| GROQ_API_KEY | Secret supplied by your deployment |
| GROQ_MODEL | Explicit model ID available to your account |
| GROQ_INPUT_CHAR_LIMIT | Character budget; default 32000 |
| GROQ_STRICT_SCHEMA | true/false, default false |
| LLM_ALLOW_FALLBACK | true/false, default false |

Keys and model names must be supplied together. There are no hardcoded model
names or claims about current account availability. Select provider models
that support the requested JSON-schema mode. A configured name is not proof
that the provider supports it. Provider schema rejection (400) is not retried
and is not silently downgraded to JSON-object/plain-text mode.

Synthesis prefers Gemini; classification prefers Groq. Fallback is explicitly
opt-in because it can send the same repository evidence to another provider
and incur additional charges. With fallback disabled, an unconfigured primary
is an error. Authentication/permanent errors, schema-invalid responses, safety
blocks and truncated outputs fail closed, without switching providers.

Character budgets are operator limits, not token counts or guarantees about
provider context windows. Whole requests and schemas must fit each provider.
The client never silently clips evidence to fit fallback. A provider can still
reject an input on its real token limit; adjust the evidence pack explicitly.

## API

```python
from reposcope.integrations.llm import LLMClient, LLMRequest

schema = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

# Run inside the application's async lifecycle, not at module import.
async def answer(question, pack, authenticated_tenant_scope):
    async with LLMClient.from_env() as client:
        result = await client.generate_from_evidence(
            question, pack, response_schema=schema,
            cache_scope=authenticated_tenant_scope,
        )
        # REQUIRED: call the Day 9 groundedness validator with result.data,
        # the exact pack, authorized symbol scope and unresolved-edge context.
        # Do not expose this result directly before that validation.
        return result
```

The evidence adapter retains existing spotlighted prompt construction and
adds repository, snapshot and commit identity to the caller's tenant scope.
It does not retrieve evidence again or relabel snapshots. Its additional
evidence metadata is a hash of the full canonical pack; full source is already
in the spotlighted prompt.

For lower-level calls pass `LLMRequest(messages=..., evidence=...,
cache_scope=..., response_schema=..., task="classification")` to
`await client.generate(request)`. Any non-None evidence is serialized and sent
as an explicitly untrusted user-data message, with a system-level warning.
Evidence is not merely a cache-key input. System messages are permitted only
at the first position. Repository data is never intentionally made a system
instruction; spotlighting is not a complete prompt-injection defense.

`LLMResponse` includes parsed data, raw JSON text, actual provider/model, SHA-256
cache key, cached flag, total network attempts and fallback-used flag.

Only local JSON-pointer schema references are permitted; remote schema
retrieval is disabled by validation. Duplicate JSON keys, non-finite JSON
constants, invalid schemas, and schema/type mismatches are rejected. Groq strict
mode additionally requires closed objects with all properties required.

## Lifecycle, retry and safety

Reuse a client within one async application lifecycle; close it with async
context management or `await client.aclose()`. Injected HTTP clients are owned
and closed by their caller. Default owned clients disable environment proxies
and redirects. Credentials are headers, not URL query parameters. Error text
never includes provider response bodies, API keys, prompts or evidence.

Transient statuses: 408, 429, 500, 502, 503, 504; transport errors are also
retryable. Defaults: 3 attempts per eligible provider, 0.5-second base backoff,
8-second maximum delay, 30-second per-request and 60-second total timeout.
Backoff has bounded jitter. `Retry-After` seconds and HTTP dates are respected;
if the required wait exceeds the retry-delay budget, do not retry that provider
sooner. An explicitly allowed fallback may then be tried. Cancellation
propagates. Retrying a request can incur duplicate provider costs if an earlier
request completed remotely before its connection failed.

Responses are limited to 2 MB while streaming from the HTTP transport. This
is not user-visible token streaming: structured output is returned only after
complete response and local schema validation. No provider tools are enabled.

## Cache

Default cache: process-local, thread-safe, bounded TTL/LRU; 256 entries,
300-second TTL, 16 MB aggregate stored bytes. It is not the empty `llm_cache`
DB model, is not durable, and is not shared across server workers. Responses
are held in plaintext memory; keys contain only SHA-256 digests, not prompts.

Key inputs: policy version, authenticated tenant/repository/snapshot scope,
messages, full evidence identity/content, schema, task, temperature, output
budget and configured provider/model/mode route. API keys are excluded.
Only schema-valid successes enter the cache; invalid output and transient
failures do not. TTL is measured with a monotonic clock. Values are copied on
read; caller mutation does not poison the cached result. Concurrent identical
misses may make duplicate calls; there is no cross-request single-flight lock.

Cache scope is not authorization. The API must derive it from authenticated,
authorized server context, never trust a request-body scope string, and avoid
sharing a cache across security boundaries without distinct scopes. Recheck
source authorization and groundedness even on a cache hit. Construct a new
client/cache or call `client.cache.clear()` when invalidating all entries.

## Tests and live verification

From backend:

```powershell
python -m pytest tests/unit/test_llm_client.py tests/unit/test_llm_cache.py -q -rs
python -m pytest tests -q -rs
```

All new tests use `httpx.MockTransport`; no keys, real API calls, DB or provider
spend. Both adapters, routing, fallback, validation, retries, timeout,
cancellation, cache isolation/expiry and evidence-adapter boundaries are tested.
Live provider/model compatibility, latency and credentials remain unverified
until a separately authorized live smoke test. Do not claim the Ask endpoint or
citation-grounded end-to-end milestone is complete from these unit tests.

Provider references:
- Gemini generateContent API: https://ai.google.dev/api/generate-content
- Groq structured outputs: https://console.groq.com/docs/structured-outputs
