from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials
from sqlmodel import Session, select

from app.core.config import settings
from app.integrations.youtube.oauth import (
    credentials_from_connection,
    get_connection,
    save_connection,
)
from app.integrations.youtube.provider import ActiveBroadcast
from app.models import User


def test_connection_status_is_honest_when_not_configured(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", None)
    response = client.get(
        f"{settings.API_V1_STR}/youtube/connection",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "connected": False,
        "status": "not_configured",
        "channel_id": None,
        "channel_name": None,
        "granted_scopes": [],
        "expires_at": None,
        "needs_reconnect": False,
        "last_error_code": None,
    }


def test_authorize_endpoint_uses_backend_state_and_pkce(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(
        settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    response = client.post(
        f"{settings.API_V1_STR}/youtube/oauth/authorize",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    query = parse_qs(urlparse(authorization_url).query)
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
    assert "server-secret" not in authorization_url

    mismatch = client.get(
        f"{settings.API_V1_STR}/youtube/oauth/callback",
        params={"state": "unknown-state-value-long-enough", "code": "unused"},
        follow_redirects=False,
    )
    assert mismatch.status_code == 400
    assert "invalid" in mismatch.json()["detail"].lower()


def test_oauth_callback_binds_connection_without_exposing_tokens(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(
        settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    authorize = client.post(
        f"{settings.API_V1_STR}/youtube/oauth/authorize",
        headers=normal_user_token_headers,
    )
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)[
        "state"
    ][0]
    credentials = Credentials(
        token="callback-access-token",
        refresh_token="callback-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.youtube_scopes,
        granted_scopes=settings.youtube_scopes,
        expiry=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )

    async def fake_exchange(*_args: object) -> Credentials:
        return credentials

    async def fake_channel(_youtube: object) -> tuple[str, str]:
        return "channel-callback", "Callback Channel"

    monkeypatch.setattr("app.api.routes.youtube.exchange_code", fake_exchange)
    monkeypatch.setattr(
        "app.api.routes.youtube.build_youtube", lambda _credentials: object()
    )
    monkeypatch.setattr("app.api.routes.youtube.channel_identity", fake_channel)
    callback = client.get(
        f"{settings.API_V1_STR}/youtube/oauth/callback",
        params={"state": state, "code": "one-use-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"].endswith(
        "/settings/connections?youtube=connected"
    )
    assert "one-use-code" not in callback.headers["location"]
    status = client.get(
        f"{settings.API_V1_STR}/youtube/connection",
        headers=normal_user_token_headers,
    ).json()
    assert status["connected"] is True
    assert status["channel_name"] == "Callback Channel"
    assert status["expires_at"] is not None
    assert "callback-access-token" not in str(status)

    owner = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).one()
    connection = get_connection(db, owner.id)
    assert connection is not None
    assert connection.expires_at is not None
    assert connection.expires_at.tzinfo is not None
    reloaded_credentials = credentials_from_connection(connection)
    assert reloaded_credentials.expiry is not None
    assert reloaded_credentials.expiry.tzinfo is None
    assert reloaded_credentials.valid
    db.delete(connection)
    db.commit()


@pytest.mark.parametrize(
    ("failure_stage", "expected_reason"),
    [
        ("exchange", "token_exchange_failed"),
        ("channel", "channel_lookup_failed"),
        ("store", "connection_store_failed"),
    ],
)
def test_oauth_callback_reports_safe_failure_stage(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(
        settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    authorize = client.post(
        f"{settings.API_V1_STR}/youtube/oauth/authorize",
        headers=normal_user_token_headers,
    )
    assert authorize.status_code == 200
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)[
        "state"
    ][0]
    credentials = Credentials(
        token="never-expose-token",
        scopes=settings.youtube_scopes,
    )

    async def fake_exchange(*_args: object) -> Credentials:
        if failure_stage == "exchange":
            raise RuntimeError("sensitive-provider-detail")
        return credentials

    async def fake_channel(_youtube: object) -> tuple[str, str]:
        if failure_stage == "channel":
            raise RuntimeError("sensitive-provider-detail")
        return "channel-id", "Channel"

    def fake_store(*_args: object) -> None:
        raise RuntimeError("sensitive-provider-detail")

    monkeypatch.setattr("app.api.routes.youtube.exchange_code", fake_exchange)
    monkeypatch.setattr(
        "app.api.routes.youtube.build_youtube", lambda _credentials: object()
    )
    monkeypatch.setattr("app.api.routes.youtube.channel_identity", fake_channel)
    monkeypatch.setattr("app.api.routes.youtube.save_connection", fake_store)
    callback = client.get(
        f"{settings.API_V1_STR}/youtube/oauth/callback",
        params={"state": state, "code": "one-use-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert parse_qs(urlparse(callback.headers["location"]).query) == {
        "youtube": ["error"],
        "reason": [expected_reason],
    }
    assert "one-use-code" not in callback.headers["location"]
    assert "never-expose-token" not in callback.headers["location"]
    assert "sensitive-provider-detail" not in callback.headers["location"]


def test_youtube_routes_require_template_auth(client: TestClient) -> None:
    assert (
        client.get(f"{settings.API_V1_STR}/youtube/connection").status_code == 401
    )
    assert (
        client.post(f"{settings.API_V1_STR}/youtube/oauth/authorize").status_code
        == 401
    )
    assert (
        client.get(f"{settings.API_V1_STR}/youtube/broadcasts").status_code == 401
    )


def test_provider_error_does_not_require_oauth_reconnect_and_success_recovers(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(
        settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    owner = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).one()
    credentials = Credentials(token="synthetic-token", scopes=settings.youtube_scopes)
    connection = save_connection(db, owner.id, credentials, "channel-1", "Channel")
    connection.status = "degraded"
    connection.last_error_code = "incompatibleParameters"
    db.add(connection)
    db.commit()

    status = client.get(
        f"{settings.API_V1_STR}/youtube/connection",
        headers=normal_user_token_headers,
    ).json()
    assert status["connected"] is True
    assert status["needs_reconnect"] is False
    assert status["last_error_code"] == "incompatibleParameters"

    async def fake_usable(*_args: object) -> Credentials:
        return credentials

    async def fake_broadcasts(_youtube: object) -> list[ActiveBroadcast]:
        return []

    monkeypatch.setattr("app.api.routes.youtube.usable_credentials", fake_usable)
    monkeypatch.setattr(
        "app.api.routes.youtube.build_youtube", lambda _credentials: object()
    )
    monkeypatch.setattr(
        "app.api.routes.youtube.list_active_broadcasts", fake_broadcasts
    )
    response = client.get(
        f"{settings.API_V1_STR}/youtube/broadcasts",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json() == []
    db.refresh(connection)
    assert connection.status == "connected"
    assert connection.last_error_code is None
    db.delete(connection)
    db.commit()


def test_disconnect_revokes_and_deletes_encrypted_tokens(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", key)
    owner = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).one()
    credentials = Credentials(
        token="plain-access-token",
        refresh_token="plain-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.youtube_scopes,
    )
    connection = save_connection(
        db, owner.id, credentials, "channel-1", "Test Channel"
    )
    assert "plain-access-token" not in connection.encrypted_access_token
    assert "plain-refresh-token" not in str(connection.encrypted_refresh_token)

    posted_tokens: list[str] = []

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self, _url: str, *, data: dict[str, str], headers: dict[str, str]
        ) -> FakeResponse:
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"
            posted_tokens.append(data["token"])
            return FakeResponse()

    monkeypatch.setattr(
        "app.api.routes.youtube.httpx.AsyncClient", FakeAsyncClient
    )
    response = client.delete(
        f"{settings.API_V1_STR}/youtube/connection",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json() == {
        "disconnected": True,
        "revocation_status": "revoked",
    }
    assert posted_tokens == ["plain-refresh-token"]
    db.expire_all()
    assert get_connection(db, owner.id) is None


def test_youtube_session_uses_selected_active_broadcast(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(
        settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    owner = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).one()
    credentials = Credentials(
        token="youtube-session-access",
        refresh_token="youtube-session-refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.youtube_scopes,
    )
    save_connection(db, owner.id, credentials, "channel-2", "Session Channel")
    character_response = client.post(
        f"{settings.API_V1_STR}/characters/",
        headers=normal_user_token_headers,
        json={"name": "Kira", "persona_description": "Bạn thân"},
    )
    assert character_response.status_code == 200

    async def fake_usable(*_args: object) -> Credentials:
        return credentials

    async def fake_resolve(*_args: object) -> ActiveBroadcast:
        return ActiveBroadcast(
            id="abcdefghijk",
            title="Selected Live",
            live_chat_id="live-chat-selected",
            actual_start_time="2026-10-12T07:00:00Z",
            life_cycle_status="live",
        )

    started_ingest: list[str] = []
    monkeypatch.setattr(
        "app.api.routes.live_sessions.usable_credentials", fake_usable
    )
    monkeypatch.setattr(
        "app.api.routes.live_sessions.build_youtube", lambda _credentials: object()
    )
    monkeypatch.setattr(
        "app.api.routes.live_sessions.resolve_live_video", fake_resolve
    )
    monkeypatch.setattr(
        "app.api.routes.live_sessions.youtube_ingest_manager.start",
        lambda session_id: started_ingest.append(str(session_id)),
    )

    response = client.post(
        f"{settings.API_V1_STR}/sessions/",
        headers=normal_user_token_headers,
        json={
            "character_id": character_response.json()["id"],
            "mode": "youtube",
            "youtube_broadcast_id": "abcdefghijk",
        },
    )
    assert response.status_code == 200
    session = response.json()
    assert session["mode"] == "youtube"
    assert session["youtube_live_chat_id"] == "live-chat-selected"
    assert session["youtube_ingest_status"] == "ready"

    start = client.post(
        f"{settings.API_V1_STR}/sessions/{session['id']}/control",
        headers=normal_user_token_headers,
        json={"command": "start"},
    )
    assert start.status_code == 200
    assert started_ingest == [session["id"]]
    stop = client.post(
        f"{settings.API_V1_STR}/sessions/{session['id']}/control",
        headers=normal_user_token_headers,
        json={"command": "stop"},
    )
    assert stop.status_code == 200


def test_manual_resolve_and_rebind_preserve_active_voice_and_overlay(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    owner = db.exec(select(User).where(User.email == settings.EMAIL_TEST_USER)).one()
    credentials = Credentials(token="test-token", scopes=settings.youtube_scopes)
    save_connection(db, owner.id, credentials, "channel-verified", "Verified Channel")
    character = client.post(
        f"{settings.API_V1_STR}/characters/",
        headers=normal_user_token_headers,
        json={"name": "Kira", "persona_description": "Bạn thân"},
    ).json()

    async def fake_usable(*_args: object) -> Credentials:
        return credentials

    async def fake_resolve(
        _youtube: object, video_url: str, channel_id: str | None
    ) -> ActiveBroadcast:
        assert channel_id == "channel-verified"
        video_id = video_url.rsplit("/", 1)[-1]
        if video_id == "wrongchannel":
            from app.integrations.youtube.provider import YouTubeProviderError

            raise YouTubeProviderError("broadcast_channel_mismatch")
        return ActiveBroadcast(
            id=video_id,
            title="Verified Live",
            live_chat_id=f"chat-{video_id}",
            actual_start_time=None,
            life_cycle_status="live",
        )

    monkeypatch.setattr("app.api.routes.youtube.usable_credentials", fake_usable)
    monkeypatch.setattr("app.api.routes.youtube.build_youtube", lambda _: object())
    monkeypatch.setattr("app.api.routes.youtube.resolve_live_video", fake_resolve)
    monkeypatch.setattr("app.api.routes.live_sessions.usable_credentials", fake_usable)
    monkeypatch.setattr("app.api.routes.live_sessions.build_youtube", lambda _: object())
    monkeypatch.setattr(
        "app.api.routes.live_sessions.resolve_live_video", fake_resolve
    )
    started: list[str] = []
    stopped: list[str] = []

    async def fake_stop(session_id: object) -> None:
        stopped.append(str(session_id))

    monkeypatch.setattr(
        "app.api.routes.live_sessions.youtube_ingest_manager.start",
        lambda session_id: started.append(str(session_id)),
    )
    monkeypatch.setattr(
        "app.api.routes.live_sessions.youtube_ingest_manager.stop", fake_stop
    )

    resolved = client.post(
        f"{settings.API_V1_STR}/youtube/broadcasts/resolve",
        headers=normal_user_token_headers,
        json={"video_url": "https://youtube.com/live/abcdefghijk"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["live_chat_id"] == "chat-abcdefghijk"
    denied = client.post(
        f"{settings.API_V1_STR}/youtube/broadcasts/resolve",
        headers=normal_user_token_headers,
        json={"video_url": "wrongchannel"},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "broadcast_channel_mismatch"
    oversized = client.post(
        f"{settings.API_V1_STR}/youtube/broadcasts/resolve",
        headers=normal_user_token_headers,
        json={"video_url": "x" * 513},
    )
    assert oversized.status_code == 422

    created = client.post(
        f"{settings.API_V1_STR}/sessions/",
        headers=normal_user_token_headers,
        json={
            "character_id": character["id"],
            "mode": "youtube",
            "youtube_broadcast_id": "abcdefghijk",
        },
    ).json()
    session_id = created["id"]
    assert client.post(
        f"{settings.API_V1_STR}/sessions/{session_id}/control",
        headers=normal_user_token_headers,
        json={"command": "start"},
    ).status_code == 200
    from app.models import LiveSession

    live_session = db.get(LiveSession, created["id"])
    assert live_session is not None
    live_session.youtube_next_page_token = "old-page"
    db.add(live_session)
    db.commit()
    epoch = live_session.session_epoch
    overlay_hash = live_session.overlay_key_hash
    changed = client.post(
        f"{settings.API_V1_STR}/sessions/{session_id}/youtube/bind",
        headers=normal_user_token_headers,
        json={"video_url": "https://youtube.com/live/lmnopqrstuv"},
    )
    assert changed.status_code == 200
    assert changed.json()["youtube_broadcast_id"] == "lmnopqrstuv"
    assert changed.json()["youtube_live_chat_id"] == "chat-lmnopqrstuv"
    db.refresh(live_session)
    assert live_session.youtube_next_page_token is None
    assert live_session.session_epoch == epoch
    assert live_session.overlay_key_hash == overlay_hash
    assert live_session.status == "active"
    assert stopped == [session_id]
    assert started == [session_id, session_id]
    rejected = client.post(
        f"{settings.API_V1_STR}/sessions/{session_id}/youtube/bind",
        headers=normal_user_token_headers,
        json={"video_url": "wrongchannel"},
    )
    assert rejected.status_code == 409
    db.refresh(live_session)
    assert live_session.youtube_broadcast_id == "lmnopqrstuv"
    assert stopped == [session_id]
    client.post(
        f"{settings.API_V1_STR}/sessions/{session_id}/control",
        headers=normal_user_token_headers,
        json={"command": "stop"},
    )
    after_stop = client.post(
        f"{settings.API_V1_STR}/sessions/{session_id}/youtube/bind",
        headers=normal_user_token_headers,
        json={"video_url": "abcdefghijk"},
    )
    assert after_stop.status_code == 409
