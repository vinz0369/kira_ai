from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from openai import AsyncOpenAI

from app.core.config import settings
from app.voice.providers import LlmDelta, OpenAIStreamingLlm


@dataclass(frozen=True, slots=True)
class LlmModelOption:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class LlmProviderOption:
    id: str
    label: str
    description: str
    credential_required: bool
    models: tuple[LlmModelOption, ...]


def _fpt_models() -> tuple[LlmModelOption, ...]:
    return tuple(LlmModelOption(model, model) for model in settings.fpt_llm_models)


def llm_provider_options() -> tuple[LlmProviderOption, ...]:
    return (
        LlmProviderOption(
            id="fake",
            label="FakeLLM",
            description="Phản hồi deterministic cho Mock Mode; Voice Real dùng provider mặc định.",
            credential_required=False,
            models=(LlmModelOption("mock-template", "Mock template"),),
        ),
        LlmProviderOption(
            id="fpt",
            label="FPT AI Marketplace",
            description="Chat Completions streaming qua FPT AI Marketplace; API key chỉ ở backend.",
            credential_required=True,
            models=_fpt_models(),
        ),
        LlmProviderOption(
            id="openai",
            label="OpenAI",
            description="OpenAI Responses streaming hiện có.",
            credential_required=True,
            models=(LlmModelOption(settings.OPENAI_MODEL, settings.OPENAI_MODEL),),
        ),
    )


def normalize_real_llm_provider(provider: str) -> str:
    return settings.DEFAULT_REAL_LLM_PROVIDER if provider == "fake" else provider


def default_llm_model(provider: str) -> str:
    normalized = normalize_real_llm_provider(provider)
    if normalized == "fpt":
        return settings.FPT_LLM_MODEL
    if normalized == "openai":
        return settings.OPENAI_MODEL
    raise ValueError("Unsupported LLM provider")


def validate_llm_selection(provider: str, model: str) -> None:
    if provider == "fake":
        if model == "mock-template":
            return
        raise ValueError("Unsupported model for selected LLM provider")
    if provider == "fpt":
        if model in settings.fpt_llm_models:
            return
        raise ValueError("Unsupported model for selected LLM provider")
    if provider == "openai":
        if model == settings.OPENAI_MODEL:
            return
        raise ValueError("Unsupported model for selected LLM provider")
    raise ValueError("Unsupported LLM provider")


class FptMarketplaceStreamingLlm:
    """OpenAI-compatible Chat Completions adapter for FPT AI Marketplace."""

    def __init__(self, model: str | None = None) -> None:
        if not settings.FPT_API_KEY:
            raise RuntimeError("FPT AI Marketplace is not configured")
        self.model = model or settings.FPT_LLM_MODEL
        validate_llm_selection("fpt", self.model)
        self._client = AsyncOpenAI(
            api_key=settings.FPT_API_KEY,
            base_url=settings.FPT_API_BASE_URL.rstrip("/"),
            timeout=settings.FPT_LLM_TIMEOUT_SECONDS,
        )

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[LlmDelta]:
        stream = cast(
            Any,
            await self._client.chat.completions.create(
                model=self.model,
                messages=cast(Any, messages),
                max_tokens=settings.FPT_LLM_MAX_OUTPUT_TOKENS,
                temperature=0.6,
                stream=True,
                stream_options={"include_usage": True},
            ),
        )
        try:
            emitted_text = False
            async for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage:
                    yield LlmDelta(
                        "",
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                    )
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                content = choices[0].delta.content
                if content:
                    emitted_text = True
                    yield LlmDelta(content)
            if not emitted_text:
                raise RuntimeError("FPT LLM returned no text")
        finally:
            await stream.close()


def build_llm(provider: str, model: str | None = None) -> Any:
    normalized = normalize_real_llm_provider(provider)
    selected_model = model if provider != "fake" else None
    selected_model = selected_model or default_llm_model(normalized)
    validate_llm_selection(normalized, selected_model)
    if not settings.llm_provider_configured(normalized):
        raise RuntimeError(f"LLM provider {normalized} is not configured")
    if normalized == "fpt":
        return FptMarketplaceStreamingLlm(selected_model)
    if normalized == "openai":
        return OpenAIStreamingLlm(selected_model)
    raise ValueError("Unsupported LLM provider")
