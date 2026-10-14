from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.integrations.youtube.mapper import MappedYouTubeEvent, map_live_chat_item
from app.integrations.youtube.oauth import get_connection, usable_credentials
from app.integrations.youtube.provider import (
    OfficialYouTubeProvider,
    StreamUnavailableError,
    YouTubeBatch,
    YouTubeProviderError,
    build_youtube,
)
from app.live.hub import live_hub
from app.models import Character, LiveSession, PaidEvent, YouTubeEventReceipt

TERMINAL_PROVIDER_CODES = {
    "auth_expired": "auth_expired",
    "insufficient_scope": "insufficient_scope",
    "quota_exceeded": "quota_exceeded",
    "quota_or_rate_limited": "quota_exceeded",
    "chat_disabled": "chat_disabled",
    "broadcast_ended": "broadcast_ended",
    "chat_disabled_or_ended": "chat_disabled_or_ended",
    "chat_not_found": "chat_not_found",
}


class YouTubeIngestManager:
    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    def running(self, session_id: uuid.UUID) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    def start(self, session_id: uuid.UUID) -> None:
        if self.running(session_id):
            return
        task = asyncio.create_task(
            self._run(session_id), name=f"youtube-ingest-{session_id}"
        )
        self._tasks[session_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(session_id, None))

    async def stop(self, session_id: uuid.UUID) -> None:
        task = self._tasks.pop(session_id, None)
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def stop_all(self) -> None:
        await asyncio.gather(
            *(self.stop(session_id) for session_id in list(self._tasks))
        )

    def restore_active(self) -> None:
        if not settings.youtube_configured:
            return
        with Session(engine) as db:
            active = db.exec(
                select(LiveSession).where(
                    LiveSession.mode == "youtube",
                    LiveSession.status == "active",
                )
            ).all()
            for live_session in active:
                self.start(live_session.id)

    async def _run(self, session_id: uuid.UUID) -> None:
        transport = settings.YOUTUBE_INGEST_TRANSPORT
        retry_count = 0
        while True:
            try:
                provider, live_chat_id, page_token = await self._provider(session_id)
                await self._set_status(session_id, "connecting", None)
                if transport == "stream":
                    async for batch in provider.stream_batches(
                        live_chat_id, page_token
                    ):
                        await self.process_batch(session_id, batch)
                        retry_count = 0
                        if batch.offline_at:
                            await self._set_status(
                                session_id, "broadcast_ended", "broadcast_ended"
                            )
                            return
                    raise YouTubeProviderError(
                        "stream_disconnected", retryable=True
                    )
                while True:
                    batch = await provider.poll_batch(live_chat_id, page_token)
                    await self.process_batch(session_id, batch)
                    page_token = batch.next_page_token
                    retry_count = 0
                    if batch.offline_at:
                        await self._set_status(
                            session_id, "broadcast_ended", "broadcast_ended"
                        )
                        return
                    await asyncio.sleep(batch.polling_interval_ms / 1000)
            except StreamUnavailableError:
                transport = "poll"
                await self._set_status(
                    session_id, "degraded", "stream_unavailable_using_polling"
                )
            except PermissionError:
                await self._set_status(session_id, "auth_expired", "reauthorize")
                return
            except YouTubeProviderError as exc:
                terminal = TERMINAL_PROVIDER_CODES.get(exc.code)
                if terminal:
                    await self._set_status(session_id, terminal, exc.code)
                    return
                if not exc.retryable:
                    await self._set_status(session_id, "down", exc.code)
                    return
                retry_count += 1
                await self._set_status(session_id, "reconnecting", exc.code)
                delay = min(
                    settings.YOUTUBE_RECONNECT_MAX_SECONDS,
                    2 ** min(retry_count, 5),
                )
                await asyncio.sleep(delay + random.random())
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._set_status(session_id, "down", "unexpected_error")
                return

    async def _provider(
        self, session_id: uuid.UUID
    ) -> tuple[OfficialYouTubeProvider, str, str | None]:
        with Session(engine) as db:
            live_session = db.get(LiveSession, session_id)
            if (
                not live_session
                or live_session.mode != "youtube"
                or live_session.status != "active"
                or not live_session.youtube_live_chat_id
            ):
                raise YouTubeProviderError("session_not_active")
            connection = get_connection(db, live_session.owner_id)
            if not connection:
                raise PermissionError("YouTube is not connected")
            credentials = await usable_credentials(db, connection)
            youtube = build_youtube(credentials)
            return (
                OfficialYouTubeProvider(youtube, credentials.token or ""),
                live_session.youtube_live_chat_id,
                live_session.youtube_next_page_token,
            )

    async def process_batch(
        self, session_id: uuid.UUID, batch: YouTubeBatch
    ) -> None:
        with Session(engine) as db:
            live_session = db.get(LiveSession, session_id)
            if not live_session:
                return
            # A persisted page token is the bootstrap commit marker. If the process
            # dies after receipts are written but before that token is saved, the
            # next response must still be treated as history rather than replayed.
            bootstrap_history = live_session.youtube_next_page_token is None
            character = db.get(Character, live_session.character_id)
            character_name = character.name if character else "Kira"

        for item in batch.items:
            mapped = map_live_chat_item(item, session_id)
            if mapped:
                await self._record_and_dispatch(
                    session_id,
                    mapped,
                    character_name,
                    is_historical=bootstrap_history,
                )

        with Session(engine) as db:
            live_session = db.get(LiveSession, session_id)
            if not live_session:
                return
            live_session.youtube_next_page_token = batch.next_page_token
            live_session.youtube_ingest_status = "connected"
            live_session.youtube_last_error = None
            live_session.youtube_connected_at = datetime.now(UTC)
            db.add(live_session)
            db.commit()
        await live_hub.provider_health(session_id, "ok", batch.transport)

    async def _record_and_dispatch(
        self,
        session_id: uuid.UUID,
        mapped: MappedYouTubeEvent,
        character_name: str,
        *,
        is_historical: bool,
    ) -> None:
        paid_id: uuid.UUID | None = None
        with Session(engine) as db:
            existing = db.exec(
                select(YouTubeEventReceipt).where(
                    YouTubeEventReceipt.live_session_id == session_id,
                    YouTubeEventReceipt.provider_message_id
                    == mapped.provider_message_id,
                )
            ).first()
            if existing:
                return
            receipt = YouTubeEventReceipt(
                live_session_id=session_id,
                provider_message_id=mapped.provider_message_id,
                event_type=mapped.envelope.type,
                published_at=mapped.published_at,
                is_historical=is_historical,
            )
            db.add(receipt)
            if mapped.is_paid:
                payload = mapped.envelope.payload
                paid = PaidEvent(
                    live_session_id=session_id,
                    provider_event_id=mapped.provider_message_id,
                    event_type=mapped.envelope.type,
                    author_display_name=str(
                        payload.get("author_name") or "Người xem"
                    )[:255],
                    amount_micros=int(payload.get("amount_micros", 0)),
                    currency=str(payload.get("currency") or "USD")[:3],
                    ack_status="skipped" if is_historical else "pending",
                )
                db.add(paid)
                paid_id = paid.id
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return

        if is_historical:
            return
        await live_hub.process(session_id, mapped.envelope, character_name)
        if paid_id:
            with Session(engine) as db:
                stored_paid = db.get(PaidEvent, paid_id)
                if stored_paid:
                    stored_paid.ack_status = "acknowledged"
                    db.add(stored_paid)
                    db.commit()

    async def _set_status(
        self, session_id: uuid.UUID, status: str, error: str | None
    ) -> None:
        with Session(engine) as db:
            live_session = db.get(LiveSession, session_id)
            if live_session:
                live_session.youtube_ingest_status = status
                live_session.youtube_last_error = error
                db.add(live_session)
                db.commit()
        health = "ok" if status == "connected" else (
            "degraded" if status in {"connecting", "reconnecting", "degraded"} else "down"
        )
        await live_hub.provider_health(session_id, health, error or status)


youtube_ingest_manager = YouTubeIngestManager()
