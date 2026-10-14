"""Real-network benchmark for credential-free Vietnamese TTS providers.

This calls gTTS and, when requested, the experimental Edge endpoint. It writes
one WAV sample per voice for human listening, but automated signal checks do not
claim naturalness or pronunciation quality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import struct
import time
import wave
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.voice.tts import EdgeExperimentalTts, GttsVietnameseTts

PROMPTS = (
    ("neutral", "Kira, tóm tắt tình huống trận này trong hai câu."),
    ("gaming_slang", "Combat này team mình outplay hay feed vậy?"),
    ("mixed_terms", "Check cooldown ulti rồi call team push mid nhé."),
    ("names_numbers", "Minh vừa donate năm mươi nghìn đồng lúc hai mươi giờ."),
    ("expressive", "Ôi, pha xử lý đẹp quá! Bình tĩnh, mình vẫn còn cơ hội."),
)


class StreamingTts(Protocol):
    sample_rate_hz: int

    async def stream(self, text: str, context_id: str) -> AsyncIterator[bytes]: ...


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def signal_metrics(pcm: bytes, sample_rate_hz: int) -> dict[str, float | bool]:
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm) if pcm else ()
    if not samples:
        return {
            "duration_seconds": 0.0,
            "rms_dbfs": -120.0,
            "peak": 0.0,
            "clipping_ratio": 0.0,
            "integrity_pass": False,
        }
    normalized_rms = math.sqrt(
        sum(sample * sample for sample in samples) / len(samples)
    ) / 32768
    peak = max(abs(sample) for sample in samples) / 32768
    clipping = sum(abs(sample) >= 32760 for sample in samples) / len(samples)
    rms_dbfs = 20 * math.log10(max(normalized_rms, 1e-6))
    duration = len(samples) / sample_rate_hz
    return {
        "duration_seconds": round(duration, 3),
        "rms_dbfs": round(rms_dbfs, 3),
        "peak": round(peak, 5),
        "clipping_ratio": round(clipping, 6),
        "integrity_pass": duration > 0.3 and -45 < rms_dbfs < -3 and clipping < 0.01,
    }


def write_wav(path: Path, pcm: bytes, sample_rate_hz: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate_hz)
        output.writeframes(pcm)


async def synthesize_once(
    adapter: StreamingTts, text: str, context_id: str
) -> tuple[bytes, float]:
    started = time.perf_counter_ns()
    first_audio_ms = 0.0
    chunks: list[bytes] = []
    async for chunk in adapter.stream(text, context_id):
        if not first_audio_ms:
            first_audio_ms = (time.perf_counter_ns() - started) / 1_000_000
        chunks.append(chunk)
    return b"".join(chunks), first_audio_ms


async def cancellation_ms(factory: Callable[[], StreamingTts]) -> float:
    adapter = factory()

    async def consume() -> None:
        async for _ in adapter.stream(PROMPTS[-1][1] * 3, "cancel"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    started = time.perf_counter_ns()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return (time.perf_counter_ns() - started) / 1_000_000


async def benchmark_voice(
    *,
    provider: str,
    voice_id: str,
    factory: Callable[[], StreamingTts],
    repeats: int,
    output_dir: Path,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    sample_written = False
    for repeat in range(repeats):
        for prompt_id, text in PROMPTS:
            try:
                adapter = factory()
                pcm, first_audio_ms = await synthesize_once(
                    adapter, text, f"{provider}-{voice_id}-{repeat}-{prompt_id}"
                )
                metrics = signal_metrics(pcm, adapter.sample_rate_hz)
                runs.append(
                    {
                        "prompt": prompt_id,
                        "repeat": repeat + 1,
                        "success": True,
                        "first_audio_ms": round(first_audio_ms, 3),
                        **metrics,
                    }
                )
                if not sample_written:
                    write_wav(
                        output_dir / f"{provider}-{voice_id}.wav",
                        pcm,
                        adapter.sample_rate_hz,
                    )
                    sample_written = True
            except Exception as exc:
                runs.append(
                    {
                        "prompt": prompt_id,
                        "repeat": repeat + 1,
                        "success": False,
                        "error_type": type(exc).__name__,
                    }
                )
    successful = [run for run in runs if run["success"]]
    latencies = [float(run["first_audio_ms"]) for run in successful]
    integrity = [bool(run["integrity_pass"]) for run in successful]
    return {
        "provider": provider,
        "voice_id": voice_id,
        "attempts": len(runs),
        "successes": len(successful),
        "reliability_percent": round(len(successful) / len(runs) * 100, 1),
        "first_audio_ms": {
            "p50": round(statistics.median(latencies), 3) if latencies else None,
            "p95": (
                round(value, 3)
                if (value := percentile(latencies, 0.95)) is not None
                else None
            ),
        },
        "automated_signal_integrity_percent": (
            round(sum(integrity) / len(integrity) * 100, 1) if integrity else 0.0
        ),
        "cancellation_dispatch_ms": round(await cancellation_ms(factory), 3),
        "runs": runs,
    }


async def run(repeats: int, output_dir: Path, include_edge: bool) -> dict[str, Any]:
    results = [
        await benchmark_voice(
            provider="gtts",
            voice_id="vi",
            factory=GttsVietnameseTts,
            repeats=repeats,
            output_dir=output_dir,
        )
    ]
    if include_edge:
        settings.EDGE_TTS_EXPERIMENTAL_ENABLED = True
        for voice_id in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
            results.append(
                await benchmark_voice(
                    provider="edge_experimental",
                    voice_id=voice_id,
                    factory=lambda voice_id=voice_id: EdgeExperimentalTts(voice_id),
                    repeats=repeats,
                    output_dir=output_dir,
                )
            )
    return {
        "measurement_scope": "REAL_CREDENTIAL_FREE_TTS_NETWORK",
        "generated_at_unix": int(time.time()),
        "prompts": [prompt_id for prompt_id, _ in PROMPTS],
        "repeats": repeats,
        "providers": results,
        "audio_contract": "pcm_s16le/24000Hz/mono",
        "obs_called": False,
        "human_naturalness_rating": "NOT_TESTED",
        "quality_note": (
            "Signal integrity is automated. Naturalness, Vietnamese pronunciation, "
            "and gaming-slang quality require listening to the exported WAV files."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../.tmp/free-tts-benchmark"),
    )
    parser.add_argument("--include-edge", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        raise SystemExit("--repeats must be between 1 and 10")
    result = asyncio.run(run(args.repeats, args.output_dir, args.include_edge))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = args.output_dir / "benchmark.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
