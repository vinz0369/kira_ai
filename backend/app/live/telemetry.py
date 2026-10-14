from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


def monotonic_ns() -> int:
    return time.perf_counter_ns()


def elapsed_ms(start_ns: int, end_ns: int | None = None) -> float:
    end = end_ns if end_ns is not None else monotonic_ns()
    return round((end - start_ns) / 1_000_000, 3)


@dataclass(slots=True)
class UtteranceTrace:
    trace_id: str
    utterance_id: str
    input_event_type: str
    event_received_ns: int
    voice_turn_end_ns: int | None = None
    measurement_scope: str = "MOCK_SIMULATED_LOCAL"
    audio_sent_ns: int | None = None
    cancel_requested_ns: int | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "utterance_id": self.utterance_id,
            "input_event_type": self.input_event_type,
            "measurement_scope": self.measurement_scope,
            "metrics_ms": dict(self.metrics),
        }


class DevelopmentTelemetry:
    """In-memory, content-free timings with an explicit measurement scope."""

    def __init__(self, scope: str = "MOCK_SIMULATED_LOCAL") -> None:
        self.scope = scope
        self._series: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
        self._traces: dict[str, UtteranceTrace] = {}
        self._recent_ids: deque[str] = deque(maxlen=20)

    def record(self, metric: str, value_ms: float) -> float:
        value = round(max(0.0, value_ms), 3)
        self._series[metric].append(value)
        return value

    def start_utterance(
        self,
        *,
        trace_id: str,
        utterance_id: str,
        input_event_type: str,
        event_received_ns: int,
        voice_turn_end_ns: int | None = None,
        stt_final_ms: float | None = None,
        event_to_decision_ms: float,
        llm_ms: float | None,
        tts_first_audio_ms: float | None,
    ) -> UtteranceTrace:
        trace = UtteranceTrace(
            trace_id=trace_id,
            utterance_id=utterance_id,
            input_event_type=input_event_type,
            event_received_ns=event_received_ns,
            voice_turn_end_ns=voice_turn_end_ns,
            measurement_scope=self.scope,
        )
        measurements = {
            "event_to_decision_ms": event_to_decision_ms,
            "stt_final_ms": stt_final_ms,
            "llm_ms": llm_ms,
            "tts_first_audio_ms": tts_first_audio_ms,
        }
        for metric, value in measurements.items():
            if value is None:
                continue
            trace.metrics[metric] = (
                round(max(0.0, value), 3)
                if metric == "event_to_decision_ms"
                else self.record(metric, value)
            )
        self._traces[utterance_id] = trace
        self._recent_ids.append(utterance_id)
        return trace

    def mark_audio_sent(self, utterance_id: str) -> None:
        trace = self._traces.get(utterance_id)
        if trace and trace.audio_sent_ns is None:
            trace.audio_sent_ns = monotonic_ns()

    def mark_playback_started(
        self, utterance_id: str, payload: dict[str, Any]
    ) -> UtteranceTrace | None:
        trace = self._traces.get(utterance_id)
        if not trace:
            return None
        now = monotonic_ns()
        if trace.audio_sent_ns is not None:
            value = self._trace_measurement(
                trace,
                "overlay_playback_ack_ms",
                elapsed_ms(trace.audio_sent_ns, now),
            )
            trace.metrics["overlay_playback_ack_ms"] = value
        value = self._trace_measurement(
            trace,
            "event_to_first_playback_ack_ms",
            elapsed_ms(trace.event_received_ns, now),
        )
        trace.metrics["event_to_first_playback_ack_ms"] = value
        if trace.voice_turn_end_ns is not None:
            value = self._trace_measurement(
                trace,
                "voice_end_to_first_playback_ack_ms",
                elapsed_ms(trace.voice_turn_end_ns, now),
            )
            trace.metrics["voice_end_to_first_playback_ack_ms"] = value
        self._record_client_metric(trace, payload, "client_first_chunk_to_playback_ms")
        return trace

    def mark_cancel_requested(self, utterance_id: str) -> None:
        trace = self._traces.get(utterance_id)
        if trace:
            trace.cancel_requested_ns = monotonic_ns()

    def mark_cancel_dispatched(self, utterance_id: str) -> None:
        trace = self._traces.get(utterance_id)
        if trace and trace.cancel_requested_ns is not None:
            value = self.record(
                "cancel_dispatch_ms", elapsed_ms(trace.cancel_requested_ns)
            )
            trace.metrics["cancel_dispatch_ms"] = value

    def mark_playback_cancelled(
        self, utterance_id: str, payload: dict[str, Any]
    ) -> UtteranceTrace | None:
        trace = self._traces.get(utterance_id)
        if not trace:
            return None
        if trace.cancel_requested_ns is not None:
            value = self.record(
                "cancel_request_to_ack_ms", elapsed_ms(trace.cancel_requested_ns)
            )
            trace.metrics["cancel_request_to_ack_ms"] = value
        self._record_client_metric(trace, payload, "client_audio_stop_ms")
        return trace

    def summary(self) -> dict[str, Any]:
        return {
            "measurement_scope": self.scope,
            "metrics": {
                name: self._summarize(values)
                for name, values in sorted(self._series.items())
            },
            "recent_traces": [
                self._traces[utterance_id].public()
                for utterance_id in reversed(self._recent_ids)
                if utterance_id in self._traces
            ],
        }

    def trace(self, utterance_id: str) -> UtteranceTrace | None:
        return self._traces.get(utterance_id)

    def _record_client_metric(
        self, trace: UtteranceTrace, payload: dict[str, Any], metric: str
    ) -> None:
        raw = payload.get(metric)
        if not isinstance(raw, int | float) or isinstance(raw, bool):
            return
        value = self._trace_measurement(trace, metric, float(raw))
        trace.metrics[metric] = value

    def _trace_measurement(
        self, trace: UtteranceTrace, metric: str, value_ms: float
    ) -> float:
        value = round(max(0.0, value_ms), 3)
        if trace.measurement_scope != "DEGRADED_FALLBACK_LOCAL":
            self._series[metric].append(value)
        return value

    @staticmethod
    def _summarize(values: deque[float]) -> dict[str, float | int]:
        ordered = sorted(values)

        def percentile(fraction: float) -> float:
            index = max(0, math.ceil(len(ordered) * fraction) - 1)
            return ordered[index]

        return {
            "samples": len(ordered),
            "latest_ms": ordered[-1] if len(ordered) == 1 else values[-1],
            "p50_ms": percentile(0.50),
            "p95_ms": percentile(0.95),
        }


def new_trace_id() -> str:
    return str(uuid.uuid4())
