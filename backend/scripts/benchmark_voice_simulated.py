"""Reproducible Phase 3 pipeline benchmark with simulated provider latency.

This never calls Deepgram, OpenAI, Google, or OBS and its output must not be
reported as real-provider performance.
"""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
import uuid
from collections.abc import AsyncIterator

from app.voice.generation import RealVoiceGenerator
from app.voice.providers import LlmDelta


class SimulatedLlm:
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[LlmDelta]:
        del messages
        await asyncio.sleep(0.08)
        yield LlmDelta("Kira nghe rõ rồi! ")
        await asyncio.sleep(0.04)
        yield LlmDelta("Mình cùng tiếp tục nhé.")
        yield LlmDelta("", input_tokens=24, output_tokens=15)


class SimulatedTts:
    sample_rate_hz = 24_000

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]:
        del text, context_id
        await asyncio.sleep(0.06)
        for _ in range(3):
            await asyncio.sleep(0.005)
            yield b"\x00\x00" * 480


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


async def run(iterations: int = 20) -> dict[str, object]:
    first_audio_values: list[float] = []
    for _ in range(iterations):
        first_audio = 0.0
        started = time.perf_counter_ns()
        generator = RealVoiceGenerator(SimulatedLlm(), SimulatedTts())

        async def on_text_ready(text: str) -> None:
            assert text

        async def on_audio(pcm: bytes, index: int) -> None:
            nonlocal first_audio
            del pcm, index
            if not first_audio:
                first_audio = (time.perf_counter_ns() - started) / 1_000_000

        await generator.generate(
            messages=[{"role": "user", "content": "Kira ơi"}],
            utterance_id=str(uuid.uuid4()),
            on_text_ready=on_text_ready,
            on_audio=on_audio,
        )
        first_audio_values.append(first_audio)

    cancel_started = 0
    cancelled_at = 0

    async def cancel_on_text(text: str) -> None:
        assert text

    async def cancel_on_audio(pcm: bytes, index: int) -> None:
        nonlocal cancel_started, cancelled_at
        del pcm, index
        cancel_started = time.perf_counter_ns()
        raise asyncio.CancelledError

    try:
        await RealVoiceGenerator(SimulatedLlm(), SimulatedTts()).generate(
            messages=[{"role": "user", "content": "stop"}],
            utterance_id=str(uuid.uuid4()),
            on_text_ready=cancel_on_text,
            on_audio=cancel_on_audio,
        )
    except asyncio.CancelledError:
        cancelled_at = time.perf_counter_ns()

    return {
        "measurement_scope": "SIMULATED_PROVIDER_LOCAL",
        "iterations": iterations,
        "event_to_first_audio_ms": {
            "p50": round(statistics.median(first_audio_values), 3),
            "p95": round(percentile(first_audio_values, 0.95), 3),
        },
        "cancellation_ms": round((cancelled_at - cancel_started) / 1_000_000, 3),
        "target_ms": {"p50": 2500, "p95": 5000},
        "real_providers_called": False,
        "obs_called": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
