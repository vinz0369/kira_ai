from __future__ import annotations

from dataclasses import dataclass
from typing import cast


@dataclass(slots=True)
class VoiceUsage:
    stt_audio_ms: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    tts_characters: int = 0
    provider_errors: int = 0
    stt_reconnects: int = 0
    dropped_mic_frames: int = 0

    def estimated_usd(
        self,
        *,
        stt_per_minute: float | None,
        llm_input_per_million: float | None,
        llm_output_per_million: float | None,
        tts_per_million_chars: float | None,
    ) -> float | None:
        rates = (
            stt_per_minute,
            llm_input_per_million,
            llm_output_per_million,
            tts_per_million_chars,
        )
        if any(rate is None for rate in rates):
            return None
        stt_rate = cast(float, stt_per_minute)
        input_rate = cast(float, llm_input_per_million)
        output_rate = cast(float, llm_output_per_million)
        tts_rate = cast(float, tts_per_million_chars)
        cost = self.stt_audio_ms / 60_000 * stt_rate
        cost += self.llm_input_tokens / 1_000_000 * input_rate
        cost += self.llm_output_tokens / 1_000_000 * output_rate
        cost += self.tts_characters / 1_000_000 * tts_rate
        return round(cost, 6)
