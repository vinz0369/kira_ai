"""Verify the configured Deepgram streaming socket without recording audio."""

from __future__ import annotations

import asyncio
import sys

from app.voice.providers import PipecatDeepgramStt


async def main() -> None:
    async def transcript(text: str, final: bool) -> None:
        del text, final

    stream = PipecatDeepgramStt(transcript)
    try:
        await stream.start()
        sys.stdout.write("DEEPGRAM_STREAM_CONNECTED sample_rate=16000\n")
    finally:
        await stream.close()


if __name__ == "__main__":
    asyncio.run(main())
