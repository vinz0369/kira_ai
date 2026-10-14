from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol


class LlmAdapter(Protocol):
    def reply(self, character_name: str, candidate: dict[str, Any]) -> str: ...


@dataclass(frozen=True, slots=True)
class AudioChunk:
    data: bytes
    chunk_index: int


class TtsAdapter(Protocol):
    sample_rate_hz: int

    def synthesize(self, text: str) -> list[AudioChunk]: ...


class FakeLlmAdapter:
    """Deterministic Vietnamese replies; untrusted text is never executed."""

    def reply(self, character_name: str, candidate: dict[str, Any]) -> str:
        kind = candidate.get("type")
        if kind in {"youtube.superchat", "youtube.supersticker"}:
            author = str(candidate.get("author_name") or "bạn")[:80]
            return f"{character_name} cảm ơn {author} nhiều nha! Món quà này làm không khí vui hẳn."
        if kind == "chat":
            author = str(candidate.get("author_name") or "bạn")[:80]
            return f"{author} hỏi hay đó! {character_name} nghiêng về phương án bình tĩnh mà chơi tiếp nhé."
        return f"Có {character_name} đây! Cứ giữ nhịp bình tĩnh, ván này vẫn còn cửa thắng đẹp nhé."


class FakeTtsAdapter:
    """Produces original PCM tones, so the mock exercises real audio playback."""

    sample_rate_hz = 24_000

    def synthesize(self, text: str) -> list[AudioChunk]:
        # Long enough for deterministic browser cancellation tests without
        # flooding the dashboard/overlay with tiny base64 WebSocket messages.
        duration = min(6.2, max(6.0, len(text) / 35))
        sample_count = int(self.sample_rate_hz * duration)
        pcm = _mock_pcm(sample_count, self.sample_rate_hz)
        chunk_size = 24_000
        return [
            AudioChunk(pcm[offset : offset + chunk_size], offset // chunk_size)
            for offset in range(0, len(pcm), chunk_size)
        ]


@lru_cache(maxsize=4)
def _mock_pcm(sample_count: int, sample_rate_hz: int) -> bytes:
    """Build a distributable tone quickly and reuse it across mock turns."""
    period = max(16, sample_rate_hz // 240)
    wave = tuple(
        int(8_000 * math.sin(2 * math.pi * index / period))
        for index in range(period)
    )
    samples = array("h", (wave[index % period] for index in range(sample_count)))
    fade = min(sample_rate_hz // 100, sample_count // 2)
    for index in range(fade):
        samples[index] = samples[index] * index // fade
        samples[-index - 1] = samples[-index - 1] * index // fade
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()
