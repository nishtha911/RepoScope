from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.repo import Repository
from backend.app.db.session import get_db
from backend.app.schemas.repo import RepoCreate, RepoRead

router = APIRouter()


@router.get("", response_model=list[RepoRead])
def list_repositories(db: Session = Depends(get_db)) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.id)).all())


@router.post("", response_model=RepoRead, status_code=status.HTTP_201_CREATED)
def create_repository(
    payload: RepoCreate,
    db: Session = Depends(get_db),
) -> Repository:
    existing = db.scalar(
        select(Repository).where(Repository.full_name == payload.full_name)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Repository already exists")

    repository = Repository(**payload.model_dump(mode="json"))
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository