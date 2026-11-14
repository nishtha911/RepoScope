"""Bounded, read-only Q&A orchestration; API wiring is a separate change.

Cache hits skip generation, not retrieval/query embedding. Quote validation
is structural, not a guarantee of semantic entailment or runtime correctness.
"""
import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool

from reposcope.contracts.api import AskResponse
from reposcope.integrations.llm import LLMClient, LLMRequest
from reposcope.integrations.llm_cache import MemoryLLMCache
from reposcope.models import Repository, RepositorySnapshot
from reposcope.rag.evidence_pack import EvidencePack, _validated, serialize_evidence_pack
from reposcope.rag.prompts import build_spotlighted_messages
from reposcope.rag.validator import ANSWER_SCHEMA, VALIDATOR_VERSION, validate_answer
from reposcope.retrieval.gemini_embeddings import INDEX_VERSION
from reposcope.retrieval.vector import EmbeddingIndexMismatchError

QA_POLICY_VERSION = "qa-general-bounded-v1"
_GENERATION_CACHE = MemoryLLMCache(max_entries=64, ttl_seconds=300, max_bytes=2_000_000)
_FORMAT_RULES = """
OUTPUT FORMAT: Return only the JSON object required by the response schema.
Put citation IDs such as E1 only in citations[].evidence_id. Do not put [E1]
labels in claim text or gaps: the server renders citation labels afterward.
Every claim must have an exact contiguous source quote of 8..500 characters.
Copy quotes exactly, including whitespace and punctuation, from source bodies.
Do not cite metadata, graph paths or gap messages as if they were source code.
Use no more than six concise claims. If the supplied evidence cannot establish
an answer, return no claims, insufficient_evidence=true, and concise gaps.
Do not fill an evidence gap with outside knowledge or invent missing code.
"""


class QuestionInputError(ValueError):
    pass


class QuestionNotFoundError(RuntimeError):
    pass


class QuestionNotReadyError(RuntimeError):
    pass


class QuestionContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedQuestion:
    pack: EvidencePack
    retrieval_expansion_ms: int
    pack_build_ms: int


@dataclass(frozen=True)
class QuestionResult:
    response: AskResponse
    cache_hit: bool
    provider: str | None
    model: str | None
    retrieval_expansion_ms: int
    pack_build_ms: int
    synthesis_validation_ms: int


def _inputs(repo_id, question):
    if type(repo_id) is not int or repo_id < 1:
        raise QuestionInputError("repo_id must be a positive integer")
    if not isinstance(question, str) or not question.strip() or len(question) > 4096:
        raise QuestionInputError("question must contain 1..4096 characters")
    return question.strip()


def _elapsed(start):
    return max(0, round((perf_counter() - start) * 1000))


def prepare_question_context(session_factory, repo_id, question):
    """Own a clean read-only REPEATABLE READ session; never share it with async code.

    Traversal/output budgets do not bound the current graph loader's entire
    repository load. Large-repository memory behavior still needs measurement.
    """
    question = _inputs(repo_id, question)
    from reposcope.retrieval.expanded_pipeline import search_chunks_hybrid_expanded
    from reposcope.rag.pipeline import assemble_evidence_pack
    with session_factory() as session:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '15s'"))
        session.execute(text("SET LOCAL lock_timeout = '3s'"))
        if session.get(Repository, repo_id) is None:
            raise QuestionNotFoundError("Repository was not found")
        snapshot = session.scalar(select(RepositorySnapshot)
            .where(RepositorySnapshot.repository_id == repo_id)
            .order_by(RepositorySnapshot.created_at.desc(), RepositorySnapshot.id.desc()).limit(1))
        if snapshot is None or snapshot.status != "ready":
            raise QuestionNotReadyError("Repository index is not ready")
        if snapshot.index_version != INDEX_VERSION:
            raise EmbeddingIndexMismatchError("Q&A requires a compatible Gemini index")
        started = perf_counter()
        expanded = search_chunks_hybrid_expanded(session, repo_id, question, limit=4,
            intent="general", candidate_limit=20, seed_limit=4, max_depth=1,
            max_neighbors_per_seed=2, max_expanded_symbols=8, max_expansions=500,
            min_confidence=0.0)
        retrieval_ms = _elapsed(started)
        started = perf_counter()
        try:
            pack = assemble_evidence_pack(session, expanded, snapshot_id=snapshot.id,
                                          max_entries=6, max_source_chars=6000)
            pack = _validated(pack)
        except (ValueError, TypeError):
            raise QuestionContextError("Could not assemble verified source evidence") from None
        if (pack.repository_id != repo_id or pack.snapshot_id != snapshot.id
                or pack.commit_sha != snapshot.commit_sha or not pack.commit_sha):
            raise QuestionContextError("Evidence provenance differs from the selected snapshot")
        prepared = PreparedQuestion(pack, retrieval_ms, _elapsed(started))
    # Session is closed before the returned pack is used for generation.
    return prepared


class _ValidatedOnlyCache:
    """Buffer LLMClient.set until output passes the citation guard."""
    def __init__(self, shared):
        self.shared = shared
        self.pending = {}

    def get(self, key):
        return self.shared.get(key)

    def set(self, key, value):
        self.pending[key] = value

    def publish(self, key):
        if key in self.pending:
            self.shared.set(key, self.pending[key])
        self.pending.clear()


def _make_llm_client(cache):
    return LLMClient.from_env(cache=cache, allow_fallback=False, max_attempts=1,
                              total_timeout=30, request_timeout=20)


def _request(question, pack):
    messages = build_spotlighted_messages(question, pack, max_context_chars=30000)
    messages[0]["content"] += "\n" + _FORMAT_RULES
    scope = json.dumps({"application": "reposcope-staging", "policy": QA_POLICY_VERSION,
        "validator": VALIDATOR_VERSION, "repository_id": pack.repository_id,
        "snapshot_id": pack.snapshot_id, "commit_sha": pack.commit_sha}, sort_keys=True)
    digest = hashlib.sha256(serialize_evidence_pack(pack).encode()).hexdigest()
    return LLMRequest(messages=tuple(messages), evidence={"pack_sha256": digest},
        cache_scope=scope, response_schema=ANSWER_SCHEMA, task="synthesis",
        temperature=0.0, max_output_tokens=2048)


async def answer_question(session_factory, repo_id, question, *, cache=None):
    """Generate or refuse; revalidate cached data against newly assembled evidence."""
    question = _inputs(repo_id, question)
    prepared = await run_in_threadpool(prepare_question_context, session_factory, repo_id, question)
    pack = _validated(prepared.pack)
    if pack.repository_id != repo_id:
        raise QuestionContextError("Prepared evidence belongs to another repository")
    started = perf_counter()
    if not pack.entries:
        checked = validate_answer({"claims": [], "gaps": [], "insufficient_evidence": True}, pack)
        result = QuestionResult(AskResponse(answer=checked.answer, evidence=list(checked.evidence),
            gaps=list(checked.gaps)), False, None, None, prepared.retrieval_expansion_ms,
            prepared.pack_build_ms, _elapsed(started))
    else:
        shared = _GENERATION_CACHE if cache is None else cache
        deferred = _ValidatedOnlyCache(shared)
        request = _request(question, pack)
        async with _make_llm_client(deferred) as client:
            generated = await client.generate(request)
        # This runs for both fresh output and cache hits. Invalid output never
        # reaches the API and fresh invalid output never enters shared cache.
        checked = validate_answer(generated.data, pack)
        deferred.publish(generated.cache_key)
        result = QuestionResult(AskResponse(answer=checked.answer, evidence=list(checked.evidence),
            gaps=list(checked.gaps)), generated.cached, generated.provider, generated.model,
            prepared.retrieval_expansion_ms, prepared.pack_build_ms, _elapsed(started))
    print(json.dumps({"event": "qa_complete", "repository_id": repo_id,
        "snapshot_id": pack.snapshot_id, "llm_cache_hit": result.cache_hit,
        "provider": result.provider, "model": result.model,
        "retrieval_expansion_ms": result.retrieval_expansion_ms,
        "pack_build_ms": result.pack_build_ms,
        "synthesis_validation_ms": result.synthesis_validation_ms}), flush=True)
    # Existing expanded retrieval combines stages; leave optional API timings
    # absent instead of inventing a separate retrieval/expansion breakdown.
    return result
