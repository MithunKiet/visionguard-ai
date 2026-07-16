"""
PersonTracker — per-camera, frame-to-frame identity for detected people via
IOU (bounding-box overlap) matching.

Deliberately not Ultralytics' built-in tracker (model.track()): BatchDetector
groups frames from multiple unrelated camera streams into one GPU inference
call for throughput (see batch_detector.py), and a stream-stateful tracker
mixed across unrelated streams in one batch risks track_id bleed between
cameras. This tracker instead runs per-camera, after batched detection
returns, matching only that camera's own frame-to-frame detections — the
same technique as the classic IOU Tracker (Bochinski et al., 2017), which is
sufficient here since frame_sample_fps is low (2fps by default) and cameras
are fixed-position (no fast, unpredictable motion between sampled frames).
"""
import time
from dataclasses import dataclass


def iou(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    intersection = iw * ih
    if intersection == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return intersection / (area_a + area_b - intersection)


def containment_ratio(inner: tuple, outer: tuple) -> float:
    """Fraction of `inner`'s own area that overlaps `outer` — used to match
    a small violation-region box (e.g. a head-only "no_helmet" box) against
    the full person box it belongs to, where plain IOU would score low even
    for a correct match simply because the two boxes are very different sizes."""
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    cx1, cy1 = max(ix1, ox1), max(iy1, oy1)
    cx2, cy2 = min(ix2, ox2), min(iy2, oy2)
    cw, ch = max(0, cx2 - cx1), max(0, cy2 - cy1)
    intersection = cw * ch
    inner_area = max(1, (ix2 - ix1) * (iy2 - iy1))
    return intersection / inner_area


@dataclass
class _Track:
    track_id: int
    bbox: tuple
    last_seen: float


class PersonTracker:
    """Assigns a stable integer track_id to each "person" box across
    consecutive frames of ONE camera. Not a full MOT algorithm (no motion
    prediction/Kalman filter) — greedy IOU matching frame-to-frame, adequate
    at low sample rates on a fixed camera; see module docstring for why this
    over Ultralytics' tracker."""

    IOU_MATCH_THRESHOLD = 0.3
    # A handful of missed/skipped frames' worth of absence at the default
    # 2fps sample rate before a track is considered gone, not just briefly
    # occluded — tune alongside frame_sample_fps if that default changes.
    STALE_AFTER_SECONDS = 10.0

    def __init__(self):
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def update(self, person_boxes: list[tuple]) -> tuple[list[int], list[int]]:
        """Returns (track_id per box in `person_boxes`, same order; track_ids
        that expired — went unseen for STALE_AFTER_SECONDS — this call)."""
        now = time.monotonic()
        expired = self._prune(now)

        assigned: list[int] = []
        used: set[int] = set()

        for box in person_boxes:
            best_id, best_score = None, 0.0
            for track_id, track in self._tracks.items():
                if track_id in used:
                    continue
                score = iou(box, track.bbox)
                if score > best_score:
                    best_id, best_score = track_id, score

            if best_id is not None and best_score >= self.IOU_MATCH_THRESHOLD:
                track_id = best_id
            else:
                track_id = self._next_id
                self._next_id += 1

            self._tracks[track_id] = _Track(track_id=track_id, bbox=box, last_seen=now)
            used.add(track_id)
            assigned.append(track_id)

        return assigned, expired

    def _prune(self, now: float) -> list[int]:
        stale = [tid for tid, t in self._tracks.items() if (now - t.last_seen) > self.STALE_AFTER_SECONDS]
        for tid in stale:
            del self._tracks[tid]
        return stale
