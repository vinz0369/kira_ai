from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

import av
import edge_tts
from av.audio.resampler import AudioResampler
from gtts import gTTS  # type: ignore[import-untyped]

from app.core.config import settings
from app.voice.providers import GoogleChirpTts

PCM_CHUNK_BYTES = 12_000


@dataclass(frozen=True, slots=True)
class TtsVoiceOption:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class TtsProviderOption:
    id: str
    label: str
    description: str
    experimental: bool
    credential_required: bool
    voices: tuple[TtsVoiceOption, ...]


TTS_PROVIDER_OPTIONS: tuple[TtsProviderOption, ...] = (
    TtsProviderOption(
        id="fake",
        label="Mock tone",
        description="Âm thanh kiểm thử offline; Voice Real tự dùng gTTS.",
        experimental=False,
        credential_required=False,
        voices=(TtsVoiceOption("mock-sine", "Mock sine"),),
    ),
    TtsProviderOption(
        id="gtts",
        label="gTTS tiếng Việt",
        description="Không cần API key; dùng dịch vụ Google Translate online.",
        experimental=False,
        credential_required=False,
        voices=(TtsVoiceOption("vi", "Tiếng Việt"),),
    ),
    TtsProviderOption(
        id="google_chirp",
        label="Google Chirp 3 HD",
        description="Provider chính thức, cần Google Cloud credentials.",
        experimental=False,
        credential_required=True,
        voices=(
            TtsVoiceOption(
                "vi-VN-Chirp3-HD-Leda", "Leda · Chirp 3 HD · vi-VN"
            ),
        ),
    ),
    TtsProviderOption(
        id="edge",
        label="Edge TTS",
        description="Không cần API key; endpoint không chính thức, thử nghiệm.",
        experimental=True,
        credential_required=False,
        voices=(
            TtsVoiceOption("vi-VN-HoaiMyNeural", "Hoài My · nữ"),
            TtsVoiceOption("vi-VN-NamMinhNeural", "Nam Minh · nam"),
        ),
    ),
)


def normalize_real_tts_provider(provider: str) -> str:
    return settings.DEFAULT_REAL_TTS_PROVIDER if provider == "fake" else provider


def default_voice_id(provider: str) -> str:
    normalized = normalize_real_tts_provider(provider)
    for option in TTS_PROVIDER_OPTIONS:
        if option.id == normalized:
            return option.voices[0].id
    raise ValueError("Unsupported TTS provider")


def validate_tts_selection(provider: str, voice_id: str) -> None:
    for option in TTS_PROVIDER_OPTIONS:
        if option.id != provider:
            continue
        if any(voice.id == voice_id for voice in option.voices):
            return
        raise ValueError("Unsupported voice for selected TTS provider")
    raise ValueError("Unsupported TTS provider")


def _pcm_chunks(mp3: bytes, sample_rate_hz: int) -> list[bytes]:
    if not mp3:
        raise RuntimeError("TTS provider returned empty audio")
    decoded: list[bytes] = []
    with av.open(BytesIO(mp3), mode="r", format="mp3") as container:
        resampler = AudioResampler(format="s16", layout="mono", rate=sample_rate_hz)
        for frame in container.decode(audio=0):
            for output in resampler.resample(frame):
                decoded.append(bytes(output.planes[0])[: output.samples * 2])
        for output in resampler.resample(None):
            decoded.append(bytes(output.planes[0])[: output.samples * 2])
    pcm = b"".join(decoded)
    if not pcm:
        raise RuntimeError("TTS audio could not be decoded")
    chunk_size = PCM_CHUNK_BYTES - (PCM_CHUNK_BYTES % 2)
    return [pcm[index : index + chunk_size] for index in range(0, len(pcm), chunk_size)]


class GttsVietnameseTts:
    """Credential-free network TTS; MP3 is decoded in memory and never persisted."""

    sample_rate_hz = settings.FREE_TTS_SAMPLE_RATE_HZ

    @staticmethod
    def _synthesize(text: str) -> bytes:
        output = BytesIO()
        gTTS(
            text=text,
            lang=settings.GTTS_LANGUAGE,
            tld=settings.GTTS_TLD,
            lang_check=False,
            timeout=settings.GTTS_TIMEOUT_SECONDS,
        ).write_to_fp(output)
        return output.getvalue()

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        del context_id
        mp3 = await asyncio.wait_for(
            asyncio.to_thread(self._synthesize, text),
            timeout=settings.GTTS_TIMEOUT_SECONDS + 2,
        )
        chunks = await asyncio.to_thread(_pcm_chunks, mp3, self.sample_rate_hz)
        for chunk in chunks:
            yield chunk


class EdgeExperimentalTts:
    """Experimental keyless Edge endpoint; disabled unless explicitly enabled."""

    sample_rate_hz = settings.FREE_TTS_SAMPLE_RATE_HZ

    def __init__(self, voice_id: str | None = None) -> None:
        if not settings.EDGE_TTS_EXPERIMENTAL_ENABLED:
            raise RuntimeError("Experimental Edge TTS is disabled")
        self.voice_id = voice_id or settings.EDGE_TTS_VOICE_ID

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        del context_id
        audio = bytearray()
        for attempt in range(2):
            audio.clear()
            try:
                communicate = edge_tts.Communicate(
                    text,
                    self.voice_id,
                    rate=settings.EDGE_TTS_RATE,
                )
                async for raw_chunk in communicate.stream():
                    audio_chunk = cast(dict[str, Any], raw_chunk)
                    if audio_chunk.get("type") == "audio" and isinstance(
                        audio_chunk.get("data"), bytes
                    ):
                        audio.extend(audio_chunk["data"])
                if audio:
                    break
                raise RuntimeError("Edge TTS returned empty audio")
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == 1:
                    raise
                await asyncio.sleep(0.15)
        chunks = await asyncio.to_thread(
            _pcm_chunks, bytes(audio), self.sample_rate_hz
        )
        for pcm_chunk in chunks:
            yield pcm_chunk


def build_tts(provider: str, voice_id: str | None = None) -> Any:
    normalized = normalize_real_tts_provider(provider)
    selected_voice = voice_id if provider != "fake" else None
    selected_voice = selected_voice or default_voice_id(normalized)
    validate_tts_selection(normalized, selected_voice)
    if not settings.tts_provider_configured(normalized):
        raise RuntimeError(f"TTS provider {normalized} is not configured")
    if normalized == "gtts":
        return GttsVietnameseTts()
    if normalized == "edge":
        return EdgeExperimentalTts(selected_voice)
    if normalized == "google_chirp":
        return GoogleChirpTts(selected_voice)
    raise ValueError("Unsupported TTS provider")
