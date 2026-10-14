from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import Session, select

from app.integrations.youtube.ingest import YouTubeIngestManager
from app.integrations.youtube.provider import (
    StreamUnavailableError,
    YouTubeBatch,
    YouTubeProviderError,
)
from app.live.hub import live_hub
from app.models import Character, LiveSession, PaidEvent, User, YouTubeEventReceipt


def paid_item(provider_id: str, event_type: str = "superChatEvent") -> dict[str, Any]:
    details_key = (
        "superChatDetails"
        if event_type == "superChatEvent"
        else "superStickerDetails"
    )
    details: dict[str, Any] = {
        "amountMicros": "5000000",
        "currency": "USD",
        "amountDisplayString": "$5.00",
    }
    if event_type == "superChatEvent":
        details["userComment"] = "Kira cảm ơn nhé"
    else:
        details["superStickerMetadata"] = {"altText": "Fox waving"}
    return {
        "id": provider_id,
        "snippet": {
            "type": event_type,
            "publishedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            details_key: details,
        },
        "authorDetails": {"channelId": "viewer", "displayName": "Minh"},
    }


@pytest.mark.anyio
async def test_history_is_bootstrapped_then_new_paid_event_is_delivered_once(
    db: Session,
) -> None:
    owner = db.exec(select(User)).first()
    assert owner is not None
    character = Character(owner_id=owner.id, name="Kira")
    db.add(character)
    db.commit()
    db.refresh(character)
    live_session = LiveSession(
        owner_id=owner.id,
        character_id=character.id,
        mode="youtube",
        status="active",
        ai_muted=False,
        youtube_broadcast_id="broadcast-ingest-test",
        youtube_live_chat_id="chat-ingest-test",
        youtube_ingest_status="connecting",
    )
    db.add(live_session)
    db.commit()
    db.refresh(live_session)

    manager = YouTubeIngestManager()
    await manager.process_batch(
        live_session.id,
        YouTubeBatch(
            items=[paid_item("history-paid")],
            next_page_token="checkpoint-1",
        ),
    )
    runtime = live_hub.runtime(live_session.id)
    assert "history-paid" not in runtime.director.state.seen_provider_ids

    await manager.process_batch(
        live_session.id,
        YouTubeBatch(
            items=[
                paid_item("history-paid"),
                paid_item("new-sticker", "superStickerEvent"),
            ],
            next_page_token="checkpoint-2",
        ),
    )
    await manager.process_batch(
        live_session.id,
        YouTubeBatch(
            items=[paid_item("new-sticker", "superStickerEvent")],
            next_page_token="checkpoint-3",
        ),
    )

    receipts = db.exec(
        select(YouTubeEventReceipt).where(
            YouTubeEventReceipt.live_session_id == live_session.id
        )
    ).all()
    assert len(receipts) == 2
    assert sum(receipt.is_historical for receipt in receipts) == 1
    paid = db.exec(
        select(PaidEvent).where(PaidEvent.live_session_id == live_session.id)
    ).all()
    assert len(paid) == 2
    assert next(item for item in paid if item.provider_event_id == "history-paid").ack_status == "skipped"
    assert next(item for item in paid if item.provider_event_id == "new-sticker").ack_status == "acknowledged"
    assert runtime.director.state.seen_provider_ids == {"new-sticker"}
    db.refresh(live_session)
    assert live_session.youtube_next_page_token == "checkpoint-3"

    live_session.status = "stopped"
    db.add(live_session)
    db.commit()


@pytest.mark.anyio
async def test_quota_error_stops_retry_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = YouTubeIngestManager()
    statuses: list[tuple[str, str | None]] = []

    async def fail_provider(
        _session_id: uuid.UUID,
    ) -> tuple[Any, str, str | None]:
        raise YouTubeProviderError("quota_exceeded")

    async def capture_status(
        _session_id: uuid.UUID, status: str, error: str | None
    ) -> None:
        statuses.append((status, error))

    monkeypatch.setattr(manager, "_provider", fail_provider)
    monkeypatch.setattr(manager, "_set_status", capture_status)
    await manager._run(uuid.uuid4())
    assert statuses == [("quota_exceeded", "quota_exceeded")]


class FallbackProvider:
    async def stream_batches(
        self, _chat_id: str, _page_token: str | None
    ) -> AsyncIterator[YouTubeBatch]:
        if False:
            yield YouTubeBatch([], None)
        raise StreamUnavailableError()

    async def poll_batch(
        self, _chat_id: str, _page_token: str | None
    ) -> YouTubeBatch:
        return YouTubeBatch(
            items=[],
            next_page_token="poll-checkpoint",
            offline_at="2026-10-12T08:00:00Z",
            transport="list",
        )


@pytest.mark.anyio
async def test_stream_unavailable_falls_back_to_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = YouTubeIngestManager()
    provider = FallbackProvider()
    processed: list[str] = []
    statuses: list[tuple[str, str | None]] = []

    async def get_provider(
        _session_id: uuid.UUID,
    ) -> tuple[Any, str, str | None]:
        return provider, "chat-id", None

    async def process(_session_id: uuid.UUID, batch: YouTubeBatch) -> None:
        processed.append(batch.transport)

    async def capture_status(
        _session_id: uuid.UUID, status: str, error: str | None
    ) -> None:
        statuses.append((status, error))

    monkeypatch.setattr(manager, "_provider", get_provider)
    monkeypatch.setattr(manager, "process_batch", process)
    monkeypatch.setattr(manager, "_set_status", capture_status)
    await manager._run(uuid.uuid4())
    assert processed == ["list"]
    assert ("degraded", "stream_unavailable_using_polling") in statuses
    assert statuses[-1] == ("broadcast_ended", "broadcast_ended")
