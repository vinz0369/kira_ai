import warnings
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    FASTAPI_ENV: Literal["development"] | None = None
    MOCK_MODE: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    WS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8000"
    DATA_ENCRYPTION_KEY: str | None = None
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_REDIRECT_URI: str = (
        "http://localhost:8000/api/v1/youtube/oauth/callback"
    )
    YOUTUBE_SCOPES: str = "https://www.googleapis.com/auth/youtube.readonly"
    YOUTUBE_INGEST_TRANSPORT: Literal["stream", "poll"] = "stream"
    YOUTUBE_RECONNECT_MAX_SECONDS: int = 30
    YOUTUBE_CHAT_RESPONSE_MODE: Literal["addressed", "all"] = "all"
    OAUTH_STATE_TTL_SECONDS: int = 600

    # Phase 3 voice providers. Secrets are backend-only and are never included in
    # API responses, WebSocket events, traces, or URLs.
    DEEPGRAM_API_KEY: str | None = None
    DEEPGRAM_MODEL: str = "nova-3-general"
    DEEPGRAM_LANGUAGE: str = "vi"
    DEEPGRAM_ENDPOINTING_MS: int = 300
    DEEPGRAM_UTTERANCE_END_MS: int = 1000
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-5.4-mini"
    OPENAI_MAX_OUTPUT_TOKENS: int = 180
    DEFAULT_REAL_LLM_PROVIDER: Literal["fpt", "openai"] = "fpt"
    FPT_API_KEY: str | None = None
    FPT_API_BASE_URL: str = "https://mkp-api.fptcloud.com/v1"
    FPT_LLM_MODEL: str = "Saola-Small-32B"
    FPT_LLM_MODELS: str = (
        "Saola-Small-32B,Llama-3.3-70B-Instruct,DeepSeek-V4-Flash,"
        "GLM-5.2,Qwen3.6-27B,Qwen3.8-27B,gpt-oss-120b"
    )
    FPT_LLM_MAX_OUTPUT_TOKENS: int = 180
    FPT_LLM_TIMEOUT_SECONDS: int = 30
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    GOOGLE_TTS_LOCATION: str = "global"
    GOOGLE_TTS_VOICE_ID: str = "vi-VN-Chirp3-HD-Leda"
    GOOGLE_TTS_LANGUAGE: str = "vi-VN"
    GOOGLE_TTS_SAMPLE_RATE_HZ: int = 24000
    DEFAULT_REAL_TTS_PROVIDER: Literal["gtts", "google_chirp", "edge"] = "gtts"
    FREE_TTS_SAMPLE_RATE_HZ: int = 24000
    GTTS_LANGUAGE: str = "vi"
    GTTS_TLD: str = "com"
    GTTS_TIMEOUT_SECONDS: int = 15
    EDGE_TTS_EXPERIMENTAL_ENABLED: bool = False
    EDGE_TTS_VOICE_ID: str = "vi-VN-HoaiMyNeural"
    EDGE_TTS_RATE: str = "+0%"
    VOICE_MAX_AUDIO_FRAME_BYTES: int = 32_000
    VOICE_CONTEXT_TURNS: int = 6
    VOICE_RECONNECT_MAX_SECONDS: int = 20
    VOICE_STT_USD_PER_MINUTE: float | None = None
    VOICE_LLM_INPUT_USD_PER_MILLION_TOKENS: float | None = None
    VOICE_LLM_OUTPUT_USD_PER_MILLION_TOKENS: float | None = None
    FPT_LLM_INPUT_USD_PER_MILLION_TOKENS: float | None = None
    FPT_LLM_OUTPUT_USD_PER_MILLION_TOKENS: float | None = None
    VOICE_TTS_USD_PER_MILLION_CHARACTERS: float | None = None

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn

    @property
    def ws_allowed_origins(self) -> set[str]:
        return {
            origin.strip().rstrip("/")
            for origin in self.WS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        }

    @property
    def youtube_scopes(self) -> list[str]:
        return [scope for scope in self.YOUTUBE_SCOPES.split() if scope]

    @property
    def youtube_configured(self) -> bool:
        return bool(
            self.GOOGLE_CLIENT_ID
            and self.GOOGLE_CLIENT_SECRET
            and self.DATA_ENCRYPTION_KEY
        )

    @property
    def real_voice_configured(self) -> bool:
        return bool(
            self.DEEPGRAM_API_KEY
            and self.llm_provider_configured(self.DEFAULT_REAL_LLM_PROVIDER)
        )

    @property
    def fpt_llm_models(self) -> list[str]:
        return [model.strip() for model in self.FPT_LLM_MODELS.split(",") if model.strip()]

    def llm_provider_configured(self, provider: str) -> bool:
        if provider == "fpt":
            return bool(self.FPT_API_KEY)
        if provider == "openai":
            return bool(self.OPENAI_API_KEY)
        return False

    def llm_cost_rates(self, provider: str) -> tuple[float | None, float | None]:
        if provider == "fpt":
            return (
                self.FPT_LLM_INPUT_USD_PER_MILLION_TOKENS,
                self.FPT_LLM_OUTPUT_USD_PER_MILLION_TOKENS,
            )
        return (
            self.VOICE_LLM_INPUT_USD_PER_MILLION_TOKENS,
            self.VOICE_LLM_OUTPUT_USD_PER_MILLION_TOKENS,
        )

    def tts_provider_configured(self, provider: str) -> bool:
        if provider == "gtts":
            return True
        if provider == "edge":
            return self.EDGE_TTS_EXPERIMENTAL_ENABLED
        credentials = (
            Path(self.GOOGLE_APPLICATION_CREDENTIALS)
            if self.GOOGLE_APPLICATION_CREDENTIALS
            else None
        )
        return bool(provider == "google_chirp" and credentials and credentials.is_file())

    def voice_cost_rates_configured_for(
        self, tts_provider: str, llm_provider: str | None = None
    ) -> bool:
        llm_input_rate, llm_output_rate = self.llm_cost_rates(
            llm_provider or self.DEFAULT_REAL_LLM_PROVIDER
        )
        required = [
            self.VOICE_STT_USD_PER_MINUTE,
            llm_input_rate,
            llm_output_rate,
        ]
        if tts_provider == "google_chirp":
            required.append(self.VOICE_TTS_USD_PER_MILLION_CHARACTERS)
        return all(value is not None for value in required)

    @property
    def voice_cost_rates_configured(self) -> bool:
        return self.voice_cost_rates_configured_for(
            self.DEFAULT_REAL_TTS_PROVIDER, self.DEFAULT_REAL_LLM_PROVIDER
        )

    @field_validator("YOUTUBE_SCOPES")
    @classmethod
    def _only_allow_readonly_youtube_scope(cls, value: str) -> str:
        scopes = {scope for scope in value.split() if scope}
        expected = {"https://www.googleapis.com/auth/youtube.readonly"}
        if scopes != expected:
            raise ValueError("YOUTUBE_SCOPES must contain only youtube.readonly")
        return value

    @field_validator("FPT_API_BASE_URL")
    @classmethod
    def _only_allow_official_fpt_marketplace_gateway(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if normalized != "https://mkp-api.fptcloud.com/v1":
            raise ValueError(
                "FPT_API_BASE_URL must use the official FPT Marketplace v1 gateway"
            )
        return normalized

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
