from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

PROTOCOL_VERSION = 1
MIC_DIRECTION = 0x01
TTS_DIRECTION = 0x02
HEADER_SIZE = 22


class AudioProtocolError(ValueError):
    """A binary audio frame failed validation."""


@dataclass(frozen=True, slots=True)
class AudioFrame:
    direction: int
    sequence: int
    stream_id: uuid.UUID
    pcm: bytes


def encode_audio_frame(
    direction: int, sequence: int, stream_id: uuid.UUID, pcm: bytes
) -> bytes:
    if direction not in {MIC_DIRECTION, TTS_DIRECTION}:
        raise AudioProtocolError("unsupported audio direction")
    if not 0 <= sequence <= 0xFFFFFFFF:
        raise AudioProtocolError("sequence is outside uint32 range")
    if not pcm or len(pcm) % 2:
        raise AudioProtocolError("PCM16 payload must be non-empty and even-sized")
    return struct.pack(">BBI", PROTOCOL_VERSION, direction, sequence) + stream_id.bytes + pcm


def decode_audio_frame(
    data: bytes, *, expected_direction: int, max_pcm_bytes: int
) -> AudioFrame:
    if len(data) < HEADER_SIZE + 2:
        raise AudioProtocolError("audio frame is too short")
    version, direction, sequence = struct.unpack(">BBI", data[:6])
    if version != PROTOCOL_VERSION:
        raise AudioProtocolError("unsupported audio protocol version")
    if direction != expected_direction:
        raise AudioProtocolError("unexpected audio direction")
    pcm = data[HEADER_SIZE:]
    if len(pcm) > max_pcm_bytes:
        raise AudioProtocolError("audio frame exceeds configured limit")
    if len(pcm) % 2:
        raise AudioProtocolError("PCM16 payload must be even-sized")
    return AudioFrame(direction, sequence, uuid.UUID(bytes=data[6:22]), pcm)
