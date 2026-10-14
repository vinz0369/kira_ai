from __future__ import annotations

import asyncio
import base64
import time
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.live.adapters import FakeLlmAdapter, FakeTtsAdapter
from app.live.avatar_assets import effective_avatar_asset_id
from app.live.contracts import EventEnvelope, make_event
from app.live.director import ConversationDirector, DirectorState
from app.live.telemetry import (
    DevelopmentTelemetry,
    elapsed_ms,
    monotonic_ns,
    new_trace_id,
)
from app.voice.generation import RealVoiceGenerator
from app.voice.llm import normalize_real_llm_provider
from app.voice.manager import VoiceInputSession
from app.voice.prompting import ConversationMemory, build_messages
from app.voice.protocol import TTS_DIRECTION, AudioFrame, encode_audio_frame
from app.voice.tts import normalize_real_tts_provider
from app.voice.usage import VoiceUsage


class SessionRuntime:
    def __init__(
        self,
        status: str,
        ai_muted: bool,
        character_name: str,
        epoch: int,
        voice_mode: str = "mock",
        character_profile: dict[str, Any] | None = None,
    ) -> None:
        self.director = ConversationDirector(
            DirectorState(
                session=status,
                ai_muted=ai_muted,
                character_name=character_name,
                generation=epoch,
                chat_response_mode=settings.YOUTUBE_CHAT_RESPONSE_MODE,
            )
        )
        self.dashboard_sockets: set[WebSocket] = set()
        self.overlay_sockets: set[WebSocket] = set()
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=100)
        self.lock = asyncio.Lock()
        self.llm_calls = 0
        self.tts_characters = 0
        self.reconnect_count = 0
        self.voice_mode = voice_mode
        self.character_profile = character_profile or {}
        self.telemetry = DevelopmentTelemetry(
            "REAL_PROVIDER_LOCAL" if voice_mode == "real" else "MOCK_SIMULATED_LOCAL"
        )
        self.usage = VoiceUsage()
        self.memory = ConversationMemory()
        self.generation_task: asyncio.Task[None] | None = None
        self.voice_input: VoiceInputSession | None = None
        self.mic_connected = False


class LiveHub:
    def __init__(self) -> None:
        self._runtimes: dict[uuid.UUID, SessionRuntime] = {}
        self._llm = FakeLlmAdapter()
        self._tts = FakeTtsAdapter()

    def runtime(
        self,
        session_id: uuid.UUID,
        status: str = "draft",
        ai_muted: bool = True,
        character_name: str = "Kira",
        epoch: int = 0,
        voice_mode: str | None = None,
        character_profile: dict[str, Any] | None = None,
    ) -> SessionRuntime:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            runtime = SessionRuntime(
                status,
                ai_muted,
                character_name,
                epoch,
                voice_mode or "mock",
                character_profile,
            )
            self._runtimes[session_id] = runtime
        elif voice_mode is not None:
            runtime.voice_mode = voice_mode
            runtime.character_profile = character_profile or runtime.character_profile
            runtime.telemetry.scope = (
                "REAL_PROVIDER_LOCAL"
                if voice_mode == "real"
                else "MOCK_SIMULATED_LOCAL"
            )
        return runtime

    async def connect_dashboard(
        self, session_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        runtime = self.runtime(session_id)
        await websocket.accept()
        runtime.dashboard_sockets.add(websocket)
        await websocket.send_json(
            self._state_snapshot(session_id, runtime).model_dump(mode="json")
        )

    async def connect_overlay(
        self, session_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        runtime = self.runtime(session_id)
        await websocket.accept()
        if runtime.overlay_sockets:
            runtime.reconnect_count += 1
        runtime.overlay_sockets.add(websocket)
        await websocket.send_json(
            self._state_snapshot(session_id, runtime).model_dump(mode="json")
        )
        await websocket.send_json(
            make_event(
                session_id,
                "character.state",
                "system",
                {"mood": "neutral", "speaking": False},
            ).model_dump(mode="json")
        )
        await self._broadcast_dashboard(
            runtime,
            make_event(
                session_id,
                "overlay.connected",
                "overlay",
                {"connection_id": str(uuid.uuid4()), "client_version": "phase1-web"},
            ),
        )
        await self._broadcast_dashboard(
            runtime, self._state_snapshot(session_id, runtime), remember=True
        )

    def disconnect_dashboard(self, session_id: uuid.UUID, websocket: WebSocket) -> None:
        self.runtime(session_id).dashboard_sockets.discard(websocket)

    async def disconnect_overlay(
        self, session_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        runtime = self.runtime(session_id)
        runtime.overlay_sockets.discard(websocket)
        await self._broadcast_dashboard(
            runtime,
            make_event(
                session_id,
                "overlay.disconnected",
                "overlay",
                {"connection_id": "closed", "reason": "socket_closed"},
            ),
        )
        await self._broadcast_dashboard(
            runtime, self._state_snapshot(session_id, runtime), remember=True
        )

    async def process(
        self,
        session_id: uuid.UUID,
        event: EventEnvelope,
        character_name: str,
        *,
        voice_turn_end_ns: int | None = None,
        stt_final_ms: float | None = None,
    ) -> list[EventEnvelope]:
        runtime = self.runtime(session_id, character_name=character_name)
        runtime.director.state.character_name = character_name
        emitted: list[EventEnvelope] = []
        event_received_ns = monotonic_ns()
        trace_id = new_trace_id()
        async with runtime.lock:
            await self._broadcast_all(runtime, event, remember=True)
            active_before = runtime.director.state.active_utterance_id
            if self._expired(event):
                decision = runtime.director.handle(
                    "system.test.candidate_expired", {"expired": True}
                )
            else:
                decision = runtime.director.handle(event.type, event.payload)
            decision_ms = elapsed_ms(event_received_ns)
            runtime.telemetry.record("event_to_decision_ms", decision_ms)
            if decision.candidate is not None:
                decision.candidate["_telemetry"] = {
                    "trace_id": trace_id,
                    "event_received_ns": event_received_ns,
                    "decision_ms": decision_ms,
                    "input_event_type": event.type,
                    "voice_turn_end_ns": voice_turn_end_ns,
                    "stt_final_ms": stt_final_ms,
                }
            diagnostic = make_event(
                session_id,
                "director.decision",
                "director",
                {
                    "input_event_id": str(event.event_id),
                    "decision": decision.decision,
                    "reason_code": decision.reason_code,
                    "priority": decision.priority,
                    "trace_id": trace_id,
                    "event_to_decision_ms": decision_ms,
                    "measurement_scope": runtime.telemetry.scope,
                },
            )
            emitted.append(diagnostic)
            await self._broadcast_dashboard(runtime, diagnostic, remember=True)

            if decision.cancel_reason:
                if runtime.generation_task and not runtime.generation_task.done():
                    runtime.generation_task.cancel()
                if active_before:
                    runtime.telemetry.mark_cancel_requested(active_before)
                    cancel = make_event(
                        session_id,
                        "speech.cancel",
                        "director",
                        {
                            "utterance_id": active_before,
                            "reason": decision.cancel_reason,
                        },
                    )
                    emitted.append(cancel)
                    await self._broadcast_all(runtime, cancel, remember=True)
                    runtime.telemetry.mark_cancel_dispatched(active_before)

            if decision.decision == "respond" and decision.candidate:
                if runtime.voice_mode == "real":
                    self._start_real_speech(
                        session_id,
                        runtime,
                        decision.candidate,
                        character_name,
                        trace_id,
                        event.type,
                        event_received_ns,
                        decision_ms,
                    )
                else:
                    emitted.extend(
                        await self._speak(
                            session_id,
                            runtime,
                            decision.candidate,
                            character_name,
                            trace_id,
                            event.type,
                            event_received_ns,
                            decision_ms,
                        )
                    )

            if (
                event.type in {"streamer.speech.ended", "streamer.transcript.final"}
                and decision.decision != "respond"
            ):
                paid = runtime.director.pop_paid_candidate()
                if paid:
                    if runtime.voice_mode == "real":
                        self._start_real_speech(
                            session_id, runtime, paid, character_name
                        )
                    else:
                        emitted.extend(
                            await self._speak(session_id, runtime, paid, character_name)
                        )
                elif event.type == "streamer.transcript.final":
                    chat = runtime.director.pop_chat_candidate()
                    if chat:
                        if runtime.voice_mode == "real":
                            self._start_real_speech(
                                session_id, runtime, chat, character_name
                            )
                        else:
                            emitted.extend(
                                await self._speak(
                                    session_id, runtime, chat, character_name
                                )
                            )
        return emitted

    async def playback_ack(self, session_id: uuid.UUID, event: EventEnvelope) -> None:
        runtime = self.runtime(session_id)
        utterance_id = str(event.payload.get("utterance_id", ""))
        async with runtime.lock:
            trace = None
            if event.type == "speech.playback.started":
                trace = runtime.telemetry.mark_playback_started(
                    utterance_id, event.payload
                )
            elif event.type == "speech.playback.cancelled":
                trace = runtime.telemetry.mark_playback_cancelled(
                    utterance_id, event.payload
                )
            if event.type in {"speech.playback.completed", "speech.playback.cancelled"}:
                if runtime.director.state.active_utterance_id == utterance_id:
                    runtime.director.state.active_utterance_id = None
                    runtime.director.state.ai_speaking = False
                    await self._broadcast_all(
                        runtime,
                        make_event(
                            session_id,
                            "character.state",
                            "system",
                            {"mood": "neutral", "speaking": False},
                        ),
                        remember=True,
                    )
                    if event.type == "speech.playback.completed":
                        paid = runtime.director.pop_paid_candidate()
                        if paid:
                            if runtime.voice_mode == "real":
                                self._start_real_speech(
                                    session_id,
                                    runtime,
                                    paid,
                                    runtime.director.state.character_name,
                                    new_trace_id(),
                                    str(paid.get("type", "youtube.superchat")),
                                    monotonic_ns(),
                                    0.0,
                                )
                            else:
                                await self._speak(
                                    session_id,
                                    runtime,
                                    paid,
                                    runtime.director.state.character_name,
                                    new_trace_id(),
                                    str(paid.get("type", "youtube.superchat")),
                                    monotonic_ns(),
                                    0.0,
                                )
                        else:
                            chat = runtime.director.pop_chat_candidate()
                            if chat:
                                if runtime.voice_mode == "real":
                                    self._start_real_speech(
                                        session_id,
                                        runtime,
                                        chat,
                                        runtime.director.state.character_name,
                                    )
                                else:
                                    await self._speak(
                                        session_id,
                                        runtime,
                                        chat,
                                        runtime.director.state.character_name,
                                    )
            await self._broadcast_dashboard(runtime, event, remember=True)
            if trace:
                await self._broadcast_dashboard(
                    runtime,
                    make_event(
                        session_id,
                        "telemetry.update",
                        "system",
                        {
                            "measurement_scope": runtime.telemetry.scope,
                            **trace.public(),
                        },
                    ),
                    remember=True,
                )

    async def sync_control(
        self, session_id: uuid.UUID, command: str, status: str, ai_muted: bool
    ) -> list[EventEnvelope]:
        runtime = self.runtime(session_id, status=status, ai_muted=ai_muted)
        event = make_event(
            session_id, "session.control", "system", {"command": command}
        )
        emitted = await self.process(
            session_id, event, runtime.director.state.character_name
        )
        runtime.director.state.session = status
        runtime.director.state.ai_muted = ai_muted
        state_event = self._state_snapshot(session_id, runtime)
        await self._broadcast_all(runtime, state_event, remember=True)
        emitted.append(state_event)
        return emitted

    async def close_overlays(self, session_id: uuid.UUID) -> None:
        runtime = self.runtime(session_id)
        if runtime.generation_task and not runtime.generation_task.done():
            runtime.generation_task.cancel()
        if runtime.voice_input:
            await runtime.voice_input.close()
            runtime.voice_input = None
            runtime.mic_connected = False
        for socket in list(runtime.overlay_sockets):
            try:
                await socket.close(code=4003, reason="session stopped")
            except RuntimeError:
                pass
        runtime.overlay_sockets.clear()

    async def avatar_motion(
        self, session_id: uuid.UUID, motion: str, duration_seconds: int = 0
    ) -> None:
        """Ephemeral visual command; reconnect always returns to idle."""
        runtime = self.runtime(session_id)
        await self._broadcast_all(
            runtime,
            make_event(
                session_id,
                "avatar.motion",
                "system",
                {"motion": motion, "duration_seconds": duration_seconds},
            ),
        )

    async def provider_health(
        self, session_id: uuid.UUID, status: str, details: str
    ) -> None:
        runtime = self.runtime(session_id)
        await self._broadcast_dashboard(
            runtime,
            make_event(
                session_id,
                "provider.health",
                "system",
                {"provider": "youtube", "status": status, "details": details},
            ),
            remember=True,
        )

    async def connect_voice_input(self, session_id: uuid.UUID) -> None:
        runtime = self.runtime(session_id)
        if runtime.voice_mode != "real" or runtime.voice_input is not None:
            return

        voice_input_ref: list[VoiceInputSession] = []

        async def on_event(event: EventEnvelope) -> None:
            turn_end_ns = None
            final_ms = None
            if event.type == "streamer.transcript.final" and voice_input_ref:
                turn_end_ns = voice_input_ref[0].turn_end_ns
                if turn_end_ns is not None:
                    final_ms = elapsed_ms(turn_end_ns)
            await self.process(
                session_id,
                event,
                runtime.director.state.character_name,
                voice_turn_end_ns=turn_end_ns,
                stt_final_ms=final_ms,
            )

        voice_input = VoiceInputSession(session_id, on_event)
        voice_input_ref.append(voice_input)
        try:
            await voice_input.connect()
        except Exception:
            runtime.usage.provider_errors += 1
            await self._voice_health(runtime, session_id, "deepgram", "error")
            return
        runtime.voice_input = voice_input
        runtime.mic_connected = True
        await self._voice_health(runtime, session_id, "deepgram", "connected")
        await self._broadcast_all(
            runtime, self._state_snapshot(session_id, runtime), remember=True
        )

    async def disconnect_voice_input(self, session_id: uuid.UUID) -> None:
        runtime = self.runtime(session_id)
        if runtime.voice_input:
            runtime.usage.stt_audio_ms += runtime.voice_input.state.audio_ms
            runtime.usage.stt_reconnects += runtime.voice_input.reconnects
            runtime.usage.dropped_mic_frames += runtime.voice_input.dropped_frames
            runtime.usage.provider_errors += runtime.voice_input.provider_errors
            await runtime.voice_input.close()
            runtime.voice_input = None
        runtime.mic_connected = False
        await self._broadcast_all(
            runtime, self._state_snapshot(session_id, runtime), remember=True
        )

    async def voice_begin(self, session_id: uuid.UUID, turn_id: uuid.UUID) -> None:
        runtime = self.runtime(session_id)
        # The dashboard socket can survive an STT startup failure. Retry when
        # the next real mic turn begins instead of silently dropping its frames.
        if runtime.voice_mode == "real" and runtime.voice_input is None:
            await self.connect_voice_input(session_id)
        if runtime.voice_input:
            await runtime.voice_input.begin_turn(turn_id)

    async def voice_audio(self, session_id: uuid.UUID, frame: AudioFrame) -> None:
        runtime = self.runtime(session_id)
        if runtime.voice_input:
            await runtime.voice_input.audio(frame)

    async def voice_end(self, session_id: uuid.UUID, turn_id: uuid.UUID) -> None:
        runtime = self.runtime(session_id)
        if runtime.voice_input:
            await runtime.voice_input.end_turn(turn_id)

    def _start_real_speech(
        self,
        session_id: uuid.UUID,
        runtime: SessionRuntime,
        candidate: dict[str, Any],
        character_name: str,
        trace_id: str | None = None,
        input_event_type: str = "queued",
        event_received_ns: int | None = None,
        decision_ms: float = 0.0,
    ) -> None:
        telemetry_meta = candidate.get("_telemetry", {})
        voice_turn_end_ns = None
        stt_final_ms = None
        if isinstance(telemetry_meta, dict):
            raw_turn_end = telemetry_meta.get("voice_turn_end_ns")
            if isinstance(raw_turn_end, int):
                voice_turn_end_ns = raw_turn_end
            raw_stt_final = telemetry_meta.get("stt_final_ms")
            if isinstance(raw_stt_final, int | float):
                stt_final_ms = float(raw_stt_final)
        if runtime.generation_task and not runtime.generation_task.done():
            runtime.generation_task.cancel()
        # Mark the slot busy before scheduling the async provider task. Another
        # chat from the same YouTube batch must queue, not replace this reply.
        runtime.director.state.ai_speaking = True
        runtime.generation_task = asyncio.create_task(
            self._speak_real(
                session_id,
                runtime,
                candidate,
                character_name,
                trace_id or new_trace_id(),
                input_event_type,
                event_received_ns or monotonic_ns(),
                decision_ms,
                voice_turn_end_ns,
                stt_final_ms,
            )
        )

    async def _speak_real(
        self,
        session_id: uuid.UUID,
        runtime: SessionRuntime,
        candidate: dict[str, Any],
        character_name: str,
        trace_id: str,
        input_event_type: str,
        event_received_ns: int,
        decision_ms: float,
        voice_turn_end_ns: int | None,
        stt_final_ms: float | None,
    ) -> None:
        utterance_id = str(uuid.uuid4())
        generation = runtime.director.state.generation
        runtime.director.state.ai_speaking = True
        runtime.director.state.active_utterance_id = utterance_id
        trace = runtime.telemetry.start_utterance(
            trace_id=trace_id,
            utterance_id=utterance_id,
            input_event_type=input_event_type,
            event_received_ns=event_received_ns,
            voice_turn_end_ns=voice_turn_end_ns,
            stt_final_ms=stt_final_ms,
            event_to_decision_ms=decision_ms,
            llm_ms=None,
            tts_first_audio_ms=None,
        )
        profile = runtime.character_profile
        llm_provider = normalize_real_llm_provider(
            str(profile.get("llm_provider", "fake"))
        )
        llm_model = str(profile.get("llm_model") or "") or None
        tts_provider = normalize_real_tts_provider(
            str(profile.get("voice_provider", "fake"))
        )
        voice_id = str(profile.get("voice_id") or "") or None
        messages = build_messages(
            character_name=character_name,
            persona=str(profile.get("persona_description", "Bạn thân tinh nghịch")),
            address_streamer_as=str(profile.get("address_streamer_as", "bạn")),
            viewer_style=str(profile.get("viewer_style", "thân thiện")),
            candidate=candidate,
            memory=runtime.memory,
        )
        generator: RealVoiceGenerator | None = None
        announced = False
        audio_started = False

        def current() -> bool:
            state = runtime.director.state
            return (
                state.session == "active"
                and not state.ai_muted
                and state.generation == generation
                and state.active_utterance_id == utterance_id
            )

        async def on_text_ready(text: str) -> None:
            nonlocal announced
            if not current():
                raise asyncio.CancelledError
            announced = True
            await self._broadcast_all(
                runtime,
                make_event(
                    session_id,
                    "speech.start",
                    "tts",
                    {
                        "utterance_id": utterance_id,
                        "text": text,
                        "format": "pcm_s16le",
                        "sample_rate_hz": generator.sample_rate_hz
                        if generator
                        else 24000,
                        "channels": 1,
                        "generation": generation,
                        "expires_at": (datetime.now(UTC) + timedelta(seconds=15))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "trace_id": trace.trace_id,
                        "measurement_scope": runtime.telemetry.scope,
                        "llm_provider": llm_provider,
                        "tts_provider": tts_provider,
                    },
                ),
                remember=True,
            )

        async def on_audio(pcm: bytes, chunk_index: int) -> None:
            nonlocal audio_started
            if not current():
                raise asyncio.CancelledError
            if not audio_started:
                runtime.telemetry.mark_audio_sent(utterance_id)
                audio_started = True
            binary = encode_audio_frame(
                TTS_DIRECTION, chunk_index, uuid.UUID(utterance_id), pcm
            )
            await self._send_binary(runtime.overlay_sockets, binary)
            await self._broadcast_dashboard(
                runtime,
                make_event(
                    session_id,
                    "speech.audio.meta",
                    "tts",
                    {
                        "utterance_id": utterance_id,
                        "chunk_index": chunk_index,
                        "byte_length": len(pcm),
                    },
                ),
            )

        try:
            generator = RealVoiceGenerator(
                llm_provider=llm_provider,
                llm_model=llm_model,
                tts_provider=tts_provider,
                voice_id=voice_id,
            )
            result = await generator.generate(
                messages=messages,
                utterance_id=utterance_id,
                on_text_ready=on_text_ready,
                on_audio=on_audio,
            )
            if not current():
                return
            runtime.usage.llm_input_tokens += result.input_tokens
            runtime.usage.llm_output_tokens += result.output_tokens
            runtime.usage.tts_characters += result.tts_characters
            runtime.usage.provider_errors += result.provider_errors
            runtime.llm_calls += 1
            runtime.tts_characters += result.tts_characters
            if result.used_llm_fallback or result.used_tts_fallback:
                trace.measurement_scope = "DEGRADED_FALLBACK_LOCAL"
            if not result.used_llm_fallback and result.llm_first_token_ms > 0:
                trace.metrics["llm_first_token_ms"] = runtime.telemetry.record(
                    "llm_first_token_ms", result.llm_first_token_ms
                )
                trace.metrics["llm_total_ms"] = runtime.telemetry.record(
                    "llm_total_ms", result.llm_total_ms
                )
            if not result.used_tts_fallback and result.tts_first_audio_ms > 0:
                trace.metrics["tts_first_audio_ms"] = runtime.telemetry.record(
                    "tts_first_audio_ms", result.tts_first_audio_ms
                )
            source_text = str(candidate.get("text") or "")
            if source_text:
                runtime.memory.add("user", source_text)
            runtime.memory.add("assistant", result.text)
            if result.used_llm_fallback:
                await self._voice_health(
                    runtime, session_id, llm_provider, "degraded_fallback"
                )
            if result.used_tts_fallback:
                await self._voice_health(
                    runtime, session_id, tts_provider, "degraded_fallback"
                )
            if announced:
                await self._broadcast_all(
                    runtime,
                    make_event(
                        session_id,
                        "speech.end",
                        "tts",
                        {"utterance_id": utterance_id},
                    ),
                    remember=True,
                )
                await self._broadcast_all(
                    runtime,
                    make_event(
                        session_id,
                        "character.state",
                        "system",
                        {"mood": "neutral", "speaking": True},
                    ),
                    remember=True,
                )
        except asyncio.CancelledError:
            return
        except Exception:
            runtime.usage.provider_errors += 1
            runtime.director.state.ai_speaking = False
            runtime.director.state.active_utterance_id = None
            await self._voice_health(runtime, session_id, "voice", "error")

    async def _voice_health(
        self, runtime: SessionRuntime, session_id: uuid.UUID, provider: str, status: str
    ) -> None:
        await self._broadcast_dashboard(
            runtime,
            make_event(
                session_id,
                "provider.health",
                "system",
                {"provider": provider, "status": status},
            ),
            remember=True,
        )

    async def _speak(
        self,
        session_id: uuid.UUID,
        runtime: SessionRuntime,
        candidate: dict[str, Any],
        character_name: str,
        trace_id: str | None = None,
        input_event_type: str = "queued",
        event_received_ns: int | None = None,
        decision_ms: float = 0.0,
    ) -> list[EventEnvelope]:
        if (
            runtime.director.state.session != "active"
            or runtime.director.state.ai_muted
        ):
            return []
        telemetry_meta = candidate.get("_telemetry", {})
        if isinstance(telemetry_meta, dict):
            trace_id = str(telemetry_meta.get("trace_id") or trace_id or new_trace_id())
            input_event_type = str(
                telemetry_meta.get("input_event_type") or input_event_type
            )
            raw_received = telemetry_meta.get("event_received_ns")
            if isinstance(raw_received, int):
                event_received_ns = raw_received
            raw_decision = telemetry_meta.get("decision_ms")
            if isinstance(raw_decision, int | float):
                decision_ms = float(raw_decision)
        utterance_id = str(uuid.uuid4())
        generation = runtime.director.state.generation
        llm_started = time.perf_counter_ns()
        text = self._llm.reply(character_name, candidate)
        llm_ms = elapsed_ms(llm_started)
        tts_started = time.perf_counter_ns()
        chunks = self._tts.synthesize(text)
        tts_first_audio_ms = elapsed_ms(tts_started)
        trace = runtime.telemetry.start_utterance(
            trace_id=trace_id or new_trace_id(),
            utterance_id=utterance_id,
            input_event_type=input_event_type,
            event_received_ns=event_received_ns or monotonic_ns(),
            event_to_decision_ms=decision_ms,
            llm_ms=llm_ms,
            tts_first_audio_ms=tts_first_audio_ms,
        )
        runtime.llm_calls += 1
        runtime.tts_characters += len(text)
        runtime.director.state.ai_speaking = True
        runtime.director.state.active_utterance_id = utterance_id
        expires_at = datetime.now(UTC) + timedelta(seconds=10)
        events = [
            make_event(
                session_id,
                "speech.start",
                "tts",
                {
                    "utterance_id": utterance_id,
                    "text": text,
                    "format": "pcm_s16le",
                    "sample_rate_hz": self._tts.sample_rate_hz,
                    "channels": 1,
                    "generation": generation,
                    "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                    "trace_id": trace.trace_id,
                    "measurement_scope": runtime.telemetry.scope,
                },
            )
        ]
        for chunk in chunks:
            events.append(
                make_event(
                    session_id,
                    "speech.audio",
                    "tts",
                    {
                        "utterance_id": utterance_id,
                        "chunk_index": chunk.chunk_index,
                        "pcm_base64": base64.b64encode(chunk.data).decode(),
                    },
                )
            )
        events.append(
            make_event(
                session_id,
                "speech.end",
                "tts",
                {"utterance_id": utterance_id},
            )
        )
        events.append(
            make_event(
                session_id,
                "character.state",
                "system",
                {
                    "mood": "happy"
                    if "super" in str(candidate.get("type"))
                    else "neutral",
                    "speaking": True,
                },
            )
        )
        for outgoing in events:
            if outgoing.type == "speech.audio":
                runtime.telemetry.mark_audio_sent(utterance_id)
            await self._broadcast_all(
                runtime, outgoing, remember=outgoing.type != "speech.audio"
            )
        return events

    @staticmethod
    def _expired(event: EventEnvelope) -> bool:
        age = (datetime.now(UTC) - event.ts).total_seconds()
        ttl = 30 if event.type.startswith("youtube.super") else 8
        return age > ttl

    @staticmethod
    def _state_snapshot(
        session_id: uuid.UUID, runtime: SessionRuntime
    ) -> EventEnvelope:
        state = runtime.director.state
        return make_event(
            session_id,
            "session.state",
            "system",
            {
                "status": state.session,
                "ai_muted": state.ai_muted,
                "mic_connected": runtime.mic_connected,
                "overlay_connected": bool(runtime.overlay_sockets),
                "voice_mode": runtime.voice_mode,
                "avatar_asset_id": effective_avatar_asset_id(
                    runtime.character_profile.get("avatar_asset_id"),
                    state.character_name,
                ),
                "avatar_camera_framing": runtime.character_profile.get(
                    "avatar_camera_framing", "chest-up"
                ),
                "avatar_camera_zoom": runtime.character_profile.get(
                    "avatar_camera_zoom", 1.0
                ),
            },
        )

    async def _broadcast_all(
        self, runtime: SessionRuntime, event: EventEnvelope, remember: bool = False
    ) -> None:
        if remember:
            runtime.recent_events.append(event.model_dump(mode="json"))
        await asyncio.gather(
            self._send(runtime.dashboard_sockets, event),
            self._send(runtime.overlay_sockets, event),
        )

    async def _broadcast_dashboard(
        self, runtime: SessionRuntime, event: EventEnvelope, remember: bool = False
    ) -> None:
        if remember:
            runtime.recent_events.append(event.model_dump(mode="json"))
        await self._send(runtime.dashboard_sockets, event)

    @staticmethod
    async def _send(sockets: set[WebSocket], event: EventEnvelope) -> None:
        dead: list[WebSocket] = []
        payload = event.model_dump(mode="json")
        for socket in list(sockets):
            try:
                await socket.send_json(payload)
            except RuntimeError, WebSocketDisconnect:
                dead.append(socket)
        for socket in dead:
            sockets.discard(socket)

    @staticmethod
    async def _send_binary(sockets: set[WebSocket], payload: bytes) -> None:
        dead: list[WebSocket] = []
        for socket in list(sockets):
            try:
                await socket.send_bytes(payload)
            except RuntimeError, WebSocketDisconnect:
                dead.append(socket)
        for socket in dead:
            sockets.discard(socket)


live_hub = LiveHub()
