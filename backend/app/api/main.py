from fastapi import APIRouter

from app.api.routes import (
    avatar_assets,
    characters,
    diagnostics,
    items,
    live_sessions,
    login,
    private,
    users,
    utils,
    youtube,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(avatar_assets.router)
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(characters.router)
api_router.include_router(diagnostics.router)
api_router.include_router(live_sessions.router)
api_router.include_router(youtube.router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
