from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.live.contracts import EventEnvelope
from app.live.hub import live_hub
from app.live.security import overlay_key_matches, ticket_store
from app.models import Character, LiveSession
from app.voice.protocol import MIC_DIRECTION, AudioProtocolError, decode_audio_frame

router = APIRouter(tags=["live-websockets"])


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    return origin is None or origin.rstrip("/") in settings.ws_allowed_origins


@router.websocket("/ws/v1/dashboard/{session_id}")
async def dashboard_socket(
    websocket: WebSocket, session_id: uuid.UUID, ticket: str
) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    issued = ticket_store.consume(ticket, session_id)
    if not issued:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    with Session(engine) as db:
        live_session = db.get(LiveSession, session_id)
        if not live_session or live_session.owner_id != issued.user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        character = db.get(Character, live_session.character_id)
        live_hub.runtime(
            session_id,
            live_session.status,
            live_session.ai_muted,
            character.name if character else "Kira",
            live_session.session_epoch,
            live_session.voice_mode,
            character.model_dump() if character else None,
        )
    try:
        await live_hub.connect_dashboard(session_id, websocket)
        if live_session.voice_mode == "real":
            await live_hub.connect_voice_input(session_id)
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            raw_bytes = message.get("bytes")
            if raw_bytes is not None:
                if live_session.voice_mode != "real":
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break
                try:
                    frame = decode_audio_frame(
                        raw_bytes,
                        expected_direction=MIC_DIRECTION,
                        max_pcm_bytes=settings.VOICE_MAX_AUDIO_FRAME_BYTES,
                    )
                except AudioProtocolError:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break
                await live_hub.voice_audio(session_id, frame)
                continue
            raw_text = message.get("text")
            try:
                payload = json.loads(raw_text or "{}")
            except json.JSONDecodeError:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            if payload.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if live_session.voice_mode != "real":
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            try:
                event = EventEnvelope.model_validate(payload)
                if event.session_id != session_id:
                    raise ValueError("session mismatch")
                turn_id = uuid.UUID(str(event.payload.get("turn_id")))
            except (ValueError, TypeError):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            if event.type == "streamer.speech.started":
                await live_hub.voice_begin(session_id, turn_id)
            elif event.type == "streamer.speech.ended":
                await live_hub.voice_end(session_id, turn_id)
            else:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
    except WebSocketDisconnect:
        pass
    finally:
        if live_session.voice_mode == "real":
            await live_hub.disconnect_voice_input(session_id)
        live_hub.disconnect_dashboard(session_id, websocket)


@router.websocket("/ws/v1/overlay/{session_id}")
async def overlay_socket(websocket: WebSocket, session_id: uuid.UUID, key: str) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    with Session(engine) as db:
        live_session = db.get(LiveSession, session_id)
        if (
            not live_session
            or live_session.status == "stopped"
            or not overlay_key_matches(key, live_session.overlay_key_hash)
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        character = db.get(Character, live_session.character_id)
        live_hub.runtime(
            session_id,
            live_session.status,
            live_session.ai_muted,
            character.name if character else "Kira",
            live_session.session_epoch,
            live_session.voice_mode,
            character.model_dump() if character else None,
        )
    try:
        await live_hub.connect_overlay(session_id, websocket)
        while True:
            raw = await websocket.receive_json()
            if raw.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            try:
                event = EventEnvelope.model_validate(raw)
            except ValueError:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            if event.type not in {
                "speech.playback.started",
                "speech.playback.completed",
                "speech.playback.cancelled",
            }:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            await live_hub.playback_ack(session_id, event)
    except WebSocketDisconnect:
        await live_hub.disconnect_overlay(session_id, websocket)


@router.get("/api/v1/health", tags=["utils"])
async def live_health() -> dict[str, str | bool]:
    return {"status": "ok", "mock_mode": settings.MOCK_MODE}
