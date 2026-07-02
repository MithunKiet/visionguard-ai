"""
BatchDetector — shared across every CameraWorker in this process. Instead
of each camera calling PPEDetector.detect() on its own frame the moment it
reads one (N sequential single-image GPU calls), cameras submit frames here
and a background loop groups whatever arrived within a short window into
one batched inference call. A GPU processes a batch far more efficiently
than the same N images one at a time, so this raises how many cameras a
single worker/GPU can serve before frame processing falls behind.

Also fixes a separate waste: previously every CameraWorker instantiated
its own PPEDetector, loading a full duplicate copy of the model onto the
GPU per camera. One BatchDetector wraps a single PPEDetector shared by all.
"""
import asyncio
import time
from typing import List

import numpy as np
import structlog

from src.pipeline.detector import Detection, PPEDetector

log = structlog.get_logger()

MAX_BATCH_SIZE = 8
MAX_WAIT_SECONDS = 0.05  # collect for up to 50ms before running an under-sized batch


class BatchDetector:

    def __init__(self, detector: PPEDetector | None = None):
        self._detector = detector or PPEDetector()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop_task: asyncio.Task | None = None

    def start(self) -> None:
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run())

    async def detect(self, frame: np.ndarray) -> List[Detection]:
        self.start()
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        await self._queue.put((frame, future))
        return await future

    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            deadline = time.monotonic() + MAX_WAIT_SECONDS

            while len(batch) < MAX_BATCH_SIZE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
                except asyncio.TimeoutError:
                    break

            frames = [item[0] for item in batch]
            try:
                results = await asyncio.to_thread(self._detector.detect_batch, frames)
            except Exception as e:
                log.error("batch_detector.inference_failed", batch_size=len(frames), error=str(e))
                for _, future in batch:
                    if not future.done():
                        future.set_exception(e)
                continue

            for (_, future), detections in zip(batch, results):
                if not future.done():
                    future.set_result(detections)
