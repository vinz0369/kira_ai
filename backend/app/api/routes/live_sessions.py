from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.integrations.youtube.ingest import youtube_ingest_manager
from app.integrations.youtube.oauth import get_connection, usable_credentials
from app.integrations.youtube.provider import (
    YouTubeProviderError,
    build_youtube,
    resolve_live_video,
)
from app.live.contracts import EventEnvelope
from app.live.hub import live_hub
from app.live.security import hash_overlay_key, new_overlay_key, ticket_store
from app.models import Character, LiveSession, PaidEvent
from app.voice.llm import normalize_real_llm_provider, validate_llm_selection
from app.voice.tts import normalize_real_tts_provider, validate_tts_selection

router = APIRouter(prefix="/sessions", tags=["live-sessions"])


class LiveSessionCreate(SQLModel):
    character_id: uuid.UUID
    mode: Literal["mock", "youtube"] = "mock"
    voice_mode: Literal["mock", "real"] = "mock"
    youtube_broadcast_id: str | None = None


class LiveSessionPublic(SQLModel):
    id: uuid.UUID
    character_id: uuid.UUID
    mode: str
    voice_mode: str
    status: str
    ai_muted: bool
    mic_connected: bool
    session_epoch: int
    created_at: datetime
    updated_at: datetime
    overlay_url: str | None = None
    youtube_broadcast_id: str | None = None
    youtube_live_chat_id: str | None = None
    youtube_ingest_status: str
    youtube_last_error: str | None = None
    real_voice_configured: bool


class ControlRequest(SQLModel):
    command: Literal["start", "pause", "resume", "mute", "unmute", "stop"]


class AvatarMotionRequest(SQLModel):
    motion: Literal["idle", "greet", "heart", "dance"]
    duration_seconds: int = Field(default=0, ge=0, le=300)


@router.post("/{session_id}/avatar-motion")
async def set_avatar_motion(
    session_id: uuid.UUID,
    request: AvatarMotionRequest,
    db: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str | int]:
    live_session = _owned_session(db, current_user, session_id)
    if live_session.status != "active":
        raise HTTPException(status_code=409, detail="Session must be active")
    if request.motion == "dance" and request.duration_seconds < 121:
        raise HTTPException(
            status_code=422, detail="Dance duration must be at least 121 seconds"
        )
    await live_hub.avatar_motion(
        session_id, request.motion, request.duration_seconds
    )
    return {
        "motion": request.motion,
        "duration_seconds": request.duration_seconds,
    }


class SimulateRequest(SQLModel):
    type: Literal[
        "streamer.speech.started",
        "streamer.speech.ended",
        "streamer.transcript.final",
        "youtube.chat.message",
        "youtube.superchat",
        "youtube.supersticker",
    ]
    payload: dict[str, Any]
    ts: datetime | None = None


class WsTicketPublic(SQLModel):
    ticket: str
    expires_in_seconds: int = 30


class UsagePublic(SQLModel):
    stt_seconds: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    tts_characters: int = 0
    estimated_usd: float | None = None
    cost_estimate_configured: bool = False
    observed_session_seconds: int = 0
    projected_3h_usd: float | None = None
    projection_basis: Literal["actual_usage_run_rate", "unavailable"] = "unavailable"
    usage_measurement_scope: Literal["MOCK_SIMULATED", "REAL_PROVIDER_OBSERVED"]
    usage_basis: dict[str, str]
    provider_errors: int = 0
    stt_reconnects: int = 0
    dropped_mic_frames: int = 0
    overlay_reconnect_count: int = 0
    telemetry: dict[str, Any]


def project_three_hour_cost(
    *, estimated_usd: float | None, observed_seconds: int, real_voice: bool
) -> tuple[float | None, Literal["actual_usage_run_rate", "unavailable"]]:
    if not real_voice or estimated_usd is None or observed_seconds < 60:
        return None, "unavailable"
    return round(estimated_usd * 10_800 / observed_seconds, 4), "actual_usage_run_rate"


def _owned_session(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> LiveSession:
    live_session = db.get(LiveSession, session_id)
    if not live_session:
        raise HTTPException(status_code=404, detail="Live session not found")
    if live_session.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return live_session


def _real_voice_ready(character: Character | None) -> bool:
    if not character or not settings.DEEPGRAM_API_KEY:
        return False
    llm_provider = normalize_real_llm_provider(character.llm_provider)
    tts_provider = normalize_real_tts_provider(character.voice_provider)
    return settings.llm_provider_configured(
        llm_provider
    ) and settings.tts_provider_configured(tts_provider)


def _public(
    live_session: LiveSession,
    overlay_key: str | None = None,
    character: Character | None = None,
) -> LiveSessionPublic:
    overlay_url = None
    if overlay_key:
        base = settings.FRONTEND_HOST.rstrip("/")
        overlay_url = f"{base}/overlay/{live_session.id}?key={overlay_key}"
    return LiveSessionPublic(
        **live_session.model_dump(),
        overlay_url=overlay_url,
        real_voice_configured=_real_voice_ready(character),
    )


@router.post("/", response_model=LiveSessionPublic)
async def create_live_session(
    *, db: SessionDep, current_user: CurrentUser, session_in: LiveSessionCreate
) -> Any:
    if session_in.mode == "mock" and not settings.MOCK_MODE:
        raise HTTPException(status_code=403, detail="Mock sessions are disabled")
    character = db.get(Character, session_in.character_id)
    if not character or character.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Character not found")
    llm_provider = normalize_real_llm_provider(character.llm_provider)
    tts_provider = normalize_real_tts_provider(character.voice_provider)
    if session_in.voice_mode == "real":
        try:
            if character.llm_provider != "fake":
                validate_llm_selection(llm_provider, character.llm_model)
            if character.voice_provider != "fake":
                validate_tts_selection(tts_provider, character.voice_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if not settings.DEEPGRAM_API_KEY:
            raise HTTPException(
                status_code=409,
                detail="Deepgram is required for Voice Real",
            )
        if not settings.llm_provider_configured(llm_provider):
            raise HTTPException(
                status_code=409,
                detail=f"LLM provider {llm_provider} is not configured",
            )
        if not settings.tts_provider_configured(tts_provider):
            raise HTTPException(
                status_code=409,
                detail=f"TTS provider {tts_provider} is not configured",
            )
    broadcast_id: str | None = None
    live_chat_id: str | None = None
    ingest_status = "disabled"
    if session_in.mode == "youtube":
        if not session_in.youtube_broadcast_id:
            raise HTTPException(
                status_code=422, detail="youtube_broadcast_id is required"
            )
        connection = get_connection(db, current_user.id)
        if not connection:
            raise HTTPException(status_code=409, detail="Connect YouTube first")
        try:
            credentials = await usable_credentials(db, connection)
            broadcast = await resolve_live_video(
                build_youtube(credentials),
                session_in.youtube_broadcast_id,
                connection.provider_channel_id,
            )
        except PermissionError:
            raise HTTPException(status_code=401, detail="Reconnect YouTube")
        except YouTubeProviderError as exc:
            raise HTTPException(status_code=409, detail=exc.code)
        broadcast_id = broadcast.id
        live_chat_id = broadcast.live_chat_id
        ingest_status = "ready"
    overlay_key = new_overlay_key()
    live_session = LiveSession(
        owner_id=current_user.id,
        character_id=character.id,
        mode=session_in.mode,
        voice_mode=session_in.voice_mode,
        status="draft",
        ai_muted=True,
        overlay_key_hash=hash_overlay_key(overlay_key),
        youtube_broadcast_id=broadcast_id,
        youtube_live_chat_id=live_chat_id,
        youtube_ingest_status=ingest_status,
    )
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    live_hub.runtime(
        live_session.id,
        live_session.status,
        live_session.ai_muted,
        character.name,
        live_session.session_epoch,
        live_session.voice_mode,
        character.model_dump(),
    )
    return _public(live_session, overlay_key, character)


@router.get("/", response_model=list[LiveSessionPublic])
def list_live_sessions(db: SessionDep, current_user: CurrentUser) -> Any:
    sessions = db.exec(
        select(LiveSession)
        .where(LiveSession.owner_id == current_user.id)
        .order_by(col(LiveSession.created_at).desc())
        .limit(20)
    ).all()
    return [
        _public(session, character=db.get(Character, session.character_id))
        for session in sessions
    ]


@router.get("/current", response_model=LiveSessionPublic | None)
def read_current_live_session(db: SessionDep, current_user: CurrentUser) -> Any:
    live_session = db.exec(
        select(LiveSession)
        .where(
            LiveSession.owner_id == current_user.id,
            col(LiveSession.status).in_(["active", "paused"]),
        )
        .order_by(col(LiveSession.updated_at).desc())
    ).first()
    if live_session is None:
        return None
    return _public(
        live_session, character=db.get(Character, live_session.character_id)
    )


@router.get("/{session_id}", response_model=LiveSessionPublic)
def read_live_session(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> Any:
    live_session = _owned_session(db, current_user, session_id)
    return _public(live_session, character=db.get(Character, live_session.character_id))


@router.post("/{session_id}/control", response_model=LiveSessionPublic)
async def control_live_session(
    *,
    db: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    control: ControlRequest,
) -> Any:
    live_session = _owned_session(db, current_user, session_id)
    character = db.get(Character, live_session.character_id)
    live_hub.runtime(
        live_session.id,
        live_session.status,
        live_session.ai_muted,
        character.name if character else "Kira",
        live_session.session_epoch,
        live_session.voice_mode,
        character.model_dump() if character else None,
    )
    now = datetime.now(UTC)
    command = control.command
    if live_session.status == "stopped" and command != "stop":
        raise HTTPException(status_code=409, detail="Stopped session cannot restart")
    if command in {"start", "resume"}:
        other = db.exec(
            select(LiveSession).where(
                LiveSession.owner_id == current_user.id,
                LiveSession.id != live_session.id,
                col(LiveSession.status).in_(["active", "paused"]),
            )
        ).first()
        if other:
            raise HTTPException(
                status_code=409, detail="Another live session is active"
            )
        live_session.status = "active"
        live_session.ai_muted = False
        live_session.started_at = live_session.started_at or now
    elif command == "pause":
        live_session.status = "paused"
    elif command == "mute":
        live_session.ai_muted = True
        live_session.session_epoch += 1
    elif command == "unmute":
        live_session.ai_muted = False
    elif command == "stop":
        live_session.status = "stopped"
        live_session.ai_muted = True
        live_session.stopped_at = now
        live_session.overlay_key_hash = None
        live_session.session_epoch += 1
    live_session.updated_at = now
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    await live_hub.sync_control(
        live_session.id, command, live_session.status, live_session.ai_muted
    )
    if live_session.mode == "youtube":
        if command in {"start", "resume"}:
            youtube_ingest_manager.start(live_session.id)
        elif command in {"pause", "stop"}:
            await youtube_ingest_manager.stop(live_session.id)
    if command == "stop":
        await live_hub.close_overlays(live_session.id)
    return _public(live_session, character=character)


@router.post("/{session_id}/youtube/reconnect", response_model=LiveSessionPublic)
async def reconnect_youtube(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> LiveSessionPublic:
    live_session = _owned_session(db, current_user, session_id)
    if live_session.mode != "youtube":
        raise HTTPException(status_code=409, detail="This is not a YouTube session")
    if live_session.status != "active":
        raise HTTPException(status_code=409, detail="Session must be active")
    await youtube_ingest_manager.stop(live_session.id)
    live_session.youtube_ingest_status = "connecting"
    live_session.youtube_last_error = None
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    youtube_ingest_manager.start(live_session.id)
    character = db.get(Character, live_session.character_id)
    return _public(live_session, character=character)


class BindYouTubeRequest(SQLModel):
    video_url: str = Field(min_length=1, max_length=512)


@router.post("/{session_id}/youtube/bind", response_model=LiveSessionPublic)
async def bind_youtube_broadcast(
    session_id: uuid.UUID,
    request: BindYouTubeRequest,
    db: SessionDep,
    current_user: CurrentUser,
) -> LiveSessionPublic:
    live_session = _owned_session(db, current_user, session_id)
    if live_session.mode != "youtube" or live_session.status == "stopped":
        raise HTTPException(status_code=409, detail="Session cannot bind YouTube")
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
    if (
        live_session.youtube_broadcast_id == broadcast.id
        and live_session.youtube_live_chat_id == broadcast.live_chat_id
        and live_session.youtube_ingest_status == "connected"
    ):
        return _public(
            live_session, character=db.get(Character, live_session.character_id)
        )
    # Only the YouTube reader is replaced. Voice, OBS overlay and session epoch stay intact.
    await youtube_ingest_manager.stop(live_session.id)
    live_session.youtube_broadcast_id = broadcast.id
    live_session.youtube_live_chat_id = broadcast.live_chat_id
    live_session.youtube_next_page_token = None
    live_session.youtube_ingest_status = "connecting" if live_session.status == "active" else "ready"
    live_session.youtube_last_error = None
    live_session.youtube_connected_at = None
    live_session.updated_at = datetime.now(UTC)
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    if live_session.status == "active":
        youtube_ingest_manager.start(live_session.id)
    return _public(live_session, character=db.get(Character, live_session.character_id))


@router.post("/{session_id}/overlay-key/rotate", response_model=LiveSessionPublic)
def rotate_overlay_key(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> Any:
    live_session = _owned_session(db, current_user, session_id)
    if live_session.status == "stopped":
        raise HTTPException(status_code=409, detail="Session is stopped")
    key = new_overlay_key()
    live_session.overlay_key_hash = hash_overlay_key(key)
    live_session.updated_at = datetime.now(UTC)
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    character = db.get(Character, live_session.character_id)
    return _public(live_session, key, character)


@router.post("/{session_id}/ws-ticket", response_model=WsTicketPublic)
def create_ws_ticket(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> WsTicketPublic:
    live_session = _owned_session(db, current_user, session_id)
    return WsTicketPublic(ticket=ticket_store.issue(live_session.id, current_user.id))


@router.post("/{session_id}/simulate")
async def simulate_event(
    *,
    db: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    simulated: SimulateRequest,
) -> dict[str, Any]:
    if not settings.MOCK_MODE:
        raise HTTPException(status_code=404, detail="Mock simulator is disabled")
    live_session = _owned_session(db, current_user, session_id)
    if live_session.status != "active":
        raise HTTPException(status_code=409, detail="Session must be active")
    character = db.get(Character, live_session.character_id)
    if not character:
        raise HTTPException(status_code=409, detail="Character is unavailable")
    live_hub.runtime(
        live_session.id,
        live_session.status,
        live_session.ai_muted,
        character.name,
        live_session.session_epoch,
        live_session.voice_mode,
        character.model_dump(),
    )
    if simulated.type.startswith("youtube.super"):
        provider_id = str(simulated.payload.get("provider_message_id", ""))[:255]
        if not provider_id:
            raise HTTPException(
                status_code=422, detail="provider_message_id is required"
            )
        existing = db.exec(
            select(PaidEvent).where(
                PaidEvent.live_session_id == live_session.id,
                PaidEvent.provider_event_id == provider_id,
            )
        ).first()
        if not existing:
            paid = PaidEvent(
                live_session_id=live_session.id,
                provider_event_id=provider_id,
                event_type=simulated.type,
                author_display_name=str(
                    simulated.payload.get("author_name") or "Người xem"
                )[:255],
                amount_micros=max(0, int(simulated.payload.get("amount_micros", 0))),
                currency=str(simulated.payload.get("currency") or "VND")[:3].upper(),
            )
            db.add(paid)
            db.commit()
    event = EventEnvelope(
        session_id=live_session.id,
        type=simulated.type,
        ts=simulated.ts or datetime.now(UTC),
        source="simulator",
        payload=simulated.payload,
    )
    emitted = await live_hub.process(live_session.id, event, character.name)
    runtime = live_hub.runtime(live_session.id)
    return {
        "accepted": True,
        "events": [item.model_dump(mode="json") for item in emitted],
        "queue_depth": len(runtime.director.state.paid_queue),
    }


@router.get("/{session_id}/usage", response_model=UsagePublic)
def read_usage(
    db: SessionDep, current_user: CurrentUser, session_id: uuid.UUID
) -> UsagePublic:
    live_session = _owned_session(db, current_user, session_id)
    character = db.get(Character, live_session.character_id)
    llm_provider = normalize_real_llm_provider(
        character.llm_provider if character else "fake"
    )
    tts_provider = normalize_real_tts_provider(
        character.voice_provider if character else "fake"
    )
    runtime = live_hub.runtime(
        live_session.id,
        live_session.status,
        live_session.ai_muted,
        character.name if character else "Kira",
        live_session.session_epoch,
        live_session.voice_mode,
        character.model_dump() if character else None,
    )
    voice_input = runtime.voice_input
    active_voice = voice_input.state if voice_input else None
    stt_audio_ms = runtime.usage.stt_audio_ms + (
        active_voice.audio_ms if active_voice else 0.0
    )
    stt_reconnects = runtime.usage.stt_reconnects + (
        voice_input.reconnects if voice_input else 0
    )
    dropped_mic_frames = runtime.usage.dropped_mic_frames + (
        voice_input.dropped_frames if voice_input else 0
    )
    llm_input_rate, llm_output_rate = settings.llm_cost_rates(llm_provider)
    estimated_usd = runtime.usage.estimated_usd(
        stt_per_minute=settings.VOICE_STT_USD_PER_MINUTE,
        llm_input_per_million=llm_input_rate,
        llm_output_per_million=llm_output_rate,
        tts_per_million_chars=(
            settings.VOICE_TTS_USD_PER_MILLION_CHARACTERS
            if tts_provider == "google_chirp"
            else 0.0
        ),
    )
    end_time = live_session.stopped_at or datetime.now(UTC)
    observed_seconds = (
        max(
            0,
            round((end_time - live_session.started_at).total_seconds()),
        )
        if live_session.started_at
        else 0
    )
    projected_3h_usd, projection_basis = project_three_hour_cost(
        estimated_usd=estimated_usd,
        observed_seconds=observed_seconds,
        real_voice=live_session.voice_mode == "real",
    )
    return UsagePublic(
        stt_seconds=round(stt_audio_ms / 1000),
        llm_input_tokens=(
            runtime.usage.llm_input_tokens
            if live_session.voice_mode == "real"
            else runtime.llm_calls * 40
        ),
        llm_output_tokens=(
            runtime.usage.llm_output_tokens
            if live_session.voice_mode == "real"
            else runtime.llm_calls * 30
        ),
        tts_characters=runtime.tts_characters,
        estimated_usd=estimated_usd,
        cost_estimate_configured=settings.voice_cost_rates_configured_for(
            tts_provider, llm_provider
        ),
        observed_session_seconds=observed_seconds,
        projected_3h_usd=projected_3h_usd,
        projection_basis=projection_basis,
        usage_measurement_scope=(
            "REAL_PROVIDER_OBSERVED"
            if live_session.voice_mode == "real"
            else "MOCK_SIMULATED"
        ),
        usage_basis={
            "stt_seconds": "pcm_frames_accepted_by_stt_pipeline",
            "llm_tokens": (
                f"provider_reported_for_completed_responses; provider={llm_provider}"
            ),
            "tts_characters": (
                "text_submitted_to_tts_pipeline; credential_free_tts_rate_zero"
                if tts_provider in {"gtts", "edge"}
                else "text_submitted_to_tts_pipeline"
            ),
            "estimated_usd": "operator_rates_not_provider_invoice",
        },
        provider_errors=runtime.usage.provider_errors,
        stt_reconnects=stt_reconnects,
        dropped_mic_frames=dropped_mic_frames,
        overlay_reconnect_count=runtime.reconnect_count,
        telemetry=runtime.telemetry.summary(),
    )
