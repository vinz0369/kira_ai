from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from openai import AsyncOpenAI
from pipecat.frames.frames import (
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.tts import GoogleTTSService
from pipecat.workers.runner import WorkerRunner

from app.core.config import settings

TranscriptCallback = Callable[[str, bool], Awaitable[None]]


class StreamingStt(Protocol):
    async def start(self) -> None: ...
    async def send(self, pcm: bytes) -> bool: ...
    async def finish_turn(self) -> None: ...
    async def close(self) -> None: ...


class _TranscriptCollector(FrameProcessor):
    def __init__(self, callback: TranscriptCallback) -> None:
        super().__init__()
        self._callback = callback

    async def process_frame(self, frame: Any, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self._callback(frame.text, True)
        elif isinstance(frame, InterimTranscriptionFrame):
            await self._callback(frame.text, False)
        await self.push_frame(frame, direction)


class PipecatDeepgramStt:
    """One bounded Deepgram stream per connected dashboard microphone."""

    def __init__(self, callback: TranscriptCallback) -> None:
        if not settings.DEEPGRAM_API_KEY:
            raise RuntimeError("Deepgram is not configured")
        dg_settings = DeepgramSTTService.Settings(
            model=settings.DEEPGRAM_MODEL,
            language=settings.DEEPGRAM_LANGUAGE,
            endpointing=settings.DEEPGRAM_ENDPOINTING_MS,
            # Deepgram hosted streaming rejects values below 1000 with HTTP 400.
            # Clamp older local .env files (which used 900) without breaking boot.
            utterance_end_ms=max(1_000, settings.DEEPGRAM_UTTERANCE_END_MS),
            interim_results=True,
            punctuate=True,
            smart_format=True,
        )
        self._service = DeepgramSTTService(
            api_key=settings.DEEPGRAM_API_KEY,
            encoding="linear16",
            channels=1,
            sample_rate=16_000,
            settings=dg_settings,
        )
        # Pipecat populates _sample_rate during SetupFrame, but this service
        # opens its WebSocket before that frame is processed. Without the
        # initial value its connect query contains sample_rate=0 (HTTP 400).
        self._service._sample_rate = 16_000
        self._worker = PipelineWorker(
            Pipeline([self._service, _TranscriptCollector(callback)]),
            params=PipelineParams(
                audio_in_sample_rate=16_000,
                audio_out_sample_rate=settings.GOOGLE_TTS_SAMPLE_RATE_HZ,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            idle_timeout_secs=None,
        )
        self._runner = WorkerRunner(handle_sigint=False)
        self._runner_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._runner_task is None:
            await self._runner.add_workers(self._worker)
            self._runner_task = asyncio.create_task(self._runner.run())
            settled = self._service._connection_settled
            await asyncio.wait_for(settled.wait(), timeout=15)
            if self._service._connection is None:
                raise ConnectionError("Deepgram streaming connection was rejected")

    async def send(self, pcm: bytes) -> bool:
        # Pipecat reconnects its Deepgram WebSocket internally. Audio is never
        # retained for replay: a disconnected frame is dropped, not queued.
        if getattr(self._service, "_connection", None) is None:
            return False
        await self._worker.queue_frame(InputAudioRawFrame(pcm, 16_000, 1))
        return True

    async def finish_turn(self) -> None:
        await self._worker.queue_frame(VADUserStoppedSpeakingFrame())

    async def close(self) -> None:
        await self._worker.cancel(reason="dashboard microphone disconnected")
        await self._runner.cancel(reason="voice input closed")
        if self._runner_task:
            await asyncio.gather(self._runner_task, return_exceptions=True)
            self._runner_task = None


@dataclass(frozen=True, slots=True)
class LlmDelta:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class OpenAIStreamingLlm:
    def __init__(self, model: str | None = None) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI is not configured")
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.OPENAI_MODEL

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[LlmDelta]:
        stream = cast(
            Any,
            await self._client.responses.create(
                model=self.model,
                input=cast(Any, messages),
                max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
                store=False,
                stream=True,
            ),
        )
        try:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield LlmDelta(event.delta)
                elif event.type == "response.completed":
                    usage = event.response.usage
                    if usage:
                        yield LlmDelta(
                            "",
                            input_tokens=usage.input_tokens,
                            output_tokens=usage.output_tokens,
                        )
        finally:
            close = getattr(stream, "close", None)
            if close:
                await close()


class GoogleChirpTts:
    sample_rate_hz = settings.GOOGLE_TTS_SAMPLE_RATE_HZ

    def __init__(self, voice_id: str | None = None) -> None:
        if not settings.GOOGLE_APPLICATION_CREDENTIALS:
            raise RuntimeError("Google Cloud TTS is not configured")
        self._service = GoogleTTSService(
            credentials_path=settings.GOOGLE_APPLICATION_CREDENTIALS,
            location=settings.GOOGLE_TTS_LOCATION,
            sample_rate=self.sample_rate_hz,
            settings=GoogleTTSService.Settings(
                voice=voice_id or settings.GOOGLE_TTS_VOICE_ID,
                language=settings.GOOGLE_TTS_LANGUAGE,
                speaking_rate=1.04,
            ),
        )

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        async for frame in self._service.run_tts(text, context_id):
            if isinstance(frame, TTSAudioRawFrame) and frame.audio:
                yield frame.audio


def pop_speakable_clause(buffer: str, *, force: bool = False) -> tuple[str, str]:
    """Split early at Vietnamese-friendly punctuation without tiny TTS calls."""
    match = re.search(r"(?<=[.!?…])\s+", buffer)
    if match and match.end() >= 24:
        return buffer[: match.end()].strip(), buffer[match.end() :]
    if len(buffer) >= 120:
        split = buffer.rfind(" ", 55, 105)
        if split > 0:
            return buffer[:split].strip(), buffer[split + 1 :]
    if force and buffer.strip():
        return buffer.strip(), ""
    return "", buffer


async def retry_once(
    operation: Callable[[], Awaitable[Any]], *, delay_seconds: float = 0.15
) -> Any:
    try:
        return await operation()
    except asyncio.CancelledError:
        raise
    except Exception:
        await asyncio.sleep(delay_seconds)
        return await operation()


def monotonic_ms() -> float:
    return time.perf_counter_ns() / 1_000_000
