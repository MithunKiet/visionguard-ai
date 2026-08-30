import asyncio
import os
import structlog
import cv2
import numpy as np
from typing import AsyncGenerator

from src.config.settings import settings
from src.health.metrics import camera_connected, frame_reader_reconnects_total

log = structlog.get_logger()

# OpenCV's FFmpeg backend has no cv2.CAP_PROP_* for RTSP transport — this env
# var (read at VideoCapture-open time) is the only way to set it. See
# settings.RTSP_TRANSPORT for why TCP is the default and when to override it.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", f"rtsp_transport;{settings.RTSP_TRANSPORT}")

RECONNECT_DELAYS = [5, 15, 60]   # seconds — retry backoff per AI Worker rule #5

# Bounds how long a single blocking OpenCV call can occupy its worker thread
# for — without this, a camera whose TCP handshake or RTSP negotiation hangs
# (firewalled IP, dead NVR) ties up that thread indefinitely. Doesn't affect
# well-behaved cameras; only kicks in when the source genuinely isn't
# responding within a reasonable window.
_OPEN_TIMEOUT_MSEC = 10_000
_READ_TIMEOUT_MSEC = 10_000


class FrameReader:

    def __init__(self, camera_id: str, rtsp_url: str, sample_fps: int = 2):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.sample_fps = sample_fps
        self._failure_count = 0
        # Actual stream properties reported by the source on the current
        # connection — None until the first successful connect. Read by
        # CameraWorker to check against the mandatory install spec.
        self.stream_fps: float | None = None
        self.stream_width: int | None = None
        self.stream_height: int | None = None

    def set_sample_fps(self, sample_fps: int) -> None:
        """Hot-applied on the next frame — used by zone config hot-swap."""
        self.sample_fps = max(1, int(sample_fps))

    async def read_frames(self) -> AsyncGenerator[np.ndarray, None]:
        while True:
            # cv2.VideoCapture(...) blocks on DNS/TCP/RTSP-handshake work —
            # potentially for seconds on an unreachable camera. This process
            # runs every CameraWorker (all cameras + heartbeat + zone_sync)
            # as tasks sharing one event loop (see main.py), so this and
            # every other blocking OpenCV call below runs in a thread via
            # asyncio.to_thread — a stalled camera then only occupies its
            # own thread, never freezing frame reading for every other
            # camera on this worker.
            cap = await asyncio.to_thread(self._open_capture)

            if not await asyncio.to_thread(cap.isOpened):
                # Always release, even on a failed open — some backends
                # (FFmpeg included) still allocate handles on a failed
                # connect attempt, and this loop retries forever, so a
                # chronically-unreachable camera would otherwise leak one
                # handle per retry (every 5-60s) for as long as the worker runs.
                await asyncio.to_thread(cap.release)
                await self._handle_failure()
                continue

            stream_fps = await asyncio.to_thread(cap.get, cv2.CAP_PROP_FPS) or 25
            self.stream_fps = stream_fps
            self.stream_width = int(await asyncio.to_thread(cap.get, cv2.CAP_PROP_FRAME_WIDTH)) or None
            self.stream_height = int(await asyncio.to_thread(cap.get, cv2.CAP_PROP_FRAME_HEIGHT)) or None
            frame_idx = 0
            self._failure_count = 0

            log.info("frame_reader.connected", camera_id=self.camera_id, rtsp=self.rtsp_url)
            camera_connected.labels(camera_id=self.camera_id).set(1)

            while True:
                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    log.warning("frame_reader.read_failed", camera_id=self.camera_id)
                    await asyncio.to_thread(cap.release)
                    await self._handle_failure()
                    break

                frame_idx += 1
                # Recomputed per frame so a hot-swapped sample_fps takes
                # effect immediately without reconnecting the stream.
                skip_frames = max(1, int(stream_fps / self.sample_fps))
                if frame_idx % skip_frames == 0:
                    yield frame

                await asyncio.sleep(0)   # yield control to event loop

    def _open_capture(self) -> cv2.VideoCapture:
        # CAP_ANY, not CAP_FFMPEG — explicitly forcing the FFmpeg backend
        # here logs a spurious "can't be used to capture by name" warning
        # on every single connect attempt in this OpenCV build; CAP_ANY lets
        # OpenCV pick FFmpeg itself (same backend actually used either way
        # for an rtsp:// URL) without the warning, and the timeout params
        # still apply.
        return cv2.VideoCapture(self.rtsp_url, cv2.CAP_ANY, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _OPEN_TIMEOUT_MSEC,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, _READ_TIMEOUT_MSEC,
        ])

    async def _handle_failure(self) -> None:
        camera_connected.labels(camera_id=self.camera_id).set(0)
        frame_reader_reconnects_total.labels(camera_id=self.camera_id).inc()
        delay = RECONNECT_DELAYS[min(self._failure_count, len(RECONNECT_DELAYS) - 1)]
        self._failure_count += 1
        log.warning("frame_reader.reconnecting", camera_id=self.camera_id,
                    attempt=self._failure_count, delay=delay)
        await asyncio.sleep(delay)
