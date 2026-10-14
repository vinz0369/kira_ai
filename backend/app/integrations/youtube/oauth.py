from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow  # type: ignore[import-untyped]
from sqlmodel import Session, select

from app.core.config import settings
from app.integrations.youtube.security import (
    TokenCipher,
    hash_oauth_state,
    new_code_verifier,
    new_oauth_state,
)
from app.models import OAuthAttempt, OAuthConnection

PROVIDER = "google_youtube"


class YouTubeNotConfiguredError(RuntimeError):
    pass


class OAuthStateError(ValueError):
    pass


def _require_configuration() -> TokenCipher:
    if not settings.youtube_configured or not settings.DATA_ENCRYPTION_KEY:
        raise YouTubeNotConfiguredError(
            "Google OAuth is not configured on this server"
        )
    return TokenCipher(settings.DATA_ENCRYPTION_KEY)


def _client_config() -> dict[str, Any]:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise YouTubeNotConfiguredError(
            "Google OAuth is not configured on this server"
        )
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def _flow(*, state: str | None = None, code_verifier: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=settings.youtube_scopes,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    return flow


def begin_authorization(db: Session, owner_id: uuid.UUID) -> str:
    cipher = _require_configuration()
    state = new_oauth_state()
    verifier = new_code_verifier()
    flow = _flow(state=state, code_verifier=verifier)
    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    if returned_state != state:
        raise OAuthStateError("OAuth client changed the state value")
    attempt = OAuthAttempt(
        owner_id=owner_id,
        state_hash=hash_oauth_state(state),
        encrypted_code_verifier=cipher.encrypt(verifier),
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.OAUTH_STATE_TTL_SECONDS),
    )
    db.add(attempt)
    db.commit()
    return str(authorization_url)


def consume_attempt(db: Session, state: str) -> tuple[OAuthAttempt, str]:
    cipher = _require_configuration()
    state_hash = hash_oauth_state(state)
    attempt = db.exec(
        select(OAuthAttempt).where(OAuthAttempt.state_hash == state_hash)
    ).first()
    now = datetime.now(UTC)
    if not attempt or attempt.consumed_at is not None or attempt.expires_at <= now:
        raise OAuthStateError("OAuth state is invalid, expired, or already used")
    attempt.consumed_at = now
    db.add(attempt)
    db.commit()
    return attempt, cipher.decrypt(attempt.encrypted_code_verifier)


async def exchange_code(code: str, state: str, verifier: str) -> Credentials:
    flow = _flow(state=state, code_verifier=verifier)
    await asyncio.to_thread(flow.fetch_token, code=code)
    return cast(Credentials, flow.credentials)


def credentials_from_connection(connection: OAuthConnection) -> Credentials:
    cipher = _require_configuration()
    return Credentials(  # type: ignore[no-untyped-call]
        token=cipher.decrypt(connection.encrypted_access_token),
        refresh_token=(
            cipher.decrypt(connection.encrypted_refresh_token)
            if connection.encrypted_refresh_token
            else None
        ),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.youtube_scopes,
        expiry=_expiry_for_google(connection.expires_at),
    )


def _expiry_for_storage(expiry: datetime | None) -> datetime | None:
    if expiry is None:
        return None
    # google-auth represents UTC expiry as naive; PostgreSQL requires an offset.
    return expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)


def _expiry_for_google(expiry: datetime | None) -> datetime | None:
    if expiry is None:
        return None
    # google-auth compares expiry with its own naive UTC clock.
    return expiry.astimezone(UTC).replace(tzinfo=None) if expiry.tzinfo else expiry


def save_connection(
    db: Session,
    owner_id: uuid.UUID,
    credentials: Credentials,
    channel_id: str | None,
    channel_name: str | None,
) -> OAuthConnection:
    cipher = _require_configuration()
    expected = set(settings.youtube_scopes)
    granted = set(credentials.granted_scopes or credentials.scopes or [])
    if not expected.issubset(granted):
        raise PermissionError("Google did not grant youtube.readonly")
    connection = db.exec(
        select(OAuthConnection).where(
            OAuthConnection.owner_id == owner_id,
            OAuthConnection.provider == PROVIDER,
        )
    ).first()
    existing_refresh = connection.encrypted_refresh_token if connection else None
    if connection is None:
        connection = OAuthConnection(
            owner_id=owner_id,
            encrypted_access_token="",
        )
    connection.encrypted_access_token = cipher.encrypt(credentials.token or "")
    connection.encrypted_refresh_token = (
        cipher.encrypt(credentials.refresh_token)
        if credentials.refresh_token
        else existing_refresh
    )
    connection.expires_at = _expiry_for_storage(credentials.expiry)
    connection.granted_scopes = " ".join(sorted(granted))
    connection.provider_channel_id = channel_id
    connection.provider_channel_name = channel_name
    connection.status = "connected"
    connection.last_error_code = None
    connection.updated_at = datetime.now(UTC)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def get_connection(db: Session, owner_id: uuid.UUID) -> OAuthConnection | None:
    return db.exec(
        select(OAuthConnection).where(
            OAuthConnection.owner_id == owner_id,
            OAuthConnection.provider == PROVIDER,
        )
    ).first()


async def usable_credentials(
    db: Session, connection: OAuthConnection
) -> Credentials:
    credentials = credentials_from_connection(connection)
    if not credentials.valid:
        if not credentials.refresh_token:
            connection.status = "reauthorize"
            connection.last_error_code = "missing_refresh_token"
            db.add(connection)
            db.commit()
            raise PermissionError("Google connection needs authorization again")
        try:
            await asyncio.to_thread(credentials.refresh, Request())
        except Exception:
            connection.status = "reauthorize"
            connection.last_error_code = "refresh_failed"
            db.add(connection)
            db.commit()
            raise
        cipher = _require_configuration()
        connection.encrypted_access_token = cipher.encrypt(credentials.token or "")
        if credentials.refresh_token:
            connection.encrypted_refresh_token = cipher.encrypt(
                credentials.refresh_token
            )
        connection.expires_at = _expiry_for_storage(credentials.expiry)
        connection.status = "connected"
        connection.last_error_code = None
        connection.updated_at = datetime.now(UTC)
        db.add(connection)
        db.commit()
    return credentials
