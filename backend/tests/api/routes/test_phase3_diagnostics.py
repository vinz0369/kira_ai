from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_phase3_diagnostics_is_authenticated(
    client: TestClient,
) -> None:
    response = client.get(f"{settings.API_V1_STR}/diagnostics/phase3")
    assert response.status_code == 401


def test_phase3_diagnostics_returns_safe_preflight_only(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credentials = tmp_path / "google.json"
    credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings, "DEEPGRAM_API_KEY", "diagnostic-only-secret")
    monkeypatch.setattr(settings, "FPT_API_KEY", "diagnostic-only-fpt-secret")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "diagnostic-only-secret")
    monkeypatch.setattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", str(credentials))

    response = client.get(
        f"{settings.API_V1_STR}/diagnostics/phase3",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["measurement_scope"] == "PREFLIGHT_ONLY"
    assert body["real_voice_ready"] is True
    assert body["raw_audio_persisted"] is False
    assert body["secrets_exposed_to_frontend"] is False
    assert body["gtts"]["configured"] is True
    assert body["fpt_llm"]["configured"] is True
    assert body["fpt_llm"]["model"] == settings.FPT_LLM_MODEL
    assert body["gtts"]["status"] == "ready"
    assert body["edge_tts"]["status"] in {"ready", "disabled"}
    serialized = response.text
    assert "diagnostic-only-secret" not in serialized
    assert "diagnostic-only-fpt-secret" not in serialized
    assert str(credentials) not in serialized


def test_invalid_google_credential_path_is_not_ready(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(settings, "FPT_API_KEY", "configured")
    monkeypatch.setattr(
        settings, "GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json")
    )

    response = client.get(
        f"{settings.API_V1_STR}/diagnostics/phase3",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["google_tts"]["status"] == "invalid"
    # The default FPT + credential-free gTTS path remains available even when
    # the optional Google Cloud provider is invalid.
    assert response.json()["real_voice_ready"] is True
