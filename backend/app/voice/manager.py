from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter_ns

from app.live.contracts import EventEnvelope, make_event
from app.voice.protocol import AudioFrame
from app.voice.providers import PipecatDeepgramStt, StreamingStt

EventCallback = Callable[[EventEnvelope], Awaitable[None]]


@dataclass(slots=True)
class MicStreamState:
    turn_id: uuid.UUID | None = None
    last_sequence: int = -1
    audio_ms: int = 0


class VoiceInputSession:
    """Owns STT lifecycle and enforces ordering without retaining raw audio."""

    def __init__(
        self,
        session_id: uuid.UUID,
        callback: EventCallback,
        stt_factory: Callable[
            [Callable[[str, bool], Awaitable[None]]], StreamingStt
        ] = PipecatDeepgramStt,
    ) -> None:
        self.session_id = session_id
        self._callback = callback
        self._stt_factory = stt_factory
        self._stt: StreamingStt | None = None
        self.state = MicStreamState()
        self.reconnects = 0
        self.dropped_frames = 0
        self.provider_errors = 0
        self.turn_end_ns: int | None = None
        self._was_disconnected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._stt is not None:
                return
            self._stt = self._stt_factory(self._transcript)
            try:
                await self._stt.start()
            except Exception:
                self.provider_errors += 1
                await self._stt.close()
                self._stt = None
                raise

    async def begin_turn(self, turn_id: uuid.UUID) -> None:
        self.state.turn_id = turn_id
        self.state.last_sequence = -1
        self.turn_end_ns = None
        await self._callback(
            make_event(
                self.session_id,
                "streamer.speech.started",
                "voice",
                {"turn_id": str(turn_id)},
            )
        )

    async def audio(self, frame: AudioFrame) -> None:
        if frame.stream_id != self.state.turn_id:
            self.dropped_frames += 1
            return
        if frame.sequence <= self.state.last_sequence:
            self.dropped_frames += 1
            return
        self.state.last_sequence = frame.sequence
        if self._stt is None:
            self.dropped_frames += 1
            return
        delivered = await self._stt.send(frame.pcm)
        if not delivered:
            # Pipecat reconnects in place; never replay stale mic audio.
            self.dropped_frames += 1
            if not self._was_disconnected:
                self.reconnects += 1
            self._was_disconnected = True
        else:
            self.state.audio_ms += round(len(frame.pcm) / 2 / 16_000 * 1000)
            self._was_disconnected = False

    async def end_turn(self, turn_id: uuid.UUID) -> None:
        if turn_id != self.state.turn_id:
            return
        # This is the server-side receipt of the browser VAD end event. It uses
        # the same monotonic clock as all following backend measurements.
        self.turn_end_ns = perf_counter_ns()
        if self._stt:
            await self._stt.finish_turn()
        await self._callback(
            make_event(
                self.session_id,
                "streamer.speech.ended",
                "voice",
                {"turn_id": str(turn_id)},
            )
        )

    async def close(self) -> None:
        async with self._lock:
            if self._stt:
                await self._stt.close()
            self._stt = None
            self.state.turn_id = None

    async def _transcript(self, text: str, final: bool) -> None:
        turn_id = self.state.turn_id
        if not turn_id or not text.strip():
            return
        event_type = (
            "streamer.transcript.final" if final else "streamer.transcript.partial"
        )
        await self._callback(
            make_event(
                self.session_id,
                event_type,
                "voice",
                {"turn_id": str(turn_id), "text": text.strip(), "confidence": 1.0},
            )
        )
