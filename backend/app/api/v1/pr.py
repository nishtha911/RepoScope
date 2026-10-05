from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{repo_id}/pull-requests/analyze")
def analyze_pull_request(repo_id: int) -> None:
    raise HTTPException(status_code=501, detail="Pull request analysis is not implemented")