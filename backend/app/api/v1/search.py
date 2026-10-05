from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{repo_id}/search")
def search_repository(repo_id: int) -> None:
    raise HTTPException(status_code=501, detail="Hybrid search is not implemented")