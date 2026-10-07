from typing import Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/repos", tags=["repos"])


class RegisterRepoRequest(BaseModel):
    url: str


class SearchRequest(BaseModel):
    q: str
    mode: str = "hybrid"


class AskRequest(BaseModel):
    question: str


class PRImpactRequest(BaseModel):
    pr_url: str


class FeedbackRequest(BaseModel):
    action: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def register_repo(payload: RegisterRepoRequest) -> dict[str, Any]:
    return {
        "repo_id": 1,
        "status": "pending",
        "message": "Repository ingestion enqueued",
    }


@router.get("/{repo_id}")
def get_repo(repo_id: int) -> dict[str, Any]:
    if repo_id <= 0:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {
        "id": repo_id,
        "url": "https://github.com/nishtha911/RepoScope",
        "name": "nishtha911/RepoScope",
        "default_branch": "main",
        "status": "ready",
        "head_sha": "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60",
        "symbol_count": 3412,
        "file_count": 142,
    }


@router.get("/{repo_id}/symbols")
def get_symbols(
    repo_id: int, q: str = "", kind: str = "", limit: int = 20
) -> dict[str, Any]:
    return {
        "symbols": [
            {
                "id": 101,
                "name": "resolve_calls",
                "qualname": "SymbolResolver.resolve_calls",
                "kind": "METHOD",
                "file_path": "backend/reposcope/parsing/resolver.py",
                "start_line": 142,
                "end_line": 180,
            }
        ]
    }


@router.post("/{repo_id}/search")
def search_repo(repo_id: int, payload: SearchRequest) -> dict[str, Any]:
    return {
        "query": payload.q,
        "hits": [
            {
                "symbol_id": 101,
                "name": "SymbolResolver.resolve_calls",
                "score": 0.032,
                "file_path": "backend/reposcope/parsing/resolver.py",
                "snippet": "def resolve_calls(self, ast_tree):",
            }
        ],
    }


@router.post("/{repo_id}/ask")
def ask_repo(repo_id: int, payload: AskRequest) -> dict[str, Any]:
    return {
        "answer": f"Analysis for query: '{payload.question}'. Scope resolver resolves function calls against the symbol table [E1].",
        "evidence": [
            {
                "evidence_id": "E1",
                "snapshot_id": 1,
                "file_id": 12,
                "file_path": "backend/reposcope/parsing/resolver.py",
                "symbol_id": 101,
                "chunk_id": 5,
                "start_line": 142,
                "end_line": 160,
                "text": "def resolve_calls(self, ast_tree): ...",
            }
        ],
        "gaps": [],
    }


@router.post("/{repo_id}/pr-impact")
def pr_impact(repo_id: int, payload: PRImpactRequest) -> dict[str, Any]:
    return {
        "pr_url": payload.pr_url,
        "risk_level": "LOW",
        "risk_score": 0.04,
        "files_changed_count": 3,
        "impacted_symbols_count": 14,
        "affected_endpoints_count": 0,
        "impacted_tests_count": 2,
        "summary": "Modifies internal helper methods in resolver.py without API signature breaking changes.",
    }


@router.get("/{repo_id}/recommendations")
def get_recommendations(repo_id: int, k: int = 10) -> dict[str, Any]:
    return {
        "recommendations": [
            {
                "id": 1,
                "snapshot_id": 1,
                "symbol_id": 101,
                "category": "UNTESTED_HOTSPOT",
                "title": "Add unit test for SymbolResolver.resolve_calls",
                "description": "High fan-in symbol lacks direct unit test coverage.",
                "score": 0.94,
                "confidence": 0.9,
            }
        ]
    }


@router.get("/symbols/{symbol_id}")
def get_symbol_detail(symbol_id: int) -> dict[str, Any]:
    return {
        "id": symbol_id,
        "file_id": 12,
        "name": "resolve_calls",
        "kind": "METHOD",
        "start_line": 142,
        "end_line": 180,
        "signature": "def resolve_calls(self, ast_tree) -> list[Edge]:",
        "docstring": "Resolves call expressions to candidate symbol IDs.",
        "cyclomatic_complexity": 4,
    }


@router.get("/symbols/{symbol_id}/neighbors")
def get_symbol_neighbors(
    symbol_id: int, dir: str = "out", types: str = ""
) -> dict[str, Any]:
    return {
        "neighbors": [
            {
                "symbol_id": 204,
                "name": "SymbolScanner.scan",
                "relationship_type": "CALLS",
                "confidence": 1.0,
                "direction": dir,
            }
        ]
    }


@router.post("/recs/{rec_id}/feedback")
def submit_feedback(rec_id: int, payload: FeedbackRequest) -> dict[str, Any]:
    return {
        "status": "ok",
        "id": rec_id,
        "action": payload.action,
    }
