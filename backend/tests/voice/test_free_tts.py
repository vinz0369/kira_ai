from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.config import settings
from app.voice.tts import (
    EdgeExperimentalTts,
    GttsVietnameseTts,
    build_tts,
    default_voice_id,
    normalize_real_tts_provider,
    validate_tts_selection,
)


def test_gtts_stream_uses_pcm_contract_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        GttsVietnameseTts,
        "_synthesize",
        staticmethod(lambda text: b"mp3:" + text.encode()),
    )
    monkeypatch.setattr(
        "app.voice.tts._pcm_chunks",
        lambda audio, sample_rate: [
            b"\x01\x00" * 20,
            b"\x02\x00" * 20,
        ],
    )

    async def scenario() -> None:
        adapter = GttsVietnameseTts()
        chunks = [chunk async for chunk in adapter.stream("Xin chào", "utterance")]
        assert chunks == [b"\x01\x00" * 20, b"\x02\x00" * 20]
        assert adapter.sample_rate_hz == 24_000

    asyncio.run(scenario())


def test_edge_tts_is_explicitly_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EDGE_TTS_EXPERIMENTAL_ENABLED", False)
    with pytest.raises(RuntimeError, match="disabled"):
        EdgeExperimentalTts()


def test_edge_stream_preserves_pcm_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCommunicate:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "audio", "data": b"mp3-a"}
            yield {"type": "WordBoundary", "text": "Xin"}
            yield {"type": "audio", "data": b"mp3-b"}

    monkeypatch.setattr(settings, "EDGE_TTS_EXPERIMENTAL_ENABLED", True)
    monkeypatch.setattr("app.voice.tts.edge_tts.Communicate", FakeCommunicate)
    monkeypatch.setattr(
        "app.voice.tts._pcm_chunks",
        lambda audio, sample_rate: [b"\x03\x00" * 30],
    )

    async def scenario() -> None:
        adapter = EdgeExperimentalTts("vi-VN-NamMinhNeural")
        chunks = [chunk async for chunk in adapter.stream("Xin chào", "utterance")]
        assert chunks == [b"\x03\x00" * 30]

    asyncio.run(scenario())


def test_provider_selection_validation_and_mock_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert normalize_real_tts_provider("fake") == "gtts"
    assert default_voice_id("gtts") == "vi"
    validate_tts_selection("edge", "vi-VN-HoaiMyNeural")
    with pytest.raises(ValueError, match="Unsupported voice"):
        validate_tts_selection("gtts", "en")
    monkeypatch.setattr(settings, "DEFAULT_REAL_TTS_PROVIDER", "gtts")
    assert isinstance(build_tts("fake", "mock-sine"), GttsVietnameseTts)
