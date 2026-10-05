from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/{symbol_id}")
def get_symbol(symbol_id: int) -> None:
    raise HTTPException(status_code=501, detail="Symbol lookup is not implemented")


@router.get("/{symbol_id}/neighbors")
def get_symbol_neighbors(symbol_id: int) -> None:
    raise HTTPException(status_code=501, detail="Graph traversal is not implemented")