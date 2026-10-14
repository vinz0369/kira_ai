from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from sqlmodel import SQLModel

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.integrations.youtube.oauth import get_connection

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ProviderPreflight(SQLModel):
    configured: bool
    status: Literal["ready", "missing", "invalid", "disabled"]
    model: str


class Phase3DiagnosticsPublic(SQLModel):
    measurement_scope: Literal["PREFLIGHT_ONLY"] = "PREFLIGHT_ONLY"
    real_voice_ready: bool
    deepgram: ProviderPreflight
    fpt_llm: ProviderPreflight
    openai: ProviderPreflight
    google_tts: ProviderPreflight
    gtts: ProviderPreflight
    edge_tts: ProviderPreflight
    cost_rates_configured: bool
    youtube_oauth_configured: bool
    youtube_connected: bool
    raw_audio_persisted: bool = False
    secrets_exposed_to_frontend: bool = False


@router.get("/phase3", response_model=Phase3DiagnosticsPublic)
def phase3_diagnostics(
    db: SessionDep, current_user: CurrentUser
) -> Phase3DiagnosticsPublic:
    """Return only safe readiness metadata; never keys, tokens, or file paths."""
    credentials = (
        Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
        if settings.GOOGLE_APPLICATION_CREDENTIALS
        else None
    )
    google_present = credentials is not None
    google_readable = bool(credentials and credentials.is_file())
    connection = get_connection(db, current_user.id)
    return Phase3DiagnosticsPublic(
        real_voice_ready=(
            settings.real_voice_configured
            and settings.tts_provider_configured(settings.DEFAULT_REAL_TTS_PROVIDER)
        ),
        deepgram=ProviderPreflight(
            configured=bool(settings.DEEPGRAM_API_KEY),
            status="ready" if settings.DEEPGRAM_API_KEY else "missing",
            model=settings.DEEPGRAM_MODEL,
        ),
        fpt_llm=ProviderPreflight(
            configured=bool(settings.FPT_API_KEY),
            status="ready" if settings.FPT_API_KEY else "missing",
            model=settings.FPT_LLM_MODEL,
        ),
        openai=ProviderPreflight(
            configured=bool(settings.OPENAI_API_KEY),
            status="ready" if settings.OPENAI_API_KEY else "missing",
            model=settings.OPENAI_MODEL,
        ),
        google_tts=ProviderPreflight(
            configured=google_readable,
            status=(
                "ready"
                if google_readable
                else "invalid"
                if google_present
                else "missing"
            ),
            model=f"{settings.GOOGLE_TTS_LANGUAGE}/{settings.GOOGLE_TTS_VOICE_ID}",
        ),
        gtts=ProviderPreflight(
            configured=True,
            status="ready",
            model=f"gTTS/{settings.GTTS_LANGUAGE}",
        ),
        edge_tts=ProviderPreflight(
            configured=settings.EDGE_TTS_EXPERIMENTAL_ENABLED,
            status=(
                "ready" if settings.EDGE_TTS_EXPERIMENTAL_ENABLED else "disabled"
            ),
            model=settings.EDGE_TTS_VOICE_ID,
        ),
        cost_rates_configured=settings.voice_cost_rates_configured,
        youtube_oauth_configured=settings.youtube_configured,
        youtube_connected=bool(connection and connection.status == "connected"),
    )
