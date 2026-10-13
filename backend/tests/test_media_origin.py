"""Origin confinement and fail-closed playlist checks (no network)."""
import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from uuid import uuid4

from src.core.settings import Settings, settings
from src.modules.camera.api.live import fetch_asset, validate_playlist


@pytest.mark.parametrize("uri", ["https://evil.invalid/seg.mp4", "//evil.invalid/seg.mp4", "../other/seg.mp4",
                                  "seg.mp4?token=secret", "nested/seg.mp4", "%2e%2e/seg.mp4"])
def test_reject_unsafe_playlist_links(uri):
    for line in [uri, f'#EXT-X-MAP:URI="{uri}"', f'#EXT-X-CONTENT-STEERING:SERVER-URI="{uri}"']:
        with pytest.raises(ValueError):
            validate_playlist(f"#EXTM3U\n{line}\n".encode())


@pytest.mark.parametrize("mapping", [{str(uuid4()): "../other"}, {"not-a-uuid": "camera"},
                                      {str(uuid4()): "same", str(uuid4()): "same"}])
def test_reject_ambiguous_media_mappings(mapping):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MEDIA_CAMERA_PATHS=mapping)


@pytest.mark.parametrize("case", ["valid", "redirect", "timeout", "large", "unsafe"])
async def test_origin_limits_and_credentials(monkeypatch, case):
    monkeypatch.setattr(settings, "MEDIA_HLS_URL", "http://media.internal:8888")
    monkeypatch.setattr(settings, "MEDIA_HLS_SECRET", "test-only-origin-secret")
    requests = []
    def handler(request):
        requests.append(request)
        assert str(request.url) == "http://media.internal:8888/unique-camera/index.m3u8"
        assert request.headers["authorization"] == "Bearer test-only-origin-secret"
        assert "cookie" not in request.headers
        if case == "timeout":
            raise httpx.ReadTimeout("secret upstream details")
        if case == "redirect":
            return httpx.Response(302, headers={"location": "http://evil.invalid/secret"})
        content = {"valid": b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\nseg1.mp4\n',
                   "unsafe": b"#EXTM3U\nhttp://evil.invalid/seg.mp4\n", "large": b"x" * (256 * 1024 + 1)}[case]
        return httpx.Response(200, content=content)
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if case == "valid":
        assert (await fetch_asset("unique-camera", "index.m3u8")).startswith(b"#EXTM3U")
    else:
        with pytest.raises(HTTPException) as error:
            await fetch_asset("unique-camera", "index.m3u8")
        assert error.value.status_code == 503
        assert error.value.detail == "Live stream unavailable"
    assert len(requests) == 1
