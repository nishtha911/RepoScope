from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from reposcope.api import health
from reposcope.contracts.api import ErrorDetail, ErrorResponse

# NOTE: do not import reposcope.config here; it raises at import time when
# DATABASE_URL is missing. Import it only in routes that need the database.

app = FastAPI(title="RepoScope API", version="1.0")

# --- CORS (Vite dev server) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Standard error envelope: {"error": {code, message, details, status}} ---
HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
}


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    envelope = ErrorResponse(error=ErrorDetail(
        code=code, message=message, details=details or {}, status=status,
    ))
    return JSONResponse(status_code=status, content=envelope.model_dump(mode="json"))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed",
        {"errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")


# --- Routers ---
from reposcope.api import repos

app.include_router(health.router, prefix="/api")
app.include_router(repos.router, prefix="/api")
