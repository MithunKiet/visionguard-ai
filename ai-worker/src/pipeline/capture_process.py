"""OpenCV runs only in a disposable child; no model or network publisher here."""
import math
import ctypes
import multiprocessing
import os
import signal
import sys
import time
import threading

import cv2
import numpy as np

from src.config.ownership import lease_clock


def open_capture(url, transport):
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}"
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,
        cv2.CAP_PROP_N_THREADS, 1,
    ])


def capture_stream(url, transport, pixels, metadata, lock, sample_fps, lease_deadline=None, *, opener=open_capture):
    if lease_deadline is not None:
        # Independent of the parent's asyncio loop and of blocking native reads.
        # Full host suspension/kernel failure still requires infrastructure fencing.
        def expire():
            while lease_clock() < lease_deadline.value:
                time.sleep(0.05)
            os._exit(0)
        if lease_clock() >= lease_deadline.value:
            return
        threading.Thread(target=expire, daemon=True).start()
    if sys.platform == "linux":
        # A worker crash must not leave a camera connection running indefinitely.
        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise RuntimeError("Cannot bind capture lifetime to parent")
        parent = multiprocessing.parent_process()
        if parent is None or os.getppid() != parent.pid:
            return
    # Native FFmpeg diagnostics can contain camera credentials. Report typed
    # health failures through the supervisor, never native stream URLs.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    cap = None
    try:
        cv2.setNumThreads(1)
        cap = opener(url, transport)
        if not cap.isOpened():
            return
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if math.isfinite(fps) and fps > 0 else 0
        shared = np.frombuffer(pixels, dtype=np.uint8)
        next_sample = 0.0
        while True:
            ok, frame = cap.read()
            received_at, wall_time = time.monotonic(), time.time()
            if not ok:
                return
            if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3
                    or frame.shape[2] != 3 or frame.size == 0 or frame.nbytes > len(shared)):
                if lock.acquire(False):
                    try:
                        metadata[7] = 1  # Explicit invalid/oversized frame; never resize evidence silently.
                    finally:
                        lock.release()
                return
            if not lock.acquire(False):
                continue  # Never wait for a consumer, even during its frame copy.
            try:
                metadata[6] = received_at
                if received_at < next_sample:
                    continue
                next_sample = received_at + 1 / max(1, sample_fps.value)
                shared[:frame.size] = frame.reshape(-1)
                metadata[1:6] = (frame.shape[0], frame.shape[1], received_at, wall_time, fps)
                metadata[0] += 1  # Commit only after pixels and timestamps are copied.
            finally:
                lock.release()
    finally:
        if cap is not None:
            cap.release()  # A hung release is killed by the parent watchdog too.
