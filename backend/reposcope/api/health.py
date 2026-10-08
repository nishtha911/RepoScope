from fastapi import APIRouter
from reposcope.contracts.api import HealthResponse

router = APIRouter(tags=["health"])
API_VERSION = "1.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check. Intentionally does not touch the database."""
    return HealthResponse(status="ok", v=API_VERSION)
