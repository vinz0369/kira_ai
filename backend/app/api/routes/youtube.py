from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.integrations.youtube.ingest import youtube_ingest_manager
from app.integrations.youtube.oauth import (
    OAuthStateError,
    YouTubeNotConfiguredError,
    begin_authorization,
    consume_attempt,
    exchange_code,
    get_connection,
    save_connection,
    usable_credentials,
)
from app.integrations.youtube.provider import (
    YouTubeProviderError,
    build_youtube,
    channel_identity,
    classify_http_error,
    list_active_broadcasts,
    resolve_live_video,
)
from app.integrations.youtube.security import TokenCipher
from app.models import LiveSession, OAuthAttempt, OAuthConnection

router = APIRouter(prefix="/youtube", tags=["youtube"])


class AuthorizationUrlPublic(SQLModel):
    authorization_url: str


class YouTubeConnectionPublic(SQLModel):
    configured: bool
    connected: bool
    status: str
    channel_id: str | None = None
    channel_name: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    needs_reconnect: bool = False
    last_error_code: str | None = None


class BroadcastPublic(SQLModel):
    id: str
    title: str
    live_chat_id: str
    actual_start_time: str | None = None
    life_cycle_status: str


class ResolveBroadcastRequest(SQLModel):
    video_url: str = Field(min_length=1, max_length=512)


class DisconnectPublic(SQLModel):
    disconnected: bool
    revocation_status: str


def _connection_public(connection: OAuthConnection | None) -> YouTubeConnectionPublic:
    if not settings.youtube_configured:
        return YouTubeConnectionPublic(
            configured=False,
            connected=False,
            status="not_configured",
            needs_reconnect=False,
        )
    if not connection:
        return YouTubeConnectionPublic(
            configured=True,
            connected=False,
            status="disconnected",
        )
    return YouTubeConnectionPublic(
        configured=True,
        connected=connection.status in {"connected", "degraded"},
        status=connection.status,
        channel_id=connection.provider_channel_id,
        channel_name=connection.provider_channel_name,
        granted_scopes=connection.granted_scopes.split(),
        expires_at=connection.expires_at,
        needs_reconnect=connection.status == "reauthorize",
        last_error_code=connection.last_error_code,
    )


@router.get("/connection", response_model=YouTubeConnectionPublic)
def read_connection(
    db: SessionDep, current_user: CurrentUser
) -> YouTubeConnectionPublic:
    return _connection_public(get_connection(db, current_user.id))


@router.post("/oauth/authorize", response_model=AuthorizationUrlPublic)
def authorize(
    db: SessionDep, current_user: CurrentUser
) -> AuthorizationUrlPublic:
    try:
        url = begin_authorization(db, current_user.id)
    except YouTubeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return AuthorizationUrlPublic(authorization_url=url)


def _callback_redirect(status: str, reason: str | None = None) -> RedirectResponse:
    query: dict[str, str] = {"youtube": status}
    if reason:
        query["reason"] = reason
    return RedirectResponse(
        f"{settings.FRONTEND_HOST.rstrip('/')}/settings/connections?{urlencode(query)}",
        status_code=303,
    )


@router.get("/oauth/callback", response_model=None)
async def oauth_callback(
    db: SessionDep,
    state: str = Query(min_length=20, max_length=512),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = Query(default=None, max_length=100),
) -> Any:
    try:
        attempt, verifier = consume_attempt(db, state)
    except (OAuthStateError, YouTubeNotConfiguredError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if error:
        return _callback_redirect("denied", "access_denied")
    if not code:
        raise HTTPException(status_code=400, detail="OAuth code is missing")
    try:
        credentials = await exchange_code(code, state, verifier)
    except Exception:
        return _callback_redirect("error", "token_exchange_failed")
    try:
        youtube = build_youtube(credentials)
        channel_id, channel_name = await channel_identity(youtube)
    except HttpError as exc:
        code = classify_http_error(exc).code
        reason = (
            code
            if code in {"youtube_api_disabled", "quota_exceeded"}
            else "channel_lookup_failed"
        )
        return _callback_redirect("error", reason)
    except Exception:
        return _callback_redirect("error", "channel_lookup_failed")
    try:
        save_connection(
            db, attempt.owner_id, credentials, channel_id, channel_name
        )
    except PermissionError:
        return _callback_redirect("error", "insufficient_scope")
    except Exception:
        return _callback_redirect("error", "connection_store_failed")
    return _callback_redirect("connected")


@router.get("/broadcasts", response_model=list[BroadcastPublic])
async def broadcasts(
    db: SessionDep, current_user: CurrentUser
) -> list[BroadcastPublic]:
    connection = get_connection(db, current_user.id)
    if not connection:
        raise HTTPException(status_code=409, detail="Connect YouTube first")
    try:
        credentials = await usable_credentials(db, connection)
        youtube = build_youtube(credentials)
        items = await list_active_broadcasts(youtube)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Reconnect YouTube")
    except YouTubeProviderError as exc:
        connection.status = (
            "reauthorize"
            if exc.code in {"auth_expired", "insufficient_scope"}
            else "degraded"
        )
        connection.last_error_code = exc.code
        db.add(connection)
        db.commit()
        raise HTTPException(status_code=503, detail=exc.code)
    if connection.status != "connected" or connection.last_error_code:
        connection.status = "connected"
        connection.last_error_code = None
        db.add(connection)
        db.commit()
    return [BroadcastPublic(**item.__dict__) for item in items]


@router.post("/broadcasts/resolve", response_model=BroadcastPublic)
async def resolve_broadcast(
    request: ResolveBroadcastRequest, db: SessionDep, current_user: CurrentUser
) -> BroadcastPublic:
    connection = get_connection(db, current_user.id)
    if not connection:
        raise HTTPException(status_code=409, detail="Connect YouTube first")
    try:
        credentials = await usable_credentials(db, connection)
        broadcast = await resolve_live_video(
            build_youtube(credentials), request.video_url, connection.provider_channel_id
        )
    except PermissionError:
        raise HTTPException(status_code=401, detail="Reconnect YouTube")
    except YouTubeProviderError as exc:
        raise HTTPException(status_code=409, detail=exc.code)
    return BroadcastPublic(**broadcast.__dict__)


@router.delete("/connection", response_model=DisconnectPublic)
async def disconnect(
    db: SessionDep, current_user: CurrentUser
) -> DisconnectPublic:
    connection = get_connection(db, current_user.id)
    if not connection:
        return DisconnectPublic(disconnected=True, revocation_status="not_connected")

    active_sessions = db.exec(
        select(LiveSession).where(
            LiveSession.owner_id == current_user.id,
            LiveSession.mode == "youtube",
            col(LiveSession.status).in_(["active", "paused"]),
        )
    ).all()
    for live_session in active_sessions:
        await youtube_ingest_manager.stop(live_session.id)
        live_session.youtube_ingest_status = "disconnected"
        live_session.youtube_last_error = "oauth_disconnected"
        db.add(live_session)

    revocation_status = "not_attempted"
    try:
        if not settings.DATA_ENCRYPTION_KEY:
            raise ValueError("missing encryption key")
        cipher = TokenCipher(settings.DATA_ENCRYPTION_KEY)
        encrypted = (
            connection.encrypted_refresh_token
            or connection.encrypted_access_token
        )
        token = cipher.decrypt(encrypted)
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        revocation_status = "revoked" if response.status_code == 200 else "unconfirmed"
    except (httpx.HTTPError, ValueError):
        revocation_status = "unconfirmed"

    attempts = db.exec(
        select(OAuthAttempt).where(OAuthAttempt.owner_id == current_user.id)
    ).all()
    for attempt in attempts:
        db.delete(attempt)
    db.delete(connection)
    db.commit()
    return DisconnectPublic(
        disconnected=True, revocation_status=revocation_status
    )
