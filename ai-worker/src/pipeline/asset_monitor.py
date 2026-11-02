"""Model-free fixed safety-asset checks on frames the camera already samples.

Each configured asset (fire extinguisher) is compared against its reference
fingerprint at its own interval. An event fires only after a change persists
for change_after_seconds across several observations; a person standing in
front of the asset holds the timer instead of advancing or resetting it.

This detects "the asset area no longer looks like its reference". It cannot
tell missing from displaced or obstructed — a human reviews the evidence.
"""
import structlog

from src.pipeline import asset_fingerprint as fp

log = structlog.get_logger()

# Whole-frame similarity below this means the camera view itself changed
# (moved, covered, dark), which must never be reported as a missing asset.
SCENE_THRESHOLD = 0.5
# A person box covering this fraction of the ROI makes the check inconclusive.
OCCLUSION_FRACTION = 0.1
MIN_CHANGED_OBSERVATIONS = 3
RESTORE_OBSERVATIONS = 2

ROUTES = {"changed": "events.asset_area_changed", "view_changed": "events.asset_view_changed",
          "restored": "events.asset_restored"}
STATUS = {"ok": "OK", "changed": "Changed", "view_changed": "ViewChanged", "occluded": "Occluded"}


class AssetCheck:

    def __init__(self, spec: dict):
        self.spec = dict(spec)
        self.asset_id = str(spec["asset_id"])
        self.roi = tuple(float(v) for v in spec["roi"])
        fp.validate_roi(*self.roi)
        self.roi_reference = fp.decode(spec["roi_fingerprint"], fp.ROI_SIZE)
        self.scene_reference = fp.decode(spec["scene_fingerprint"], fp.SCENE_SIZE)
        self.interval = max(10, int(spec.get("check_interval_seconds", 60)))
        self.change_after = max(30, int(spec.get("change_after_seconds", 300)))
        self.threshold = float(spec.get("similarity_threshold", 0.6))
        self.next_check = 0.0
        self.pending_kind = None
        self.pending_since = None
        self.pending_count = 0
        self.active = None
        self.ok_streak = 0

    def adopt(self, previous: "AssetCheck") -> None:
        """Keep timers across a policy re-apply that did not change this asset."""
        for name in ("next_check", "pending_kind", "pending_since", "pending_count", "active", "ok_streak"):
            setattr(self, name, getattr(previous, name))

    def observe(self, observation: str, now: float):
        """Advance the state machine; returns 'changed', 'view_changed', 'restored' or None."""
        if observation == "ok":
            self.pending_kind, self.pending_since, self.pending_count = None, None, 0
            if self.active is None:
                return None
            self.ok_streak += 1
            if self.ok_streak >= RESTORE_OBSERVATIONS:
                self.active, self.ok_streak = None, 0
                return "restored"
            return None
        if observation not in ("changed", "view_changed"):
            return None  # Occluded: inconclusive, hold every timer.
        self.ok_streak = 0
        if self.active == observation:
            return None
        if self.pending_kind != observation:
            self.pending_kind, self.pending_since, self.pending_count = observation, now, 1
        else:
            self.pending_count += 1
        if self.pending_count >= MIN_CHANGED_OBSERVATIONS and now - self.pending_since >= self.change_after:
            self.active = observation
            self.pending_kind, self.pending_since, self.pending_count = None, None, 0
            return observation
        return None


def _overlap(box, roi_box):
    x0, y0 = max(box[0], roi_box[0]), max(box[1], roi_box[1])
    x1, y1 = min(box[2], roi_box[2]), min(box[3], roi_box[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


class AssetMonitor:

    def __init__(self, specs: list | None, previous: "AssetMonitor | None" = None):
        self.checks: list[AssetCheck] = []
        old = {check.asset_id: check for check in (previous.checks if previous else [])}
        for spec in specs or []:
            try:
                check = AssetCheck(spec)
            except (KeyError, TypeError, ValueError) as error:
                # One malformed entry must not stop the camera or its other assets.
                log.error("asset_monitor.invalid_spec", asset_id=str(spec.get("asset_id")) if isinstance(spec, dict) else None,
                          error_type=type(error).__name__)
                continue
            if check.asset_id in old and old[check.asset_id].spec == check.spec:
                check.adopt(old[check.asset_id])
            self.checks.append(check)

    def due(self, now: float) -> bool:
        return any(now >= check.next_check for check in self.checks)

    def evaluate(self, frame, person_boxes, now: float):
        """Returns (transitions, statuses) for every asset due at `now`."""
        transitions, statuses = [], []
        scene = None
        for check in self.checks:
            if now < check.next_check:
                continue
            check.next_check = now + check.interval
            if scene is None:
                scene = fp.scene_fingerprint(frame)
            scene_similarity = fp.scene_similarity(scene, check.scene_reference, check.roi)
            similarity = None
            if scene_similarity < SCENE_THRESHOLD:
                observation = "view_changed"
            else:
                box = fp.roi_box(frame.shape, check.roi)
                area = (box[2] - box[0]) * (box[3] - box[1])
                if any(_overlap(person, box) >= OCCLUSION_FRACTION * area for person in person_boxes):
                    observation = "occluded"
                else:
                    similarity = fp.similarity(fp.roi_fingerprint(frame, check.roi), check.roi_reference)
                    observation = "changed" if similarity < check.threshold else "ok"
            statuses.append({"asset_id": check.asset_id, "state": STATUS[observation],
                             "similarity": None if similarity is None else round(similarity, 4)})
            result = check.observe(observation, now)
            if result:
                transitions.append({"route": ROUTES[result], "event": ROUTES[result].split(".", 1)[1],
                    "asset_id": check.asset_id, "similarity": None if similarity is None else round(similarity, 4),
                    "scene_similarity": round(scene_similarity, 4)})
        return transitions, statuses
