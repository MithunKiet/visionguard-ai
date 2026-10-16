"""Continuously drain each stream into one latest-frame slot, independently of AI."""
import asyncio
from dataclasses import dataclass
import multiprocessing
import time

import numpy as np
import structlog

from src.config.ownership import lease_clock

from src.config.settings import settings
from src.health.metrics import (
    camera_connected, capture_last_received, capture_restarts, frames_discarded,
    frame_reader_reconnects_total,
)
from src.pipeline.capture_process import capture_stream

log = structlog.get_logger()
RECONNECT_DELAYS = [5, 15, 60]
POLL_SECONDS = 0.02


@dataclass(frozen=True)
class CapturedFrame:
    image: np.ndarray
    received_at: float  # Host monotonic time after decode, NOT camera exposure time.
    received_wall_time: float
    generation: int


class CaptureProcess:
    """One bounded shared slot. Never wait on a lock possibly held by a dead child."""

    def __init__(self, url, sample_fps, *, target=capture_stream, lease_deadline=None):
        context = multiprocessing.get_context("spawn")
        self.pixels = context.RawArray("B", settings.CAPTURE_MAX_FRAME_BYTES)
        self.metadata = context.RawArray("d", 8)
        self.lock = context.Lock()
        self.sample_fps = context.RawValue("d", sample_fps)
        self.lease_deadline = context.RawValue("d", lease_deadline or 0)
        args = (url, settings.RTSP_TRANSPORT, self.pixels, self.metadata, self.lock, self.sample_fps)
        if lease_deadline is not None:
            args += (self.lease_deadline,)
        self.process = context.Process(target=target, args=args, daemon=True)
        self.sequence = 0
        self.started_at = time.monotonic()
        self.process.start()

    def poll(self, generation):
        if not self.lock.acquire(False):
            return None, None, 0
        try:
            sequence, height, width, received, wall_time, fps, progress, error = self.metadata
            packet = None
            if sequence != self.sequence:
                height, width = int(height), int(width)
                image = np.frombuffer(self.pixels, dtype=np.uint8, count=height * width * 3).reshape(height, width, 3).copy()
                packet = CapturedFrame(image, received, wall_time, generation)
                self.sequence = sequence
            return packet, (progress, fps), error
        finally:
            self.lock.release()

    async def stop(self):
        # join(0) only: no capture read/release or process wait uses the shared
        # asyncio executor. A stuck camera cannot exhaust its worker threads.
        process = self.process
        if process.is_alive():
            process.terminate()
        deadline = time.monotonic() + settings.CAPTURE_STOP_TIMEOUT_SECONDS
        while process.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(POLL_SECONDS)
        if process.is_alive():
            process.kill()
            deadline = time.monotonic() + settings.CAPTURE_STOP_TIMEOUT_SECONDS
            while process.is_alive() and time.monotonic() < deadline:
                await asyncio.sleep(POLL_SECONDS)
        if process.is_alive():
            raise RuntimeError("Capture process could not be reaped; host intervention required")
        process.join(timeout=0)
        process.close()


class FrameReader:
    def __init__(self, camera_id: str, rtsp_url: str, sample_fps: int = 2, on_status=None,
                 *, process_factory=CaptureProcess):
        self.camera_id, self.rtsp_url = camera_id, rtsp_url
        self.sample_fps = max(1, int(sample_fps))
        self.on_status = on_status
        self._process_factory = process_factory
        self._capture = None
        self._lease_deadline = None
        self._task = None
        self._latest = None
        self._generation = 0
        self._connected = False
        self._offline = False
        self._failure_count = 0
        self.stream_fps = self.stream_width = self.stream_height = None

    def set_lease_deadline(self, deadline):
        self._lease_deadline = deadline
        if self._capture:
            self._capture.lease_deadline.value = deadline

    def set_sample_fps(self, sample_fps):
        self.sample_fps = max(1, int(sample_fps))
        if self._capture:
            self._capture.sample_fps.value = self.sample_fps

    def is_current(self, packet):
        return self._connected and packet.generation == self._generation

    async def start(self):
        if self._task is None:
            if self._capture is not None:
                raise RuntimeError("Previous capture process has not been reaped")
            self._task = asyncio.create_task(self._supervise())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self._retire()
        self._connected = False
        self._latest = None
        camera_connected.labels(camera_id=self.camera_id).set(0)

    async def _retire(self):
        if self._capture:
            await self._capture.stop()
            self._capture = None

    async def _status(self, connected):
        self._connected = connected
        camera_connected.labels(camera_id=self.camera_id).set(int(connected))
        if not connected:
            self._latest = None
            self.stream_fps = self.stream_width = self.stream_height = None
        if self.on_status and connected == self._offline:
            await self.on_status(not connected)
        self._offline = not connected

    async def _supervise(self):
        try:
            while True:
                if self._lease_deadline is not None and lease_clock() >= self._lease_deadline:
                    return
                self._generation += 1
                options = {"lease_deadline": self._lease_deadline} if self._lease_deadline is not None else {}
                self._capture = self._process_factory(self.rtsp_url, self.sample_fps, **options)
                progress = self._capture.started_at
                reason = "exited"
                while True:
                    if self._lease_deadline is not None and lease_clock() >= self._lease_deadline:
                        return
                    packet, health, error = self._capture.poll(self._generation)
                    if error:
                        reason = "invalid_frame"
                        break
                    if not self._capture.process.is_alive():
                        break
                    if health and health[0]:
                        progress = health[0]
                    if time.monotonic() - progress > settings.CAPTURE_STALL_SECONDS:
                        reason = "stalled"
                        break
                    if packet is not None:
                        self.stream_height, self.stream_width = packet.image.shape[:2]
                        self.stream_fps = health[1] or None
                        capture_last_received.labels(camera_id=self.camera_id).set(packet.received_wall_time)
                        if self._latest is not None:
                            frames_discarded.labels(camera_id=self.camera_id, reason="superseded").inc()
                        self._latest = packet
                        if not self._connected:
                            log.info("frame_reader.connected", camera_id=self.camera_id)
                            await self._status(True)
                        if progress - self._capture.started_at > 60:
                            self._failure_count = 0
                    await asyncio.sleep(POLL_SECONDS)
                await self._status(False)
                capture_restarts.labels(camera_id=self.camera_id, reason=reason).inc()
                frame_reader_reconnects_total.labels(camera_id=self.camera_id).inc()
                await self._retire()
                delay = RECONNECT_DELAYS[min(self._failure_count, len(RECONNECT_DELAYS) - 1)]
                self._failure_count += 1
                log.warning("frame_reader.reconnecting", camera_id=self.camera_id, reason=reason, delay=delay)
                await asyncio.sleep(delay)
        finally:
            self._connected = False
            self._latest = None
            camera_connected.labels(camera_id=self.camera_id).set(0)
            await self._retire()

    async def read_frames(self):
        await self.start()
        try:
            while True:
                if self._task.done():
                    await self._task
                    return
                packet, self._latest = self._latest, None
                if packet is not None:
                    yield packet
                else:
                    await asyncio.sleep(POLL_SECONDS)
        finally:
            await self.stop()
