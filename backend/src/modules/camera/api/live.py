"""Authenticated HLS gateway. Media origins and camera credentials stay private."""
import asyncio
import re
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.shared.database.models import Camera
from src.shared.database.session import get_db
from src.shared.security.dependencies import AuthUser, get_current_user
from src.shared.security.resource_policy import require_reference

router = APIRouter(prefix="/cameras", tags=["Live video"])
_ASSET = re.compile(r"[A-Za-z0-9_-]+\.(?:m3u8|mp4|m4s|ts)\Z")
_TYPES = {"m3u8": "application/vnd.apple.mpegurl", "mp4": "video/mp4",
          "m4s": "video/mp4", "ts": "video/mp2t"}
_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def validate_playlist(content: bytes) -> None:
    """Only relative sibling assets may leave the gateway (including URI tags).

    Reject redirects, absolute URLs, nested paths and encryption/key URLs rather
    than allowing a player to send authorization to an untrusted destination.
    """
    text = content.decode("utf-8")
    if not text.startswith("#EXTM3U"):
        raise ValueError("Invalid playlist")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            uris = re.findall(r'URI="([^"]*)"', line)
            if "URI=" in line and not uris:
                raise ValueError("Invalid URI attribute")
        else:
            uris = [line]
        if any(not _ASSET.fullmatch(uri) for uri in uris):
            raise ValueError("Unsafe playlist URI")


async def fetch_asset(path: str, asset: str) -> bytes:
    # Fixed deployment-owned origin and mapping; never fetch the camera's RTSP
    # URL or a URL supplied by a browser. No ambient proxies or redirects.
    url = f"{settings.MEDIA_HLS_URL.rstrip('/')}/{path}/{asset}"
    limit = 256 * 1024 if asset.endswith(".m3u8") else 16 * 1024 * 1024
    try:
        async with asyncio.timeout(15), httpx.AsyncClient(timeout=10, trust_env=False) as client:
            async with client.stream("GET", url, headers={"Authorization": f"Bearer {settings.MEDIA_HLS_SECRET}"}) as upstream:
                if upstream.status_code != 200:
                    raise HTTPException(503, "Live stream unavailable", headers=_HEADERS)
                content = bytearray()
                async for chunk in upstream.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > limit:
                        raise ValueError("Media asset too large")
        result = bytes(content)
        if asset.endswith(".m3u8"):
            validate_playlist(result)
        return result
    except (httpx.HTTPError, TimeoutError, ValueError):
        raise HTTPException(503, "Live stream unavailable", headers=_HEADERS) from None


@router.get("/{camera_id}/live/{asset}", summary="Read an authorized live-video asset")
async def live_asset(
    camera_id: UUID, asset: str, request: Request,
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    camera = await require_reference(db, Camera, str(camera_id), user)
    path = settings.MEDIA_CAMERA_PATHS.get(str(camera_id))
    if not settings.MEDIA_HLS_URL or not path:
        raise HTTPException(404, "Live streaming is not configured for this camera", headers=_HEADERS)
    if camera.status == "Inactive" or camera.in_maintenance:
        raise HTTPException(409, "Live streaming is paused for this camera", headers=_HEADERS)
    if not _ASSET.fullmatch(asset) or request.url.query:
        raise HTTPException(400, "Invalid media asset", headers=_HEADERS)
    # Release the authorization read transaction before waiting on media IO.
    await db.rollback()
    content = await fetch_asset(path, asset)
    return Response(content, media_type=_TYPES[asset.rsplit('.', 1)[1]], headers=_HEADERS)
