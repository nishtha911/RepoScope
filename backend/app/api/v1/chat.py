from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{repo_id}/ask")
def ask_repository(repo_id: int) -> None:
    raise HTTPException(status_code=501, detail="Repository Q&A is not implemented")