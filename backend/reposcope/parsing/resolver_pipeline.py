"""Public entry point for Python reference analysis."""

from dataclasses import dataclass

from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import ResolutionResult
from reposcope.parsing.binding_index import build_binding_index
from reposcope.parsing.reference_resolver import (
    AnalysisEdge,
    resolve_references,
    resolved_edges,
)
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.repository_models import detect_repository_models
from reposcope.parsing.resolver import collect_references
from reposcope.parsing.scope_index import build_scope_index


@dataclass(frozen=True)
class ResolverAnalysis:
    results: tuple[ResolutionResult, ...]
    edges: tuple[AnalysisEdge, ...]


def analyze_python_files(
    parsed_files: list[ParsedFile],
    *,
    source_roots: tuple[str, ...] = (".",),
) -> ResolverAnalysis:
    repo = build_repo_index(parsed_files, source_roots=source_roots)
    scopes = build_scope_index(repo)
    bindings = build_binding_index(scopes)
    references = collect_references(bindings)

    first_results = resolve_references(references)
    model_detection = detect_repository_models(
        list(repo.files_by_path.values()),
        first_results,
    )
    verified_sqlmodel_keys = {
        model.symbol_key
        for model in model_detection.models
        if model.framework == "sqlmodel"
    }
    verified_locations = {
        (path, symbol.definition_start_byte)
        for path, parsed in repo.files_by_path.items()
        for symbol in parsed.symbols
        if symbol.local_key in verified_sqlmodel_keys
    }

    if verified_locations:
        results = resolve_references(
            references,
            supported_sqlmodel_locations=verified_locations,
        )
    else:
        results = first_results

    return ResolverAnalysis(
        results=results,
        edges=resolved_edges(results),
    )