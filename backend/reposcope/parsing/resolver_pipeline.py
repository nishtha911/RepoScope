"""Public entry point for the Day 4 analysis pipeline."""
from dataclasses import dataclass

from reposcope.contracts.parsing import ParsedFile
from reposcope.contracts.resolution import ResolutionResult
from reposcope.parsing.binding_index import build_binding_index
from reposcope.parsing.reference_resolver import AnalysisEdge, resolve_references, resolved_edges
from reposcope.parsing.repo_index import build_repo_index
from reposcope.parsing.resolver import collect_references
from reposcope.parsing.scope_index import build_scope_index


@dataclass(frozen=True)
class ResolverAnalysis:
    results: tuple[ResolutionResult, ...]
    edges: tuple[AnalysisEdge, ...]


def analyze_python_files(
    parsed_files: list[ParsedFile], *, source_roots: tuple[str, ...] = (".",)
) -> ResolverAnalysis:
    repo = build_repo_index(parsed_files, source_roots=source_roots)
    scopes = build_scope_index(repo)
    bindings = build_binding_index(scopes)
    references = collect_references(bindings)
    results = resolve_references(references)
    return ResolverAnalysis(results=results, edges=resolved_edges(results))
