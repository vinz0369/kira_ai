"""Serve operator-supplied non-redistributable VRM only to local authenticated previews."""

import ipaddress
import uuid
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.live.security import overlay_key_matches
from app.models import LiveSession

router = APIRouter(prefix="/avatar-assets", tags=["avatar-assets"])
ARCANA_FILE = Path(__file__).resolve().parents[4] / "assets" / "Arcana.vrm"
TWO_PHUT_HON_VMD_FILE = (
    Path(__file__).resolve().parents[4]
    / "assets"
    / "motions"
    / "PUBG_2PhutHon_VMD_JL_v2.0"
    / "Loop version"
    / "PUBG_2PhutHon_loop_VMD_WristFix_JL_v2.0.vmd"
)


def _local_asset(request: Request, asset: Path, media_type: str) -> FileResponse:
    host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    if settings.FASTAPI_ENV != "development" or not local:
        raise HTTPException(status_code=403, detail="Local avatar preview only")
    if not asset.is_file():
        raise HTTPException(status_code=404, detail="Local operator asset not found")
    return FileResponse(
        asset,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/arcana/studio")
def studio_avatar(request: Request, current_user: CurrentUser) -> FileResponse:
    del current_user
    return _local_asset(request, ARCANA_FILE, "model/gltf-binary")


@router.get("/arcana/overlay/{session_id}")
def overlay_avatar(
    request: Request,
    session_id: uuid.UUID,
    db: SessionDep,
    x_overlay_key: str = Header(default=""),
) -> FileResponse:
    live_session = db.get(LiveSession, session_id)
    if (
        not live_session
        or live_session.status == "stopped"
        or not overlay_key_matches(x_overlay_key, live_session.overlay_key_hash)
    ):
        raise HTTPException(status_code=403, detail="Invalid overlay access")
    return _local_asset(request, ARCANA_FILE, "model/gltf-binary")


@router.get("/motions/2-phut-hon/studio")
def studio_2_phut_hon_motion(
    request: Request, current_user: CurrentUser
) -> FileResponse:
    """Development-only VMD supplied by the operator; never expose its audio."""
    del current_user
    return _local_asset(request, TWO_PHUT_HON_VMD_FILE, "application/octet-stream")


@router.get("/motions/2-phut-hon/overlay/{session_id}")
def overlay_2_phut_hon_motion(
    request: Request,
    session_id: uuid.UUID,
    db: SessionDep,
    x_overlay_key: str = Header(default=""),
) -> FileResponse:
    live_session = db.get(LiveSession, session_id)
    if (
        not live_session
        or live_session.status == "stopped"
        or not overlay_key_matches(x_overlay_key, live_session.overlay_key_hash)
    ):
        raise HTTPException(status_code=403, detail="Invalid overlay access")
    return _local_asset(request, TWO_PHUT_HON_VMD_FILE, "application/octet-stream")
