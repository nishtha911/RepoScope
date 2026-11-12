"""Day 11 deterministic candidate detection; no database writes or ranking.

Input must describe one repository snapshot. Missing enrichment is unknown,
not evidence of absence. TESTED_BY points from implementation to test.
"""
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from reposcope.contracts.symbol import Symbol
from reposcope.contracts.edge import Edge
from reposcope.contracts.finding import Finding


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CandidateSymbol(Record):
    symbol: Symbol
    filepath: str = Field(min_length=1)
    is_test: bool | None = None
    cyclomatic_complexity: int | None = Field(default=None, ge=1, strict=True)
    complexity_policy: str | None = Field(default=None, min_length=1)
    docstring: str | None = None
    documentation_known: bool = False

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        if self.symbol.id is None:
            raise ValueError("Candidate symbols require persisted IDs")
        if (self.cyclomatic_complexity is None) != (self.complexity_policy is None):
            raise ValueError("Complexity and its policy must be supplied together")
        if self.docstring is not None and not self.documentation_known:
            raise ValueError("Docstring requires documentation_known=True")
        return self


class CandidateDataset(Record):
    repo_id: int = Field(gt=0, strict=True)
    snapshot_id: int = Field(gt=0, strict=True)
    symbols: tuple[CandidateSymbol, ...] = ()
    edges: tuple[Edge, ...] = ()
    test_links_complete: bool = False

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        ids = [s.symbol.id for s in self.symbols]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate symbol IDs")
        filepaths, pathfiles = {}, {}
        for row in self.symbols:
            sid = row.symbol.file_id
            if sid in filepaths and filepaths[sid] != row.filepath:
                raise ValueError("Inconsistent file metadata")
            if row.filepath in pathfiles and pathfiles[row.filepath] != sid:
                raise ValueError("One snapshot path cannot have multiple file IDs")
            filepaths[sid], pathfiles[row.filepath] = row.filepath, sid
        for edge in self.edges:
            if edge.source_symbol_id not in ids or edge.target_symbol_id not in ids:
                raise ValueError("Edge references a symbol outside this dataset")
        return self


class DetectorConfig(Record):
    min_fan_in: int = Field(default=5, ge=1, strict=True)
    min_complexity: int = Field(default=10, ge=1, strict=True)
    min_edge_confidence: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)


class CandidateGap(Record):
    symbol_id: int = Field(gt=0)
    code: str
    detail: str


class CandidateEvidence(Record):
    category: str
    symbol_id: int = Field(gt=0)
    related_symbol_ids: tuple[int, ...] = ()
    measured_value: int | None = None
    threshold: int | None = None
    policy: str | None = None


class CandidateReport(Record):
    repo_id: int
    snapshot_id: int
    findings: tuple[Finding, ...]
    evidence: tuple[CandidateEvidence, ...]
    gaps: tuple[CandidateGap, ...]


def detect_candidates(dataset: CandidateDataset, config: DetectorConfig | None = None) -> CandidateReport:
    """Return stable, unranked findings. Input scoping is the loader's responsibility.

    Endpoint documentation policy v1 requires a nonblank handler docstring.
    It does not assess OpenAPI completeness or external documentation.
    """
    config = config or DetectorConfig()
    rows = {r.symbol.id: r for r in dataset.symbols}
    callers, tests, handlers = {}, {}, {}
    for edge in dataset.edges:
        src, dst = edge.source_symbol_id, edge.target_symbol_id
        if edge.kind == "TESTED_BY":
            # Any recorded association blocks an absence claim, even low-confidence.
            tests.setdefault(src, set()).add(dst)
        if edge.confidence is None or edge.confidence < config.min_edge_confidence:
            continue
        if edge.kind == "CALLS" and src != dst:
            if rows[src].symbol.kind == "endpoint":
                handlers.setdefault(src, set()).add(dst)
            elif rows[src].is_test is False:
                callers.setdefault(dst, set()).add(src)
    findings, evidence, gaps = [], [], []

    def gap(sid, code, detail):
        gaps.append(CandidateGap(symbol_id=sid, code=code, detail=detail))

    def emit(row, category, title, description, **facts):
        findings.append(Finding(snapshot_id=dataset.snapshot_id,
            symbol_id=row.symbol.id, file_id=row.symbol.file_id,
            category=category, title=title, description=description))
        evidence.append(CandidateEvidence(category=category, symbol_id=row.symbol.id, **facts))

    for sid, row in sorted(rows.items()):
        sym = row.symbol
        name = sym.qualname or sym.name
        if sym.kind in ("function", "method"):
            if row.is_test is None:
                gap(sid, "TEST_ROLE_UNKNOWN", "Callable excluded until its test role is known")
                continue
            if row.is_test:
                continue
            incoming = tuple(sorted(callers.get(sid, ())))
            if len(incoming) >= config.min_fan_in and not tests.get(sid):
                if not dataset.test_links_complete:
                    gap(sid, "TEST_LINKS_INCOMPLETE", "Cannot claim no known links from incomplete test-link input")
                else:
                    emit(row, "UNTESTED_HOTSPOT", f"Add linked tests for {name}",
                        f"{len(incoming)} distinct known non-test callers; no TESTED_BY links in the supplied complete static index. This is not runtime coverage.",
                        related_symbol_ids=incoming, measured_value=len(incoming), threshold=config.min_fan_in)
            if row.cyclomatic_complexity is None:
                gap(sid, "COMPLEXITY_UNKNOWN", "No measured complexity supplied")
            elif row.cyclomatic_complexity >= config.min_complexity:
                emit(row, "COMPLEXITY_HOTSPOT", f"Simplify {name}",
                    f"Measured cyclomatic complexity {row.cyclomatic_complexity} meets threshold {config.min_complexity} under {row.complexity_policy}.",
                    measured_value=row.cyclomatic_complexity, threshold=config.min_complexity, policy=row.complexity_policy)
        elif sym.kind == "endpoint":
            linked = tuple(sorted(handlers.get(sid, ())))
            if len(linked) != 1:
                gap(sid, "ENDPOINT_HANDLER_UNKNOWN", "Requires exactly one eligible endpoint-to-handler CALLS link")
                continue
            handler = rows[linked[0]]
            if handler.symbol.kind not in ("function", "method"):
                gap(sid, "ENDPOINT_HANDLER_INVALID", "Endpoint target is not a callable")
            elif not handler.documentation_known:
                gap(sid, "DOCUMENTATION_UNKNOWN", "Handler documentation was not inspected")
            elif not (handler.docstring or "").strip():
                emit(row, "API_DOC_GAP", f"Document endpoint {name}",
                    "The linked handler has no nonblank docstring under handler_docstring_v1; external/OpenAPI documentation was not assessed.",
                    related_symbol_ids=linked, policy="handler_docstring_v1")
    return CandidateReport(repo_id=dataset.repo_id, snapshot_id=dataset.snapshot_id,
        findings=tuple(findings), evidence=tuple(evidence),
        gaps=tuple(sorted(gaps, key=lambda g: (g.symbol_id, g.code))))
