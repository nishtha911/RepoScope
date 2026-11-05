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
    reference_paths=None,
    cached_results=(),
) -> ResolverAnalysis:
    repo = build_repo_index(parsed_files, source_roots=source_roots)
    scopes = build_scope_index(repo)
    bindings = build_binding_index(scopes)
    references = collect_references(bindings)

    paths = None if reference_paths is None else frozenset(reference_paths)
    if paths is None and cached_results:
        raise ValueError("cached_results requires reference_paths")
    if paths is not None and not paths <= set(repo.files_by_path):
        raise ValueError("Unknown reference path")
    retained = tuple(
        result for result in cached_results
        if result.reference.file_path in repo.files_by_path
        and result.reference.file_path not in paths
    ) if paths is not None else ()
    first_results = retained + resolve_references(
        references, reference_paths=paths,
    )
    def ordered(rows):
        return tuple(sorted(rows, key=lambda result: (
            result.reference.file_path, result.reference.start_byte,
            result.reference.end_byte, result.reference.reference_kind,
        )))
    first_results = ordered(first_results)
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
        results = retained + resolve_references(
            references,
            supported_sqlmodel_locations=verified_locations,
            reference_paths=paths,
        )
    else:
        results = first_results

    return ResolverAnalysis(
        results=ordered(results),
        edges=resolved_edges(ordered(results)),
    )
