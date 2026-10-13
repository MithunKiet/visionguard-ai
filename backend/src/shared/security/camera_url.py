"""Validate camera endpoints and remove credentials from public output."""
import ipaddress
from urllib.parse import urlsplit, urlunsplit

from src.core.settings import settings


def validate_rtsp_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname or parsed.fragment:
        raise ValueError("A valid rtsp:// or rtsps:// camera URL is required")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid camera port")
    host = parsed.hostname.lower()
    if settings.CAMERA_ALLOWED_HOSTS and host not in settings.CAMERA_ALLOWED_HOSTS:
        raise ValueError("Camera host is not in CAMERA_ALLOWED_HOSTS")
    if host in {"localhost", "metadata.google.internal"}:
        raise ValueError("Camera host is not permitted")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast):
        raise ValueError("Camera address is not permitted")
    return value


def redact_rtsp_url(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
