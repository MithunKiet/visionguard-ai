"""One short RTSP probe per disposable child; credentials arrive only on stdin."""
import asyncio
import json
import os
import sys
import time
import weakref

from src.core.exceptions import VisionGuardException
from src.shared.security.camera_url import redact_rtsp_url, validate_rtsp_url

_LIMITS = weakref.WeakKeyDictionary()
PROBE_SECONDS = 12


async def probe_url(url):
    validate_rtsp_url(url)
    loop = asyncio.get_running_loop()
    limit = _LIMITS.setdefault(loop, asyncio.Semaphore(2))
    try:
        await asyncio.wait_for(limit.acquire(), timeout=0.05)
    except TimeoutError:
        raise VisionGuardException("CAMERA_PROBE_BUSY", "Connection checks are busy; retry shortly", 503)
    process = None
    started = time.monotonic()
    reachable = False
    try:
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", __name__,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(url.encode()), PROBE_SECONDS)
            reachable = process.returncode == 0 and json.loads(output).get("reachable") is True
        except (TimeoutError, ValueError):
            reachable = False
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        limit.release()
    return {"reachable": reachable, "latency_ms": int((time.monotonic() - started) * 1000),
            "rtsp_url": redact_rtsp_url(url), "status": "Online" if reachable else "Offline"}


def main():
    import cv2
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    url = sys.stdin.buffer.read(4097).decode()
    if len(url.encode()) > 4096:
        return 1
    validate_rtsp_url(url)
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
    try:
        ok, frame = cap.read()
        print(json.dumps({"reachable": bool(ok and frame is not None)}))
    finally:
        cap.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
