from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.voice.llm import (
    FptMarketplaceStreamingLlm,
    build_llm,
    normalize_real_llm_provider,
    validate_llm_selection,
)


def test_fpt_streaming_chat_completions_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    closed = False

    class Stream:
        def __init__(self) -> None:
            self.index = 0

        def __aiter__(self) -> Stream:
            return self

        async def __anext__(self) -> object:
            chunks = [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="Xin chào "))
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[],
                    usage=SimpleNamespace(prompt_tokens=21, completion_tokens=7),
                ),
            ]
            if self.index >= len(chunks):
                raise StopAsyncIteration
            chunk = chunks[self.index]
            self.index += 1
            return chunk

        async def close(self) -> None:
            nonlocal closed
            closed = True

    class Completions:
        async def create(self, **kwargs: object) -> Stream:
            captured.update(kwargs)
            return Stream()

    def client_factory(**kwargs: object) -> object:
        captured["client"] = kwargs
        return SimpleNamespace(
            chat=SimpleNamespace(completions=Completions())
        )

    monkeypatch.setattr(settings, "FPT_API_KEY", "test-only-fpt-secret")
    monkeypatch.setattr("app.voice.llm.AsyncOpenAI", client_factory)

    async def scenario() -> None:
        adapter = FptMarketplaceStreamingLlm("Saola-Small-32B")
        deltas = [
            delta
            async for delta in adapter.stream(
                [{"role": "user", "content": "Kira ơi"}]
            )
        ]
        assert [delta.text for delta in deltas] == ["Xin chào ", ""]
        assert deltas[-1].input_tokens == 21
        assert deltas[-1].output_tokens == 7

    asyncio.run(scenario())
    assert captured["model"] == "Saola-Small-32B"
    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}
    assert captured["max_tokens"] == settings.FPT_LLM_MAX_OUTPUT_TOKENS
    assert closed is True
    client_config = captured["client"]
    assert isinstance(client_config, dict)
    assert client_config["base_url"] == "https://mkp-api.fptcloud.com/v1"


def test_fpt_cancellation_closes_provider_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_started = asyncio.Event()
    closed = False

    class BlockingStream:
        def __aiter__(self) -> BlockingStream:
            return self

        async def __anext__(self) -> object:
            stream_started.set()
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def close(self) -> None:
            nonlocal closed
            closed = True

    class Completions:
        async def create(self, **kwargs: object) -> BlockingStream:
            del kwargs
            return BlockingStream()

    monkeypatch.setattr(settings, "FPT_API_KEY", "test-only")
    monkeypatch.setattr(
        "app.voice.llm.AsyncOpenAI",
        lambda **_: SimpleNamespace(
            chat=SimpleNamespace(completions=Completions())
        ),
    )

    async def scenario() -> None:
        adapter = FptMarketplaceStreamingLlm()

        async def consume() -> None:
            async for _ in adapter.stream([]):
                pass

        task = asyncio.create_task(consume())
        await stream_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert closed is True


def test_fpt_selection_and_factory_require_backend_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert normalize_real_llm_provider("fake") == settings.DEFAULT_REAL_LLM_PROVIDER
    validate_llm_selection("fpt", "Saola-Small-32B")
    with pytest.raises(ValueError, match="Unsupported model"):
        validate_llm_selection("fpt", "not-a-real-model")
    monkeypatch.setattr(settings, "FPT_API_KEY", "")
    with pytest.raises(RuntimeError, match="not configured"):
        build_llm("fpt", "Saola-Small-32B")
