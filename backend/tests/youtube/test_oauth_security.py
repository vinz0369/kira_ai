import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from sqlmodel import Session, select

from app.core.config import settings
from app.integrations.youtube.oauth import (
    OAuthStateError,
    begin_authorization,
    consume_attempt,
    credentials_from_connection,
    save_connection,
    usable_credentials,
)
from app.integrations.youtube.security import TokenCipher, hash_oauth_state
from app.models import OAuthAttempt, User


def configure_google(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", key)
    return key


def test_token_cipher_never_stores_plaintext() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("refresh-token-secret")
    assert "refresh-token-secret" not in encrypted
    assert cipher.decrypt(encrypted) == "refresh-token-secret"


def test_authorization_uses_state_pkce_and_one_time_consumption(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = configure_google(monkeypatch)
    owner = db.exec(select(User)).first()
    assert owner is not None
    url = begin_authorization(db, owner.id)
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert "test-client-secret" not in url

    state = query["state"][0]
    attempt = db.exec(
        select(OAuthAttempt).where(
            OAuthAttempt.state_hash == hash_oauth_state(state)
        )
    ).one()
    verifier = TokenCipher(key).decrypt(attempt.encrypted_code_verifier)
    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == [expected_challenge]

    consumed, returned_verifier = consume_attempt(db, state)
    assert consumed.id == attempt.id
    assert returned_verifier == verifier
    with pytest.raises(OAuthStateError):
        consume_attempt(db, state)
    with pytest.raises(OAuthStateError):
        consume_attempt(db, "wrong-state-value-that-is-long-enough")


@pytest.mark.anyio
async def test_refresh_stores_aware_utc_and_returns_google_naive_expiry(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_google(monkeypatch)
    owner = db.exec(select(User)).first()
    assert owner is not None
    expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    credentials = Credentials(
        token="expired-synthetic-token",
        refresh_token="synthetic-refresh-token",
        scopes=settings.youtube_scopes,
        expiry=expired,
    )
    connection = save_connection(db, owner.id, credentials, "channel-1", "Channel")

    def fake_refresh(self: Credentials, _request: object) -> None:
        self.token = "refreshed-synthetic-token"
        self.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    refreshed = await usable_credentials(db, connection)
    assert refreshed.valid
    assert refreshed.expiry is not None and refreshed.expiry.tzinfo is None
    db.refresh(connection)
    assert connection.expires_at is not None
    assert connection.expires_at.tzinfo is not None
    assert credentials_from_connection(connection).valid
    assert "refreshed-synthetic-token" not in connection.encrypted_access_token
    db.delete(connection)
    db.commit()
