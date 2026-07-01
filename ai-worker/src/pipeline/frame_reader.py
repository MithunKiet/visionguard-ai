import asyncio
import structlog
import cv2
import numpy as np
from typing import AsyncGenerator

log = structlog.get_logger()

RECONNECT_DELAYS = [5, 15, 60]   # seconds — retry backoff per AI Worker rule #5


class FrameReader:

    def __init__(self, camera_id: str, rtsp_url: str, sample_fps: int = 2):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.sample_fps = sample_fps
        self._failure_count = 0

    async def read_frames(self) -> AsyncGenerator[np.ndarray, None]:
        while True:
            cap = cv2.VideoCapture(self.rtsp_url)

            if not cap.isOpened():
                await self._handle_failure()
                continue

            stream_fps = cap.get(cv2.CAP_PROP_FPS) or 25
            skip_frames = max(1, int(stream_fps / self.sample_fps))
            frame_idx = 0
            self._failure_count = 0

            log.info("frame_reader.connected", camera_id=self.camera_id, rtsp=self.rtsp_url)

            while True:
                ret, frame = cap.read()
                if not ret:
                    log.warning("frame_reader.read_failed", camera_id=self.camera_id)
                    cap.release()
                    await self._handle_failure()
                    break

                frame_idx += 1
                if frame_idx % skip_frames == 0:
                    yield frame

                await asyncio.sleep(0)   # yield control to event loop

    async def _handle_failure(self) -> None:
        delay = RECONNECT_DELAYS[min(self._failure_count, len(RECONNECT_DELAYS) - 1)]
        self._failure_count += 1
        log.warning("frame_reader.reconnecting", camera_id=self.camera_id,
                    attempt=self._failure_count, delay=delay)
        await asyncio.sleep(delay)
