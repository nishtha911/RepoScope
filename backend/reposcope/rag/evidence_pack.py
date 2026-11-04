"""Deterministic, pack-local citations using the existing Evidence contract.

Pure serialization: no database, configuration, model or network calls.
Whole source chunks are selected or omitted, never silently shortened.
"""
import json
import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from reposcope.contracts.evidence import Evidence


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidencePath(_Record):
    seed_symbol_id: int = Field(gt=0, strict=True)
    symbol_ids: tuple[int, ...]
    edge_ids: tuple[int, ...]
    edge_kinds: tuple[str, ...]
    directions: tuple[Literal["incoming", "outgoing"], ...]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @field_validator("symbol_ids", "edge_ids", mode="before")
    @classmethod
    def strict_ids(cls, values):
        if any(isinstance(i,bool) or not isinstance(i,int) or i < 1 for i in values):
            raise ValueError("Path IDs must be positive integers")
        return values

    @model_validator(mode="after")
    def coherent(self) -> Self:
        count = len(self.edge_ids)
        if not 1 <= count <= 2 or len(self.symbol_ids) != count + 1:
            raise ValueError("Evidence paths must contain one or two edges")
        if len(self.edge_kinds) != count or len(self.directions) != count:
            raise ValueError("Path relationship metadata lengths differ")
        if self.symbol_ids[0] != self.seed_symbol_id or len(set(self.symbol_ids)) != len(self.symbol_ids):
            raise ValueError("Path seed/cycle mismatch")
        if any(isinstance(i, bool) or not isinstance(i, int) or i < 1 for i in (*self.symbol_ids, *self.edge_ids)):
            raise ValueError("Path IDs must be positive integers")
        if any(not kind.strip() for kind in self.edge_kinds):
            raise ValueError("Empty edge kind")
        return self


class EvidenceCandidate(_Record):
    """Hydrated, source-aligned input; text is source body, not chunk header."""
    repository_id: int = Field(gt=0, strict=True)
    snapshot_id: int = Field(gt=0, strict=True)
    file_id: int = Field(gt=0, strict=True)
    file_path: str = Field(min_length=1, max_length=4096)
    symbol_id: int = Field(gt=0, strict=True)
    chunk_id: int = Field(gt=0, strict=True)
    start_line: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=1024)
    qualname: str | None = None
    kind: str = Field(min_length=1, max_length=100)
    signature: str | None = None
    origin: Literal["seed", "expanded"]
    order: int = Field(ge=0, strict=True)
    fused_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    paths: tuple[EvidencePath, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.text.strip() or self.end_line < self.start_line:
            raise ValueError("Source text/range is invalid")
        line_count = self.text.count("\n") + (0 if self.text.endswith("\n") else 1)
        if self.end_line - self.start_line + 1 != line_count:
            raise ValueError("Source body and citation line range differ")
        if not self.file_path.strip() or not self.name.strip() or not self.kind.strip():
            raise ValueError("Source metadata must not be blank")
        parts = self.file_path.split("/")
        if self.file_path.startswith("/") or "\\" in self.file_path or "\x00" in self.file_path or any(p in {"", ".", ".."} for p in parts) or ":" in parts[0]:
            raise ValueError("Expected repository-relative POSIX path")
        if self.signature is not None and not self.signature.strip():
            raise ValueError("Signature must be nonblank or absent")
        if any(path.symbol_ids[-1] != self.symbol_id for path in self.paths):
            raise ValueError("Path does not terminate at evidence symbol")
        if self.origin == "seed" and self.paths:
            raise ValueError("Seed evidence must not claim an expansion path")
        if self.origin == "expanded" and not self.paths:
            raise ValueError("Expanded evidence needs relationship provenance")
        return self


class EvidenceEntry(_Record):
    source: Evidence
    name: str
    qualname: str | None
    kind: str
    signature: str | None
    origin: Literal["seed", "expanded"]
    fused_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    paths: tuple[EvidencePath, ...] = ()


class ContextSymbol(_Record):
    """Scoped graph metadata, not a citable source record or evidence ID."""
    symbol_id: int = Field(gt=0, strict=True)
    file_id: int = Field(gt=0, strict=True)
    snapshot_id: int = Field(gt=0, strict=True)
    file_path: str
    name: str
    qualname: str | None
    kind: str
    is_seed: bool
    paths: tuple[EvidencePath, ...] = ()


class EvidencePack(_Record):
    schema_version: Literal[1] = 1
    repository_id: int = Field(gt=0, strict=True)
    snapshot_id: int = Field(gt=0, strict=True)
    commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40,64}$")
    entries: tuple[EvidenceEntry, ...] = ()
    context_symbols: tuple[ContextSymbol, ...] = ()
    gaps: tuple[str, ...] = ()
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()

    @field_validator("gaps")
    @classmethod
    def valid_gaps(cls, values):
        if len(values) > 256 or any(not v.strip() or len(v) > 1000 for v in values):
            raise ValueError("Gaps must be nonblank, <=1000 chars each, <=256 total")
        return values

    @model_validator(mode="after")
    def coherent(self) -> Self:
        ids = [entry.source.evidence_id for entry in self.entries]
        if ids != [f"E{i}" for i in range(1, len(ids) + 1)]:
            raise ValueError("Evidence IDs must be contiguous in pack order")
        nodes = [node.symbol_id for node in self.context_symbols]
        if len(nodes) != len(set(nodes)) or any(node.snapshot_id != self.snapshot_id for node in self.context_symbols):
            raise ValueError("Duplicate or mixed-snapshot graph metadata")
        for node in self.context_symbols:
            if any(p.symbol_ids[-1] != node.symbol_id for p in node.paths):
                raise ValueError("Graph metadata path terminal mismatch")
        chunks = [entry.source.chunk_id for entry in self.entries]
        if None in chunks or len(set(chunks)) != len(chunks):
            raise ValueError("Each entry must identify a unique stored chunk")
        for entry in self.entries:
            if entry.source.snapshot_id != self.snapshot_id:
                raise ValueError("Mixed snapshots in evidence pack")
            if any(p.symbol_ids[-1] != entry.source.symbol_id for p in entry.paths):
                raise ValueError("Evidence path terminal mismatch")
            if (entry.origin == "expanded") != bool(entry.paths):
                raise ValueError("Evidence origin/path mismatch")
        if self.truncated != bool(self.truncation_reasons):
            raise ValueError("Truncation flag/reasons mismatch")
        return self


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def build_evidence_pack(
    candidates, *, repository_id: int, snapshot_id: int,
    commit_sha: str | None = None, gaps=(), truncation_reasons=(), context_symbols=(),
    max_entries: int = 40, max_source_chars: int = 48_000,
) -> EvidencePack:
    """Assign IDs AFTER deterministic deduplication and whole-chunk budgeting.

    IDs are stable for the same scoped inputs/options, not across all queries.
    order is upstream context order; ties use chunk ID. No relevance re-ranking.
    """
    for value, name in ((repository_id,"repository_id"),(snapshot_id,"snapshot_id"),
                        (max_entries,"max_entries"),(max_source_chars,"max_source_chars")):
        _positive(value,name)
    if len(candidates) > 1000:
        raise ValueError("Pass a bounded retrieval result (<=1000 chunks)")
    unique = {}
    for candidate in candidates:
        candidate = EvidenceCandidate.model_validate(candidate.model_dump() if isinstance(candidate,EvidenceCandidate) else candidate)
        if candidate.repository_id != repository_id or candidate.snapshot_id != snapshot_id:
            raise ValueError("Mixed repository/snapshot evidence")
        previous = unique.get(candidate.chunk_id)
        if previous is not None and previous != candidate:
            raise ValueError("Conflicting duplicate chunk evidence")
        unique[candidate.chunk_id] = candidate
    gap_set, reasons = set(gaps), set(truncation_reasons)
    entries, used = [], 0
    for candidate in sorted(unique.values(), key=lambda c: (c.order,c.chunk_id)):
        if len(entries) >= max_entries:
            reasons.add("max_entries")
            gap_set.add("Evidence records were omitted by the entry budget")
            continue
        cost = len(candidate.text) + len(candidate.signature or "")
        if used + cost > max_source_chars:
            reasons.add("max_source_chars")
            gap_set.add("Whole source chunks were omitted by the source-character budget")
            continue
        used += cost
        source = Evidence(evidence_id=f"E{len(entries)+1}", snapshot_id=snapshot_id,
                          file_id=candidate.file_id,file_path=candidate.file_path,
                          symbol_id=candidate.symbol_id,chunk_id=candidate.chunk_id,
                          start_line=candidate.start_line,end_line=candidate.end_line,text=candidate.text)
        entries.append(EvidenceEntry(source=source,name=candidate.name,qualname=candidate.qualname,
                                     kind=candidate.kind,signature=candidate.signature,origin=candidate.origin,
                                     fused_score=candidate.fused_score,paths=candidate.paths))
    if not entries:
        gap_set.add("No citable source evidence is available in this pack")
    if reasons:
        gap_set.add("Context is incomplete: " + ", ".join(sorted(reasons)))
    return EvidencePack(repository_id=repository_id,snapshot_id=snapshot_id,commit_sha=commit_sha,
                        entries=tuple(entries),context_symbols=tuple(context_symbols),gaps=tuple(sorted(gap_set)),truncated=bool(reasons),
                        truncation_reasons=tuple(sorted(reasons)))


def _validated(pack):
    return EvidencePack.model_validate(pack.model_dump())


def serialize_evidence_pack(pack: EvidencePack) -> str:
    return json.dumps(_validated(pack).model_dump(mode="json"),ensure_ascii=False,
                      sort_keys=True,separators=(",",":"))


def citation_map(pack: EvidencePack) -> dict:
    return {entry.source.evidence_id:entry.model_dump(mode="json") for entry in _validated(pack).entries}


def render_evidence_pack(pack: EvidencePack) -> str:
    """Readable data-only context; caller must retain the structured ID mapping."""
    pack = _validated(pack)
    blocks = []
    for entry in pack.entries:
        metadata = entry.model_dump(mode="json")
        body = metadata["source"].pop("text")
        metadata["source"].pop("evidence_id")
        signature = metadata.pop("signature")
        runs = [len(match.group()) for match in re.finditer(r"`+",body)]
        fence = "`" * max(3, 1 + max(runs,default=0))
        blocks.append(f"[{entry.source.evidence_id}]\n" +
                      json.dumps(metadata,ensure_ascii=False,sort_keys=True) +
                      "\nSignature (JSON): " + json.dumps(signature,ensure_ascii=False) +
                      f"\n{fence}python\n{body}" + ("" if body.endswith("\n") else "\n") + fence)
    if pack.context_symbols:
        blocks.append("[CONTEXT_METADATA — NOT SOURCE CITATIONS]\n" +
                      json.dumps([node.model_dump(mode="json") for node in pack.context_symbols],
                                 ensure_ascii=False,sort_keys=True))
    blocks.extend("[GAP] " + json.dumps(gap,ensure_ascii=False) for gap in pack.gaps)
    return "\n\n".join(blocks)
