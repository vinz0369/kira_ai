import hashlib
import json
import struct
import uuid
from pathlib import Path
from zipfile import ZipFile

from app.live.avatar_assets import DEFAULT_AVATAR_ASSET_ID, effective_avatar_asset_id
from app.live.hub import LiveHub

REPO_ROOT = Path(__file__).resolve().parents[3]
AVATAR_SHA256 = "7b05637cee422bf9966ab9a670060f85aa581fd672958c2ec4ea705b43aa72cd"
TWO_PHUT_HON_VMD_SHA256 = (
    "bb51072d8812832c0329f405cf9627a88757105a92b415d2648eb28844fbbf10"
)


def test_operator_vrm_is_private_and_license_metadata_is_respected() -> None:
    original = REPO_ROOT / "assets" / "Arcana.vrm"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == AVATAR_SHA256
    assert not (REPO_ROOT / "frontend" / "public" / "avatars" / "Arcana.vrm").exists()
    with original.open("rb") as stream:
        magic, glb_version, total_length = struct.unpack("<4sII", stream.read(12))
        json_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        document = json.loads(stream.read(json_length))
    assert (magic, glb_version, total_length, chunk_type) == (
        b"glTF",
        2,
        original.stat().st_size,
        b"JSON",
    )
    vrm = document["extensions"]["VRM"]
    assert vrm["specVersion"] == "0.0"
    assert vrm["meta"]["title"] == "Arcana"
    assert vrm["meta"]["author"] == "Wulong"
    assert vrm["meta"]["licenseName"] == "Redistribution_Prohibited"
    assert vrm["meta"]["commercialUssageName"] == "Disallow"


def test_only_uncustomized_kira_gets_local_default() -> None:
    assert effective_avatar_asset_id(None, "Kira") == DEFAULT_AVATAR_ASSET_ID
    assert effective_avatar_asset_id(None, "Other") is None
    assert effective_avatar_asset_id("private-custom", "Kira") == "private-custom"
    assert effective_avatar_asset_id("avatar-sample-b", "Kira") == DEFAULT_AVATAR_ASSET_ID
    assert effective_avatar_asset_id("avatar-sample-b", "Other") == "avatar-sample-b"


def test_cc0_dance_clip_is_present_in_browser_bundle() -> None:
    motion = REPO_ROOT / "frontend" / "public" / "motions" / "UAL1_Standard.glb"
    assert hashlib.sha256(motion.read_bytes()).hexdigest() == (
        "69591853d817488edaa8fd9bf8fc1d821eaeaf789f8627b3cd23b41c4ed67997"
    )
    with motion.open("rb") as stream:
        magic, version, length = struct.unpack("<4sII", stream.read(12))
        json_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        document = json.loads(stream.read(json_length))
    assert (magic, version, length, chunk_type) == (
        b"glTF", 2, motion.stat().st_size, b"JSON"
    )
    assert "Dance_Loop" in {animation["name"] for animation in document["animations"]}
    with ZipFile(REPO_ROOT / "assets" / "motions" / "Quaternius_UAL1_Standard.zip") as source:
        license_text = source.read("Universal Animation Library[Standard]/License.txt")
    assert b"CC0" in license_text


def test_operator_2_phut_hon_motion_stays_private_and_audio_is_not_bundled() -> None:
    source = (
        REPO_ROOT
        / "assets"
        / "motions"
        / "PUBG_2PhutHon_VMD_JL_v2.0"
        / "Loop version"
        / "PUBG_2PhutHon_loop_VMD_WristFix_JL_v2.0.vmd"
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == TWO_PHUT_HON_VMD_SHA256
    readme = source.parents[1] / "readme.txt"
    assert "Do not use this motion for commercial use" in readme.read_text(
        encoding="utf-8", errors="replace"
    )
    assert not (REPO_ROOT / "frontend" / "public" / "motions" / source.name).exists()
    public_files = {
        path.name.lower()
        for path in (REPO_ROOT / "frontend" / "public").rglob("*")
        if path.is_file()
    }
    assert "pubg_2phuthon.wav" not in public_files
    assert "pubg_2phuthon_loop.wav" not in public_files


def test_overlay_snapshot_receives_resolved_avatar_without_other_profile_data() -> None:
    hub = LiveHub()
    session_id = uuid.uuid4()
    runtime = hub.runtime(
        session_id,
        "active",
        False,
        "Kira",
        character_profile={"avatar_asset_id": None, "persona_description": "secret"},
    )
    payload = hub._state_snapshot(session_id, runtime).payload
    assert payload["avatar_asset_id"] == DEFAULT_AVATAR_ASSET_ID
    assert "persona_description" not in payload

    runtime.character_profile = {"avatar_asset_id": "private-custom"}
    assert (
        hub._state_snapshot(session_id, runtime).payload["avatar_asset_id"]
        == "private-custom"
    )
