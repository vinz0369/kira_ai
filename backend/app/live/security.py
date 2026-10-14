from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass


def new_overlay_key() -> str:
    return secrets.token_urlsafe(32)


def hash_overlay_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def overlay_key_matches(key: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    return secrets.compare_digest(hash_overlay_key(key), expected_hash)


@dataclass(frozen=True, slots=True)
class WsTicket:
    session_id: uuid.UUID
    user_id: uuid.UUID
    expires_at: float


class TicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, WsTicket] = {}

    def issue(
        self, session_id: uuid.UUID, user_id: uuid.UUID, ttl_seconds: int = 30
    ) -> str:
        token = secrets.token_urlsafe(24)
        self._tickets[token] = WsTicket(
            session_id, user_id, time.monotonic() + ttl_seconds
        )
        return token

    def consume(self, token: str, session_id: uuid.UUID) -> WsTicket | None:
        ticket = self._tickets.pop(token, None)
        if (
            not ticket
            or ticket.session_id != session_id
            or ticket.expires_at < time.monotonic()
        ):
            return None
        return ticket


ticket_store = TicketStore()
