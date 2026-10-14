"""Shared, bounded inference batching. Native model execution remains serial."""
import asyncio
import time

import numpy as np
import structlog

from src.config.settings import settings
from src.health.metrics import batch_size as batch_size_metric
from src.health.metrics import (
    detection_failures_total, detection_queue_depth, frame_processing_seconds, inference_batch_seconds,
)

log = structlog.get_logger()
MAX_BATCH_SIZE = 8
MAX_WAIT_SECONDS = 0.05


class DetectionOverloaded(RuntimeError):
    pass


class BatchDetector:
    def __init__(self, detector=None, *, queue_size=None, timeout=None):
        if detector is None:
            from src.pipeline.detector import PPEDetector
            detector = PPEDetector()
        self._detector = detector
        self._queue = asyncio.Queue(maxsize=queue_size or settings.DETECTION_QUEUE_SIZE)
        self._timeout = timeout if timeout is not None else settings.DETECTION_TIMEOUT_SECONDS
        self._loop_task = None
        self._closed = False

    def start(self):
        if self._closed:
            raise RuntimeError("Detector is stopped")
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run())

    async def detect(self, frame: np.ndarray, camera_id: str = "unknown"):
        self.start()
        future = asyncio.get_running_loop().create_future()
        submitted_at = time.monotonic()
        try:
            self._queue.put_nowait((frame, future))
        except asyncio.QueueFull:
            detection_failures_total.labels(camera_id=camera_id, reason="overload").inc()
            raise DetectionOverloaded("Inference queue is full") from None
        detection_queue_depth.set(self._queue.qsize())
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            detection_failures_total.labels(camera_id=camera_id, reason="timeout").inc()
            raise
        except Exception:
            detection_failures_total.labels(camera_id=camera_id, reason="inference").inc()
            raise
        finally:
            frame_processing_seconds.labels(camera_id=camera_id).observe(time.monotonic() - submitted_at)

    async def stop(self):
        self._closed = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        while not self._queue.empty():
            _, future = self._queue.get_nowait()
            if not future.done():
                future.cancel()
        detection_queue_depth.set(0)

    async def _run(self):
        batch = []
        try:
            while True:
                batch = [await self._queue.get()]
                detection_queue_depth.set(self._queue.qsize())
                deadline = time.monotonic() + MAX_WAIT_SECONDS
                while len(batch) < MAX_BATCH_SIZE:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
                        detection_queue_depth.set(self._queue.qsize())
                    except asyncio.TimeoutError:
                        break
                # Cancelled or timed-out queued frames must not consume inference.
                batch = [item for item in batch if not item[1].done()]
                if not batch:
                    continue
                batch_size_metric.observe(len(batch))
                try:
                    with inference_batch_seconds.time():
                        results = await asyncio.to_thread(self._detector.detect_batch, [item[0] for item in batch])
                    if len(results) != len(batch):
                        raise ValueError("Detector returned the wrong number of frame results")
                except Exception as error:
                    log.error("batch_detector.inference_failed", batch_size=len(batch), error_type=type(error).__name__)
                    for _, future in batch:
                        if not future.done():
                            future.set_exception(error)
                else:
                    for (_, future), detections in zip(batch, results):
                        if not future.done():
                            future.set_result(detections)
                batch = []
        finally:
            for _, future in batch:
                if not future.done():
                    future.cancel()
