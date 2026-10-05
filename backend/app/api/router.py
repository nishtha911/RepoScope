from fastapi import APIRouter

from backend.app.api.v1 import chat, pr, repos, search, symbols

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(repos.router, prefix="/repos", tags=["repositories"])
api_router.include_router(search.router, prefix="/repos", tags=["search"])
api_router.include_router(symbols.router, prefix="/symbols", tags=["symbols"])
api_router.include_router(chat.router, prefix="/repos", tags=["chat"])
api_router.include_router(pr.router, prefix="/repos", tags=["pull requests"])