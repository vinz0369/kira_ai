from __future__ import annotations

import asyncio
import statistics
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.live.contracts import EventEnvelope
from app.live.telemetry import DevelopmentTelemetry, monotonic_ns
from app.voice.generation import RealVoiceGenerator
from app.voice.manager import VoiceInputSession
from app.voice.protocol import MIC_DIRECTION, AudioFrame
from app.voice.providers import LlmDelta, OpenAIStreamingLlm, PipecatDeepgramStt


def test_deepgram_connect_uses_mic_sample_rate_before_pipeline_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEEPGRAM_API_KEY", "test-key")

    async def callback(text: str, final: bool) -> None:
        del text, final

    async def scenario() -> None:
        stt = PipecatDeepgramStt(callback)
        assert stt._service._build_connect_kwargs()["sample_rate"] == "16000"
        assert int(stt._service._build_connect_kwargs()["utterance_end_ms"]) >= 1000

    asyncio.run(scenario())


class SimulatedLlm:
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[LlmDelta]:
        del messages
        await asyncio.sleep(0.005)
        yield LlmDelta("Chào bạn! ")
        await asyncio.sleep(0.002)
        yield LlmDelta("Mình sẵn sàng đồng hành.")
        yield LlmDelta("", input_tokens=20, output_tokens=12)


class SimulatedTts:
    sample_rate_hz = 24_000

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        del text, context_id
        await asyncio.sleep(0.004)
        yield b"\x00\x00" * 240
        yield b"\x01\x00" * 240


class FakeStt:
    def __init__(self, callback: Callable[[str, bool], Awaitable[None]]) -> None:
        self.callback = callback
        self.frames: list[bytes] = []
        self.closed = False

    async def start(self) -> None:
        return

    async def send(self, pcm: bytes) -> bool:
        self.frames.append(pcm)
        return True

    async def finish_turn(self) -> None:
        await self.callback("Kira, chào bạn", True)

    async def close(self) -> None:
        self.closed = True


def test_simulated_streaming_benchmark_and_usage() -> None:
    async def scenario() -> None:
        timings: list[float] = []

        async def run_once() -> float:
            generator = RealVoiceGenerator(SimulatedLlm(), SimulatedTts())
            audio: list[bytes] = []
            started = time.perf_counter()
            first_audio = 0.0

            async def on_text(text: str) -> None:
                assert text

            async def on_audio(pcm: bytes, index: int) -> None:
                nonlocal first_audio
                assert index == len(audio)
                audio.append(pcm)
                first_audio = first_audio or (time.perf_counter() - started) * 1000

            result = await generator.generate(
                messages=[{"role": "user", "content": "xin chào"}],
                utterance_id=str(uuid.uuid4()),
                on_text_ready=on_text,
                on_audio=on_audio,
            )
            assert result.input_tokens == 20
            assert result.output_tokens == 12
            assert result.tts_characters > 0
            assert len(audio) == 2
            return first_audio

        for _ in range(7):
            timings.append(await run_once())
        ordered = sorted(timings)
        p50 = statistics.median(ordered)
        p95 = ordered[-1]
        # SIMULATED_PROVIDER_LOCAL only: validates instrumentation/cadence, not
        # Deepgram/OpenAI/Google or network performance.
        assert p50 < 250
        assert p95 < 500

    asyncio.run(scenario())


def test_voice_input_deduplicates_frames_and_emits_final_transcript() -> None:
    async def scenario() -> None:
        events: list[EventEnvelope] = []
        instances: list[FakeStt] = []

        def factory(callback: Callable[[str, bool], Awaitable[None]]) -> FakeStt:
            instance = FakeStt(callback)
            instances.append(instance)
            return instance

        async def callback(event: EventEnvelope) -> None:
            events.append(event)

        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        voice = VoiceInputSession(session_id, callback, factory)
        await voice.connect()
        await voice.begin_turn(turn_id)
        frame = AudioFrame(MIC_DIRECTION, 0, turn_id, b"\x00\x00" * 160)
        await voice.audio(frame)
        await voice.audio(frame)
        await voice.audio(AudioFrame(MIC_DIRECTION, 1, uuid.uuid4(), frame.pcm))
        await voice.end_turn(turn_id)
        await voice.close()
        assert len(instances[0].frames) == 1
        assert voice.dropped_frames == 2
        assert voice.state.audio_ms == 10
        assert voice.turn_end_ns is not None
        assert [event.type for event in events] == [
            "streamer.speech.started",
            "streamer.transcript.final",
            "streamer.speech.ended",
        ]
        assert instances[0].closed

    asyncio.run(scenario())


def test_voice_latency_trace_starts_at_vad_end() -> None:
    telemetry = DevelopmentTelemetry("REAL_PROVIDER_LOCAL")
    vad_end = monotonic_ns() - 20_000_000
    trace = telemetry.start_utterance(
        trace_id=str(uuid.uuid4()),
        utterance_id=str(uuid.uuid4()),
        input_event_type="streamer.transcript.final",
        event_received_ns=monotonic_ns(),
        voice_turn_end_ns=vad_end,
        stt_final_ms=8.5,
        event_to_decision_ms=0.4,
        llm_ms=None,
        tts_first_audio_ms=None,
    )
    telemetry.mark_audio_sent(trace.utterance_id)
    updated = telemetry.mark_playback_started(trace.utterance_id, {})

    assert updated is trace
    assert trace.metrics["stt_final_ms"] == 8.5
    assert trace.metrics["voice_end_to_first_playback_ack_ms"] >= 20
    summary = telemetry.summary()
    assert summary["measurement_scope"] == "REAL_PROVIDER_LOCAL"
    assert summary["metrics"]["stt_final_ms"]["samples"] == 1
    assert summary["metrics"]["voice_end_to_first_playback_ack_ms"]["samples"] == 1


def test_degraded_fallback_trace_does_not_pollute_real_e2e_percentiles() -> None:
    telemetry = DevelopmentTelemetry("REAL_PROVIDER_LOCAL")
    trace = telemetry.start_utterance(
        trace_id=str(uuid.uuid4()),
        utterance_id=str(uuid.uuid4()),
        input_event_type="streamer.transcript.final",
        event_received_ns=monotonic_ns(),
        voice_turn_end_ns=monotonic_ns() - 5_000_000,
        stt_final_ms=3.0,
        event_to_decision_ms=0.2,
        llm_ms=None,
        tts_first_audio_ms=None,
    )
    trace.measurement_scope = "DEGRADED_FALLBACK_LOCAL"
    telemetry.mark_audio_sent(trace.utterance_id)
    telemetry.mark_playback_started(trace.utterance_id, {})

    assert trace.metrics["voice_end_to_first_playback_ack_ms"] >= 5
    assert "voice_end_to_first_playback_ack_ms" not in telemetry.summary()["metrics"]


def test_openai_responses_stream_disables_provider_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Stream:
        def __aiter__(self) -> Stream:
            return self

        async def __anext__(self) -> object:
            raise StopAsyncIteration

    class Responses:
        async def create(self, **kwargs: object) -> Stream:
            captured.update(kwargs)
            return Stream()

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(
        "app.voice.providers.AsyncOpenAI",
        lambda **_: SimpleNamespace(responses=Responses()),
    )

    async def scenario() -> None:
        adapter = OpenAIStreamingLlm()
        assert [delta async for delta in adapter.stream([])] == []

    asyncio.run(scenario())
    assert captured["store"] is False
    assert captured["stream"] is True
    assert captured["model"] == settings.OPENAI_MODEL


def test_streaming_generation_cancellation_stops_audio() -> None:
    async def scenario() -> None:
        generator = RealVoiceGenerator(SimulatedLlm(), SimulatedTts())
        chunks: list[bytes] = []

        async def on_text(text: str) -> None:
            assert text

        async def on_audio(pcm: bytes, index: int) -> None:
            del index
            chunks.append(pcm)
            raise asyncio.CancelledError

        task = asyncio.create_task(
            generator.generate(
                messages=[{"role": "user", "content": "stop"}],
                utterance_id=str(uuid.uuid4()),
                on_text_ready=on_text,
                on_audio=on_audio,
            )
        )
        try:
            await task
        except asyncio.CancelledError:
            pass
        before = len(chunks)
        await asyncio.sleep(0.02)
        assert len(chunks) == before == 1

    asyncio.run(scenario())
