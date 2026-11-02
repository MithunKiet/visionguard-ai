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
MAX_STILL_BYTES = 8 * 1024 * 1024
MAX_STILL_WIDTH = 1920


async def _acquire():
    loop = asyncio.get_running_loop()
    limit = _LIMITS.setdefault(loop, asyncio.Semaphore(2))
    try:
        await asyncio.wait_for(limit.acquire(), timeout=0.05)
    except TimeoutError:
        raise VisionGuardException("CAMERA_PROBE_BUSY", "Connection checks are busy; retry shortly", 503)
    return limit


async def capture_still(url):
    """One JPEG still from a disposable child, bounded like a connection probe.

    Returns None when the camera produced no frame in time. The flag argument
    selects the mode; credentials still arrive only on stdin."""
    validate_rtsp_url(url)
    limit = await _acquire()
    process = None
    try:
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", __name__, "--still",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(url.encode()), PROBE_SECONDS)
        except TimeoutError:
            return None
        if process.returncode != 0 or not output or len(output) > MAX_STILL_BYTES or not output.startswith(b"\xff\xd8"):
            return None
        return output
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        limit.release()


async def probe_url(url):
    validate_rtsp_url(url)
    limit = await _acquire()
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
        if "--still" in sys.argv[1:]:
            if not ok or frame is None:
                return 1
            if frame.shape[1] > MAX_STILL_WIDTH:
                scale = MAX_STILL_WIDTH / frame.shape[1]
                frame = cv2.resize(frame, (MAX_STILL_WIDTH, max(1, int(round(frame.shape[0] * scale)))),
                                   interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                return 1
            sys.stdout.buffer.write(encoded.tobytes())
            sys.stdout.buffer.flush()
            return 0
        print(json.dumps({"reachable": bool(ok and frame is not None)}))
    finally:
        cap.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
