"""Real-network provider chain with synthetic speech; no mic, VAD, or OBS."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from io import BytesIO

from gtts import gTTS  # type: ignore[import-untyped]

from app.voice.generation import RealVoiceGenerator
from app.voice.providers import PipecatDeepgramStt
from app.voice.tts import _pcm_chunks


def input_pcm() -> bytes:
    output = BytesIO()
    gTTS("Kira ơi, trận này mình nên đẩy đường giữa hay ăn rồng?", lang="vi").write_to_fp(output)
    return b"".join(_pcm_chunks(output.getvalue(), 16_000))


async def main() -> None:
    text_parts: list[str] = []
    final = asyncio.Event()

    async def on_transcript(text: str, is_final: bool) -> None:
        if is_final and text.strip():
            text_parts.append(text.strip())
            final.set()

    pcm = await asyncio.to_thread(input_pcm)
    stt = PipecatDeepgramStt(on_transcript)
    try:
        await stt.start()
        for offset in range(0, len(pcm), 3_200):
            await stt.send(pcm[offset : offset + 3_200])
            await asyncio.sleep(0.1)
        speech_end = time.perf_counter_ns()
        for _ in range(10):
            await stt.send(bytes(3_200))
            await asyncio.sleep(0.1)
        await stt.finish_turn()
        await asyncio.wait_for(final.wait(), timeout=10)
        stt_final_ms = (time.perf_counter_ns() - speech_end) / 1_000_000
    finally:
        await stt.close()

    transcript = " ".join(text_parts)
    generator = RealVoiceGenerator(llm_provider="fpt", tts_provider="gtts")
    audio_chunks = 0

    async def on_text(text: str) -> None:
        if not text:
            raise RuntimeError("Empty FPT answer")

    async def on_audio(audio: bytes, index: int) -> None:
        nonlocal audio_chunks
        if not audio or index != audio_chunks:
            raise RuntimeError("Invalid TTS audio chunk")
        audio_chunks += 1

    result = await generator.generate(
        messages=[
            {"role": "system", "content": "Bạn là Kira, trợ lý livestream. Trả lời ngắn gọn bằng tiếng Việt."},
            {"role": "user", "content": transcript},
        ],
        utterance_id=str(uuid.uuid4()),
        on_text_ready=on_text,
        on_audio=on_audio,
    )
    if result.used_llm_fallback or result.used_tts_fallback or not audio_chunks:
        raise RuntimeError("Provider chain fell back or returned no audio")
    sys.stdout.write(json.dumps({
        "scope": "REAL_DEEPGRAM_FPT_GTTS_SYNTHETIC_INPUT_NO_BROWSER_NO_OBS",
        "transcript": transcript,
        "response": result.text,
        "synthetic_speech_end_to_stt_final_ms": round(stt_final_ms, 3),
        "llm_first_token_ms": result.llm_first_token_ms,
        "tts_first_audio_ms": result.tts_first_audio_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "audio_chunks": audio_chunks,
    }, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
