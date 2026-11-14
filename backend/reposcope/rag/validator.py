"""Structural citation and exact-source-quote checks for generated claims.

Not an entailment model: a matching quote does not prove that a claim follows
from it, answers the question, or describes runtime behavior. Keep evaluation
and prompt-injection tests separate. Never execute repository/model code.
"""
from dataclasses import dataclass
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from reposcope.contracts.evidence import Evidence
from reposcope.rag.evidence_pack import EvidencePack, _validated

VALIDATOR_VERSION = "citation-quotes-v1"


class CitationValidationError(RuntimeError):
    """Sanitized failure: do not include generated text or source in errors."""


class _DraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CitationSupport(_DraftRecord):
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$",
                             description="A source ID from the supplied pack, such as E1")
    quote: str = Field(min_length=8, max_length=500,
        description="Exact contiguous source excerpt, preserving case, whitespace and punctuation")


class CitedClaim(_DraftRecord):
    text: str = Field(min_length=1, max_length=1500,
        description="One plain-language claim; do not put citation labels or instructions here")
    citations: list[CitationSupport] = Field(min_length=1, max_length=3)


class AnswerDraft(_DraftRecord):
    claims: list[CitedClaim] = Field(max_length=6,
        description="Source-supported claims; empty when evidence is insufficient")
    gaps: list[str] = Field(max_length=12,
        description="What retrieved evidence cannot establish; never claim missing retrieval proves absence")
    insufficient_evidence: bool


ANSWER_SCHEMA = AnswerDraft.model_json_schema()


@dataclass(frozen=True)
class ValidatedAnswer:
    answer: str
    evidence: tuple[Evidence, ...]
    gaps: tuple[str, ...]
    insufficient_evidence: bool


def _failure(message):
    raise CitationValidationError(message)


def validate_answer(draft, pack: EvidencePack) -> ValidatedAnswer:
    """Validate fresh output OR a cache hit against the actual evidence pack.

    The rendered answer is constructed from validated claims, not a separate
    unchecked model-authored answer field. Evidence records come from the pack,
    never from model-provided paths, symbol IDs, line ranges, or source bodies.
    """
    try:
        pack = _validated(pack)
        if isinstance(draft, AnswerDraft):
            draft = draft.model_dump()
        draft = AnswerDraft.model_validate(draft)
    except (ValidationError, ValueError, TypeError, AttributeError):
        _failure("Invalid answer schema or evidence pack")
    for gap in draft.gaps:
        if not gap.strip() or len(gap) > 1000 or "[E" in gap:
            _failure("Invalid generated gap record")
    gaps = tuple(dict.fromkeys((*pack.gaps, *draft.gaps)))
    if draft.insufficient_evidence:
        if draft.claims:
            _failure("Insufficient-evidence output must not contain factual claims")
        if not gaps:
            gaps = ("Retrieved evidence does not establish an answer to this question",)
        return ValidatedAnswer(
            answer="The retrieved evidence is insufficient to answer this question reliably.",
            evidence=(), gaps=gaps, insufficient_evidence=True)
    if not draft.claims or not pack.entries:
        _failure("An affirmative answer requires citable source claims")
    entries = {entry.source.evidence_id: entry for entry in pack.entries}
    lines, used = [], set()
    for claim in draft.claims:
        if not claim.text.strip() or "[E" in claim.text:
            _failure("Claim text is blank or contains model-authored citation labels")
        seen, labels = set(), []
        for support in claim.citations:
            entry = entries.get(support.evidence_id)
            if entry is None:
                _failure("Generated citation ID is not in the evidence pack")
            quote = support.quote
            if len(quote.strip()) < 8 or not re.search(r"[A-Za-z0-9_]", quote):
                _failure("Supporting quote is empty or trivial")
            if quote not in entry.source.text:
                _failure("Supporting quote does not match the cited source")
            identity = (support.evidence_id, quote)
            if identity in seen:
                _failure("Duplicate claim citation")
            seen.add(identity)
            if support.evidence_id not in labels:
                labels.append(support.evidence_id)
            used.add(support.evidence_id)
        lines.append(claim.text.strip() + " " + " ".join(f"[{label}]" for label in labels))
    evidence = tuple(Evidence.model_validate(entry.source.model_dump())
                     for entry in pack.entries if entry.source.evidence_id in used)
    return ValidatedAnswer(answer="\n\n".join(lines), evidence=evidence,
                           gaps=gaps, insufficient_evidence=False)
