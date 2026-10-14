from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.live.adapters import FakeTtsAdapter
from app.voice.llm import build_llm
from app.voice.providers import LlmDelta, pop_speakable_clause
from app.voice.tts import build_tts


class StreamingLlm(Protocol):
    async def stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[LlmDelta]:
        yield LlmDelta("")


class StreamingTts(Protocol):
    sample_rate_hz: int

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        yield b""


@dataclass(slots=True)
class GenerationResult:
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    tts_characters: int = 0
    llm_first_token_ms: float = 0
    llm_total_ms: float = 0
    tts_first_audio_ms: float = 0
    provider_errors: int = 0
    used_llm_fallback: bool = False
    used_tts_fallback: bool = False


class RealVoiceGenerator:
    """Streams LLM clauses into TTS; cancellation propagates through both."""

    def __init__(
        self,
        llm: StreamingLlm | None = None,
        tts: StreamingTts | None = None,
        llm_provider: str = "fpt",
        llm_model: str | None = None,
        tts_provider: str = "gtts",
        voice_id: str | None = None,
    ) -> None:
        self._llm = llm or build_llm(llm_provider, llm_model)
        self._tts = tts or build_tts(tts_provider, voice_id)
        self.sample_rate_hz = self._tts.sample_rate_hz

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        utterance_id: str,
        on_text_ready: Callable[[str], Awaitable[None]],
        on_audio: Callable[[bytes, int], Awaitable[None]],
    ) -> GenerationResult:
        result = GenerationResult()
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)
        llm_started = time.perf_counter_ns()

        async def produce() -> None:
            buffer = ""
            first_delta = True
            attempts = 0
            while attempts < 2:
                try:
                    async for delta in self._llm.stream(messages):
                        if delta.input_tokens or delta.output_tokens:
                            result.input_tokens += delta.input_tokens
                            result.output_tokens += delta.output_tokens
                        if not delta.text:
                            continue
                        if first_delta:
                            result.llm_first_token_ms = round(
                                (time.perf_counter_ns() - llm_started) / 1_000_000, 3
                            )
                            first_delta = False
                        result.text += delta.text
                        buffer += delta.text
                        clause, buffer = pop_speakable_clause(buffer)
                        if clause:
                            await queue.put(clause)
                    clause, buffer = pop_speakable_clause(buffer, force=True)
                    if clause:
                        await queue.put(clause)
                    break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    result.provider_errors += 1
                    attempts += 1
                    if result.text or attempts >= 2:
                        result.used_llm_fallback = True
                        fallback = "Mình nghe rồi, nhưng kết nối AI đang chập chờn. Chờ mình một chút nhé!"
                        result.text = result.text or fallback
                        await queue.put(buffer.strip() or fallback)
                        break
                    await asyncio.sleep(0.15)
            await queue.put(None)
            result.llm_total_ms = round(
                (time.perf_counter_ns() - llm_started) / 1_000_000, 3
            )

        async def consume() -> None:
            chunk_index = 0
            text_announced = False
            fake_tts = FakeTtsAdapter()
            while True:
                clause = await queue.get()
                if clause is None:
                    return
                if not text_announced:
                    await on_text_ready(clause)
                    text_announced = True
                result.tts_characters += len(clause)
                tts_started = time.perf_counter_ns()
                received = False
                try:
                    async for pcm in self._tts.stream(clause, utterance_id):
                        if not received:
                            result.tts_first_audio_ms = round(
                                (time.perf_counter_ns() - tts_started) / 1_000_000,
                                3,
                            )
                            received = True
                        await on_audio(pcm, chunk_index)
                        chunk_index += 1
                except asyncio.CancelledError:
                    raise
                except Exception:
                    result.provider_errors += 1
                    # Local PCM fallback keeps the overlay operable but is clearly
                    # surfaced as degraded, never reported as provider performance.
                    result.used_tts_fallback = True
                    for chunk in fake_tts.synthesize(clause):
                        await on_audio(chunk.data, chunk_index)
                        chunk_index += 1

        producer = asyncio.create_task(produce())
        consumer = asyncio.create_task(consume())
        try:
            await asyncio.gather(producer, consumer)
        except asyncio.CancelledError:
            producer.cancel()
            consumer.cancel()
            await asyncio.gather(producer, consumer, return_exceptions=True)
            raise
        return result
