from fastapi import APIRouter

router = APIRouter(tags=["health"])

API_VERSION = "1.0"


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Intentionally does not touch the database."""
    return {"status": "ok", "v": API_VERSION}
