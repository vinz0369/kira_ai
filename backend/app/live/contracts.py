from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EventSource = Literal[
    "voice", "youtube", "simulator", "director", "llm", "tts", "overlay", "system"
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = 1
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: uuid.UUID
    type: str = Field(min_length=1, max_length=80)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: EventSource
    payload: dict[str, Any]

    @field_validator("ts")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


def make_event(
    session_id: uuid.UUID,
    event_type: str,
    source: EventSource,
    payload: dict[str, Any],
) -> EventEnvelope:
    return EventEnvelope(
        session_id=session_id,
        type=event_type,
        source=source,
        payload=payload,
    )
