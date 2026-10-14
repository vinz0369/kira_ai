from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.api.routes.test_live_character import create_character, create_session


def test_private_arcana_requires_auth_and_local_client(
    normal_user_token_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "FASTAPI_ENV", "development")
    path = f"{settings.API_V1_STR}/avatar-assets/arcana/studio"
    with TestClient(app, client=("127.0.0.1", 43000)) as local:
        assert local.get(path).status_code == 401
        response = local.get(path, headers=normal_user_token_headers)
        assert response.status_code == 200
        assert response.content[:4] == b"glTF"
        assert response.headers["cache-control"] == "private, no-store"
        motion_path = f"{settings.API_V1_STR}/avatar-assets/motions/2-phut-hon/studio"
        assert local.get(motion_path).status_code == 401
        motion = local.get(motion_path, headers=normal_user_token_headers)
        assert motion.status_code == 200
        assert motion.content.startswith(b"Vocaloid Motion Data")
        assert motion.headers["cache-control"] == "private, no-store"
    with TestClient(app, client=("192.0.2.1", 43000)) as remote:
        assert remote.get(path, headers=normal_user_token_headers).status_code == 403
        assert (
            remote.get(motion_path, headers=normal_user_token_headers).status_code
            == 403
        )


def test_overlay_asset_key_and_avatar_motion_control(
    normal_user_token_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "FASTAPI_ENV", "development")
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        character = create_character(client, normal_user_token_headers)
        live = create_session(client, normal_user_token_headers, character["id"])
        session_id = live["id"]
        key = parse_qs(urlparse(live["overlay_url"]).query)["key"][0]
        path = f"{settings.API_V1_STR}/avatar-assets/arcana/overlay/{session_id}"
        assert client.get(path).status_code == 403
        assert client.get(path, headers={"X-Overlay-Key": "wrong"}).status_code == 403
        assert client.get(path, headers={"X-Overlay-Key": key}).status_code == 200
        dance_path = (
            f"{settings.API_V1_STR}/avatar-assets/motions/2-phut-hon/overlay/"
            f"{session_id}"
        )
        assert client.get(dance_path).status_code == 403
        assert client.get(
            dance_path, headers={"X-Overlay-Key": "wrong"}
        ).status_code == 403
        dance = client.get(dance_path, headers={"X-Overlay-Key": key})
        assert dance.status_code == 200
        assert dance.content.startswith(b"Vocaloid Motion Data")
        assert dance.headers["cache-control"] == "private, no-store"
        motion_path = f"{settings.API_V1_STR}/sessions/{session_id}/avatar-motion"
        assert client.post(
            motion_path,
            headers=normal_user_token_headers,
            json={"motion": "dance", "duration_seconds": 150},
        ).status_code == 409
        assert client.post(
            f"{settings.API_V1_STR}/sessions/{session_id}/control",
            headers=normal_user_token_headers,
            json={"command": "start"},
        ).status_code == 200
        too_short = client.post(
            motion_path,
            headers=normal_user_token_headers,
            json={"motion": "dance", "duration_seconds": 120},
        )
        assert too_short.status_code == 422
        motion = client.post(
            motion_path,
            headers=normal_user_token_headers,
            json={"motion": "dance", "duration_seconds": 150},
        )
        assert motion.status_code == 200
        assert motion.json() == {"motion": "dance", "duration_seconds": 150}
        greeting = client.post(
            motion_path,
            headers=normal_user_token_headers,
            json={"motion": "greet", "duration_seconds": 4},
        )
        assert greeting.status_code == 200
        assert greeting.json()["motion"] == "greet"
        assert client.post(motion_path, json={"motion": "idle"}).status_code == 401
        assert client.post(
            f"{settings.API_V1_STR}/sessions/{session_id}/control",
            headers=normal_user_token_headers,
            json={"command": "stop"},
        ).status_code == 200
