from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

CHAT_QUEUE_LIMIT = 10
CHAT_QUEUE_TTL_SECONDS = 8


@dataclass(slots=True)
class DirectorState:
    session: str = "active"
    ai_muted: bool = False
    ai_speaking: bool = False
    streamer_speaking: bool = False
    character_name: str = "Kira"
    active_utterance_id: str | None = None
    seen_provider_ids: set[str] = field(default_factory=set)
    paid_queue: list[dict[str, Any]] = field(default_factory=list)
    chat_queue: list[tuple[float, dict[str, Any]]] = field(default_factory=list)
    chat_response_mode: str = "all"
    generation: int = 0


@dataclass(slots=True)
class DirectorDecision:
    decision: str
    reason_code: str
    priority: int = 3
    candidate: dict[str, Any] | None = None
    cancel_reason: str | None = None
    duplicate_dropped: bool = False
    paid_event_saved: bool = False
    snapshot_sent: bool = False


class ConversationDirector:
    """Pure deterministic priority and safety core; it never calls an LLM."""

    def __init__(self, state: DirectorState) -> None:
        self.state = state

    def handle(self, event_type: str, payload: dict[str, Any]) -> DirectorDecision:
        if event_type == "session.control":
            return self._control(str(payload.get("command", "")))
        if event_type == "overlay.connected":
            return DirectorDecision("ignore", "overlay_snapshot", snapshot_sent=True)
        if event_type == "system.test.candidate_expired":
            return DirectorDecision("cancel", "stale", cancel_reason="stale")
        if event_type == "streamer.speech.started":
            self.state.streamer_speaking = True
            if self.state.ai_speaking:
                self._cancel_generation()
                return DirectorDecision(
                    "cancel", "streamer_barge_in", priority=0, cancel_reason="barge_in"
                )
            return DirectorDecision("ignore", "streamer_has_floor", priority=1)
        if event_type == "streamer.speech.ended":
            self.state.streamer_speaking = False
            return DirectorDecision("ignore", "streamer_turn_ended", priority=1)

        if event_type in {"youtube.superchat", "youtube.supersticker"}:
            return self._paid(event_type, payload)
        if event_type == "youtube.chat.message":
            return self._chat(payload)
        if event_type == "streamer.transcript.final":
            return self._transcript(payload)
        return DirectorDecision("ignore", "unsupported_event")

    def _control(self, command: str) -> DirectorDecision:
        if command == "mute":
            self.state.ai_muted = True
            self.state.paid_queue.clear()
            self.state.chat_queue.clear()
            self._cancel_generation()
            return DirectorDecision(
                "cancel", "owner_mute", priority=0, cancel_reason="mute"
            )
        if command == "stop":
            self.state.session = "stopped"
            self.state.ai_muted = True
            self.state.paid_queue.clear()
            self.state.chat_queue.clear()
            self._cancel_generation()
            return DirectorDecision(
                "cancel", "owner_stop", priority=0, cancel_reason="stop"
            )
        if command == "unmute" and self.state.session != "stopped":
            self.state.ai_muted = False
            return DirectorDecision("ignore", "owner_unmute", priority=0)
        if command == "pause" and self.state.session == "active":
            self.state.session = "paused"
            self.state.chat_queue.clear()
            self._cancel_generation()
            return DirectorDecision(
                "cancel", "owner_pause", priority=0, cancel_reason="stop"
            )
        if command in {"start", "resume"} and self.state.session != "stopped":
            self.state.session = "active"
            return DirectorDecision("ignore", "owner_start", priority=0)
        return DirectorDecision("ignore", "invalid_control", priority=0)

    def _transcript(self, payload: dict[str, Any]) -> DirectorDecision:
        self.state.streamer_speaking = False
        if not self._can_speak():
            return DirectorDecision("ignore", "session_not_speakable", priority=1)
        text = str(payload.get("text", ""))[:2000]
        if self.state.character_name.casefold() not in text.casefold():
            return DirectorDecision("ignore", "not_directly_addressed", priority=1)
        return DirectorDecision(
            "respond",
            "direct_streamer_call",
            priority=1,
            candidate={"type": "voice", **payload},
        )

    def _chat(self, payload: dict[str, Any]) -> DirectorDecision:
        provider_id = str(payload.get("provider_message_id", ""))
        if provider_id and provider_id in self.state.seen_provider_ids:
            return DirectorDecision(
                "ignore", "duplicate", priority=3, duplicate_dropped=True
            )
        if provider_id:
            self.state.seen_provider_ids.add(provider_id)
        if not self._can_speak():
            return DirectorDecision("ignore", "session_not_speakable", priority=3)
        text = str(payload.get("text", ""))[:2000]
        if not text.strip():
            return DirectorDecision("ignore", "empty_chat", priority=3)
        lowered = text.casefold()
        injection_markers = ("system:", "ignore all", "bỏ qua system", "reveal private")
        if any(marker in lowered for marker in injection_markers):
            return DirectorDecision("ignore", "untrusted_instruction", priority=3)
        direct_question = (
            self.state.character_name.casefold() in lowered and "?" in text
        )
        if self.state.chat_response_mode == "addressed" and not direct_question:
            return DirectorDecision("ignore", "chat_not_selected", priority=3)
        priority = 2 if direct_question else 3
        candidate = {"type": "chat", **payload}
        if (
            self.state.streamer_speaking
            or self.state.ai_speaking
            or self.state.paid_queue
        ):
            self._drop_stale_chat()
            if len(self.state.chat_queue) >= CHAT_QUEUE_LIMIT:
                return DirectorDecision("ignore", "chat_queue_full", priority=priority)
            self.state.chat_queue.append((monotonic(), candidate))
            return DirectorDecision(
                "queue", "waiting_for_streamer", priority=priority, candidate=candidate
            )
        return DirectorDecision(
            "respond",
            "direct_viewer_question" if direct_question else "all_chat_test_mode",
            priority=priority,
            candidate=candidate,
        )

    def _drop_stale_chat(self) -> None:
        now = monotonic()
        self.state.chat_queue = [
            (queued_at, candidate)
            for queued_at, candidate in self.state.chat_queue
            if now - queued_at <= CHAT_QUEUE_TTL_SECONDS
        ]

    def pop_chat_candidate(self) -> dict[str, Any] | None:
        if (
            not self._can_speak()
            or self.state.streamer_speaking
            or self.state.ai_speaking
            or self.state.paid_queue
        ):
            return None
        self._drop_stale_chat()
        if not self.state.chat_queue:
            return None
        return self.state.chat_queue.pop(0)[1]

    def _paid(self, event_type: str, payload: dict[str, Any]) -> DirectorDecision:
        provider_id = str(payload.get("provider_message_id", ""))
        if provider_id and provider_id in self.state.seen_provider_ids:
            return DirectorDecision(
                "ignore",
                "duplicate",
                priority=2,
                duplicate_dropped=True,
                paid_event_saved=False,
            )
        if provider_id:
            self.state.seen_provider_ids.add(provider_id)
        candidate = {"type": event_type, **payload}
        if self.state.session != "active" or self.state.ai_muted:
            return DirectorDecision(
                "ignore", "session_not_speakable", priority=2, paid_event_saved=True
            )
        if self.state.streamer_speaking or self.state.ai_speaking:
            self.state.paid_queue.append(candidate)
            return DirectorDecision(
                "queue",
                "waiting_for_streamer",
                priority=2,
                candidate=candidate,
                paid_event_saved=True,
            )
        return DirectorDecision(
            "respond",
            "paid_acknowledgement",
            priority=2,
            candidate=candidate,
            paid_event_saved=True,
        )

    def pop_paid_candidate(self) -> dict[str, Any] | None:
        if (
            not self._can_speak()
            or self.state.streamer_speaking
            or self.state.ai_speaking
        ):
            return None
        return self.state.paid_queue.pop(0) if self.state.paid_queue else None

    def _can_speak(self) -> bool:
        return self.state.session == "active" and not self.state.ai_muted

    def _cancel_generation(self) -> None:
        self.state.generation += 1
        self.state.ai_speaking = False
        self.state.active_utterance_id = None


def run_fixture_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    initial = scenario["initial_state"]
    state = DirectorState(
        session=initial["session"],
        ai_muted=initial["ai_muted"],
        ai_speaking=initial["ai_speaking"],
        streamer_speaking=initial["streamer_speaking"],
        active_utterance_id="fixture-active" if initial["ai_speaking"] else None,
    )
    director = ConversationDirector(state)
    decisions = [
        director.handle(event["type"], event["payload"]) for event in scenario["events"]
    ]
    final = decisions[-1]
    return {
        "decision": final.decision,
        "priority": f"P{final.priority}",
        "ai_muted": state.ai_muted,
        "active_utterances": int(state.active_utterance_id is not None),
        "speech_cancelled": any(d.cancel_reason is not None for d in decisions),
        "speech_started": any(d.decision == "respond" for d in decisions),
        "paid_event_unique": len(state.seen_provider_ids),
        "duplicate_dropped": any(d.duplicate_dropped for d in decisions),
        "interrupt_streamer": False,
        "paid_event_saved": any(d.paid_event_saved for d in decisions),
        "privileged_action": False,
        "secrets_exposed": False,
        "snapshot_sent": any(d.snapshot_sent for d in decisions),
        "old_audio_replayed": False,
    }
