import os
import sys

# The container's apt python3.11 package is a pre-release build (3.11.0~rc1)
# missing sys.get_int_max_str_digits / sys.set_int_max_str_digits, added only
# late in the 3.11 release cycle. torch._dynamo's polyfills module imports
# them unconditionally (torch/_dynamo/polyfills/sys.py) and validates the
# polyfill's signature against the original, so the shim names/signatures
# below must match exactly.
_int_max_str_digits = 4300

if not hasattr(sys, "get_int_max_str_digits"):
    def get_int_max_str_digits() -> int:
        return _int_max_str_digits
    sys.get_int_max_str_digits = get_int_max_str_digits

if not hasattr(sys, "set_int_max_str_digits"):
    def set_int_max_str_digits(maxdigits: int) -> None:
        global _int_max_str_digits
        _int_max_str_digits = maxdigits
    sys.set_int_max_str_digits = set_int_max_str_digits

import time
import hashlib
from pathlib import Path

import cv2
import numpy as np
import structlog
from typing import List

from src.config.settings import settings
from src.pipeline.remote_ppe_client import RoboflowPPEClient
from src.pipeline.types import Detection

log = structlog.get_logger()

# Demo mode only (no fine-tuned PPE model): which synthetic violation type is
# "active" cycles on a fixed schedule rather than per-frame-random, since
# PPEValidator requires 3 CONSECUTIVE frames of the SAME type before
# confirming a violation (see ppe_validator.py) — a type that changes every
# frame would never accumulate enough consecutive frames to fire at all.
# Kept stable for DEMO_ROTATION_SECONDS at a time so each type gets a fair
# chance to confirm and fire before rotating to the next.
DEMO_VIOLATION_TYPES = ["no_helmet", "no_vest", "no_gloves", "no_safety_shoes"]
DEMO_ROTATION_SECONDS = 20

# Which body zone each demo violation type needs visible in the frame. There's
# no real pose estimation in demo mode — this is a coarse geometry heuristic
# off the person bbox (e.g. a face/upper-body close-up shouldn't ever be able
# to fire "shoes missing", since feet aren't in frame at all) so the fake
# labels at least stay plausible for the shot, even though they're not real
# PPE detection.
ZONE_FOR_TYPE = {
    "no_helmet": "head",
    "no_vest": "torso",
    "no_gloves": "torso",
    "no_safety_shoes": "feet",
}
# Fraction of frame height the bbox's bottom edge must reach for "feet" to
# count as visible — a tight face/shoulders shot ends well above this.
FEET_VISIBLE_BOTTOM_FRAC = 0.80
# A standing full body is much taller than wide (~2.5-4x); a close-up shot
# with an arm/hand reaching toward the bottom of frame (common with laptop
# webcams) can also push the bbox bottom edge down without feet being in
# frame at all, so the bottom-edge check alone isn't reliable — require the
# bbox shape to actually look like a standing body too. A seated upper-body/
# torso shot (head+shoulders+chest) can still reach ~1.6-2x, so the floor
# needs to sit close to the documented standing-body range, not just above 1.
FEET_VISIBLE_MIN_ASPECT = 2.2

PPE_CLASSES = {
    0: "helmet",
    1: "no_helmet",
    2: "vest",
    3: "no_vest",
    4: "gloves",
    5: "no_gloves",
    6: "safety_shoes",
    7: "no_safety_shoes",
    8: "person",
}

VIOLATION_CLASSES = {"no_helmet", "no_vest", "no_gloves", "no_safety_shoes", "no_mask"}

# Fallback for the pilot when no fine-tuned PPE weights are present at
# YOLO_MODEL_PATH: use a generic pretrained COCO model so the pipeline still
# runs end-to-end (person detection only, no real PPE violation classes).
_FALLBACK_MODEL = "yolov8n.pt"

# Option B remote mode (no local fine-tuned model, but a Roboflow-hosted
# community PPE model is configured): that model only reports item PRESENCE,
# not absence and not "person" — so violations are inferred by combining it
# with the local COCO fallback's person boxes. Each item is only expected in
# a coarse vertical band of the person's bbox (no pose estimation available).
#
# Deliberately limited to helmet/vest: the default hosted model
# (ppe-detection-yolov11-42krk/1) was verified to only ever emit "helmet" and
# "Vest" classes — it has no gloves/shoes classes at all. Since absence is
# inferred from "item never reported", a class the model can't report would
# be reported missing on every single person, every time — a guaranteed false
# positive, not a real detection. If a Roboflow model that genuinely covers
# gloves/shoes is configured later, extend this map (and ITEM_REGION below).
ITEM_TO_VIOLATION = {
    "helmet": "no_helmet",
    "vest": "no_vest",
}
ITEM_REGION = {"helmet": "head", "vest": "torso"}
REGION_FRAC = {"head": (0.0, 0.30), "torso": (0.15, 0.75), "feet": (0.70, 1.0)}
# Horizontal slack around the person bbox — items like gloves/shoes can
# protrude slightly past the torso outline the local model boxed.
REMOTE_MATCH_HORIZONTAL_SLACK = 0.2


class PPEDetector:

    def __init__(self):
        self._ready = False
        self._failed = False
        self._remote_client = None
        production = settings.ENVIRONMENT.lower() == "production"
        if production and (settings.DEMO_MODE or not settings.USE_GPU):
            raise RuntimeError("Production workers require CUDA and forbid demo mode")
        self._ppe_mode = os.path.isfile(settings.YOLO_MODEL_PATH)
        if production and not self._ppe_mode:
            raise RuntimeError("Production requires a local PPE checkpoint; remote/demo fallback is disabled")
        if production and not settings.YOLO_MODEL_SHA256:
            raise RuntimeError("Production requires the reviewed PPE checkpoint SHA-256")
        if self._ppe_mode:
            self.model_sha256 = self._hash_model(settings.YOLO_MODEL_PATH)
            if settings.YOLO_MODEL_SHA256 and self.model_sha256 != settings.YOLO_MODEL_SHA256.lower():
                raise RuntimeError("PPE checkpoint checksum mismatch")
        elif settings.YOLO_MODEL_SHA256:
            raise RuntimeError("Pinned PPE checkpoint is missing")

        import torch
        from ultralytics import YOLO
        if settings.USE_GPU and (not torch.cuda.is_available() or torch.cuda.device_count() < 1):
            raise RuntimeError("CUDA was requested but is unavailable; CPU fallback is disabled")
        self.device = "cuda:0" if settings.USE_GPU else "cpu"
        self._remote_mode = not self._ppe_mode and bool(settings.ROBOFLOW_API_KEY)
        model_path = settings.YOLO_MODEL_PATH if self._ppe_mode else _FALLBACK_MODEL

        if self._remote_mode:
            log.warning(
                "detector.ppe_model_missing",
                expected=settings.YOLO_MODEL_PATH,
                fallback=f"COCO person-detection + Roboflow hosted model ({settings.ROBOFLOW_MODEL_ID})",
                note="No local fine-tuned weights. Using a Roboflow-hosted community PPE model for "
                     "helmet/vest detection only (that model has no gloves/shoes classes), combined "
                     "with local person detection via bbox-region overlap.",
            )
            self._remote_client = RoboflowPPEClient()
        elif not self._ppe_mode:
            if not settings.DEMO_MODE:
                raise RuntimeError("PPE weights or a remote provider are required; DEMO_MODE must be explicitly enabled for synthetic development data")
            log.warning(
                "detector.ppe_model_missing",
                expected=settings.YOLO_MODEL_PATH,
                fallback=_FALLBACK_MODEL,
                note="Using a generic COCO model. DEMO MODE: any detected 'person' is reported "
                     "as a synthetic violation (rotating through helmet/vest/gloves/shoes every "
                     f"{DEMO_ROTATION_SECONDS}s) so the pipeline and UI can be exercised end-to-end "
                     "against real camera frames. Replace with a fine-tuned PPE model for real "
                     "violation detection.",
            )
            self._remote_client = None
        else:
            self._remote_client = None

        try:
            log.info("detector.loading", model=Path(model_path).name, device=self.device)
            self._model = YOLO(model_path)
            if self._model.task != "detect":
                raise RuntimeError("PPE checkpoint must be an object detection model")
            names = self._model.names
            if self._ppe_mode and names != PPE_CLASSES:
                raise RuntimeError("PPE model class mapping does not match the configured detector")
            if not self._ppe_mode:
                if names.get(0) != "person":
                    raise RuntimeError("Development fallback must provide the COCO person class")
                self.model_sha256 = self._hash_model(model_path)
            self._model.to(self.device)
            self._verify_device(require_predictor=False)
            # Exercise preprocessing, predictor initialization, inference and parsing
            # without opening cameras, persisting incidents or publishing alerts.
            self.detect_batch([np.zeros((640, 640, 3), dtype=np.uint8)])
            if settings.USE_GPU:
                torch.cuda.synchronize(0)
            self._verify_device()
            self.mode = "ppe" if self._ppe_mode else "remote" if self._remote_mode else "demo"
            self.model_version = f"{self.mode}:{self.model_sha256[:40]}"  # Existing DB column is 50 characters.
            self._ready = True
            log.info("detector.ready", device=self.device, mode=self.mode, model_sha256=self.model_sha256)
        except BaseException:
            if self._remote_client:
                self._remote_client.close()
            raise

    @staticmethod
    def _hash_model(path):
        with open(path, "rb") as file:
            return hashlib.file_digest(file, "sha256").hexdigest()

    def _verify_device(self, *, require_predictor=True):
        devices = [str(self._model.device)]
        if require_predictor:
            predictor = self._model.predictor
            devices.extend([str(predictor.device), str(predictor.model.device)])
        if any(device != self.device for device in devices):
            raise RuntimeError("Loaded model or predictor is not using the requested inference device")

    def heartbeat_fields(self):
        if not self._ready or self._failed:
            raise RuntimeError("Model runtime is not ready")
        try:
            self._verify_device()
        except Exception:
            self._ready = False
            self._failed = True
            raise
        return {"gpu_available": self.device.startswith("cuda:"), "model_version": self.model_version}

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Rule 13: CLAHE preprocessing on every frame before YOLO inference."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        lightness, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = cv2.merge([clahe.apply(lightness), a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        return self.detect_batch([frame])[0]

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        if self._failed:
            raise RuntimeError("Model runtime failed; restart is required")
        try:
            self._verify_device(require_predictor=False)
            result = self._detect_batch(frames)
            self._verify_device()
            return result
        except Exception:
            self._ready = False
            self._failed = True
            raise

    def _detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        """
        Run inference on multiple camera frames in a single forward pass.
        A GPU processes a batch of N images far more efficiently than N
        sequential single-image calls (better utilization of parallel
        compute per call), so this is what lets one GPU serve more cameras
        — BatchDetector groups pending per-camera frames and calls this.
        """
        processed = [self.preprocess(f) for f in frames]
        results_list = self._model(processed, verbose=False, device=self.device)
        if len(results_list) != len(frames):
            raise RuntimeError("Model returned an invalid number of inference results")

        if self._remote_mode:
            # Sent unprocessed — the remote model was trained on plain
            # images, not our CLAHE-enhanced ones used for local inference.
            remote_preds_list = [self._remote_client.detect(f) for f in frames]
        else:
            remote_preds_list = [None] * len(frames)

        return [
            self._parse_results(r, remote_preds)
            for r, remote_preds in zip(results_list, remote_preds_list)
        ]

    @staticmethod
    def _visible_zones(x1: int, y1: int, x2: int, y2: int, frame_height: int) -> set:
        """Coarse "is this body part plausibly in frame" heuristic from bbox
        geometry alone. Head/torso are assumed visible whenever a person is
        detected at all; feet only count as visible once the box's bottom
        edge reaches near the bottom of the frame AND the box is shaped like
        a standing body (tall/narrow) rather than a close-up (wide/short)."""
        zones = {"head", "torso"}
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        bottom_frac = (y2 / frame_height) if frame_height else 1.0
        aspect = height / width
        if bottom_frac >= FEET_VISIBLE_BOTTOM_FRAC and aspect >= FEET_VISIBLE_MIN_ASPECT:
            zones.add("feet")
        return zones

    def _remote_violations_for_person(
        self, x1: int, y1: int, x2: int, y2: int, frame_height: int,
        remote_preds: list, confidence: float,
    ) -> List[Detection]:
        """Roboflow-hosted model only reports item PRESENCE — no "no_X"
        classes and no "person" class of its own. Absence (violation) is
        inferred: for each item type, look for a same-class remote box whose
        center falls inside this person's bbox within the item's expected
        vertical band; if none is found (and that zone is even plausibly
        visible for this shot), report the corresponding violation."""
        visible = self._visible_zones(x1, y1, x2, y2, frame_height)
        width = max(1, x2 - x1)
        slack = REMOTE_MATCH_HORIZONTAL_SLACK * width
        violations = []

        for item, violation_name in ITEM_TO_VIOLATION.items():
            zone = ITEM_REGION[item]
            if zone not in visible:
                continue
            lo_frac, hi_frac = REGION_FRAC[zone]
            band_top = y1 + lo_frac * (y2 - y1)
            band_bottom = y1 + hi_frac * (y2 - y1)
            found = any(
                str(p.get("class", "")).lower() == item
                and (x1 - slack) <= p.get("x", -1) <= (x2 + slack)
                and band_top <= p.get("y", -1) <= band_bottom
                for p in remote_preds
            )
            if not found:
                violations.append(Detection(
                    class_name=violation_name,
                    confidence=confidence,
                    bbox=(x1, y1, x2, y2),
                    is_violation=True,
                ))
        return violations

    def _parse_results(self, results, remote_preds: list | None = None) -> List[Detection]:
        detections = []
        frame_height = results.orig_shape[0] if getattr(results, "orig_shape", None) else None

        for box in results.boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            if self._ppe_mode:
                class_name = self._model.names.get(cls_id, "unknown")
                is_violation = class_name in VIOLATION_CLASSES
            elif self._remote_mode:
                class_name = self._model.names.get(cls_id, "unknown")
                is_violation = False
                if class_name == "person":
                    detections.extend(self._remote_violations_for_person(
                        x1, y1, x2, y2, frame_height, remote_preds or [], confidence,
                    ))
            else:
                class_name = self._model.names.get(cls_id, "unknown")
                is_violation = False
                # Demo mode: no fine-tuned PPE model is loaded, so there's no
                # real helmet/vest/gloves/shoes signal to violate. Emit the
                # person detection itself (so occupancy counting still works),
                # plus a synthetic violation — type rotates on a fixed
                # schedule (see DEMO_VIOLATION_TYPES/DEMO_ROTATION_SECONDS
                # above), skipped when the current slot's body zone isn't
                # plausibly visible for this bbox (e.g. never "shoes missing"
                # on a face/upper-body close-up) — so the rest of the
                # pipeline (snapshot capture, MinIO upload, alert, dashboard)
                # can be exercised end-to-end against real camera frames,
                # across all violation types, without nonsensical labels.
                if class_name == "person":
                    demo_type = DEMO_VIOLATION_TYPES[
                        int(time.monotonic() // DEMO_ROTATION_SECONDS) % len(DEMO_VIOLATION_TYPES)
                    ]
                    visible = self._visible_zones(x1, y1, x2, y2, frame_height)
                    if ZONE_FOR_TYPE[demo_type] in visible:
                        detections.append(Detection(
                            class_name=demo_type,
                            confidence=confidence,
                            bbox=(x1, y1, x2, y2),
                            is_violation=True,
                        ))

            detections.append(Detection(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
                is_violation=is_violation,
            ))

        return detections
