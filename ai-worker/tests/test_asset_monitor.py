"""Fixed safety-asset checks on synthetic frames — no camera, model or broker.

These pin the state machine and fingerprint behavior only. They do not
establish detection accuracy on real factory footage."""
import numpy as np
import pytest

from src.pipeline import asset_fingerprint as fp
from src.pipeline.asset_monitor import MIN_CHANGED_OBSERVATIONS, AssetCheck, AssetMonitor

ROI = (0.6, 0.3, 0.15, 0.4)


def scene(seed=7):
    rng = np.random.default_rng(seed)
    frame = rng.integers(60, 200, size=(180, 320, 3), dtype=np.uint8)
    # Structured background (machines, shelving) so the view has context.
    frame[20:90, 10:120] = (90, 110, 120)
    frame[110:170, 40:150] = (170, 160, 150)
    frame[0:180, 250:270] = (40, 60, 70)
    x0, y0, x1, y1 = fp.roi_box(frame.shape, ROI)
    frame[y0:y1, x0:x1] = (30, 30, 200)                 # red cylinder body
    frame[y0:y0 + 6, x0:x1] = (20, 20, 20)              # black valve head
    frame[y0 + 20:y0 + 30, x0 + 4:x1 - 4] = (240, 240, 240)  # white label
    return frame


def removed(frame):
    out = frame.copy()
    x0, y0, x1, y1 = fp.roi_box(out.shape, ROI)
    rng = np.random.default_rng(99)
    out[y0:y1, x0:x1] = rng.integers(60, 200, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    return out


def spec(frame, asset_id="a1", **overrides):
    return {"asset_id": asset_id, "asset_code": "FE-001", "camera_id": "cam", "roi": list(ROI),
            "roi_fingerprint": fp.encode(fp.roi_fingerprint(frame, ROI)),
            "scene_fingerprint": fp.encode(fp.scene_fingerprint(frame)),
            "check_interval_seconds": 10, "change_after_seconds": 30, "similarity_threshold": 0.6,
            "reference_sha256": "x", "version": 1, **overrides}


def run(monitor, frames, start=0.0, step=10.0, persons=()):
    out = []
    for index, frame in enumerate(frames):
        transitions, statuses = monitor.evaluate(frame, list(persons), start + index * step)
        out.append((transitions, statuses))
    return out


def test_fingerprint_round_trip_and_lighting_tolerance():
    frame = scene()
    reference = fp.roi_fingerprint(frame, ROI)
    assert np.array_equal(fp.decode(fp.encode(reference), fp.ROI_SIZE), reference)
    assert fp.similarity(reference, reference) == pytest.approx(1.0)
    darker = (frame.astype(np.float32) * 0.7).astype(np.uint8)
    assert fp.similarity(fp.roi_fingerprint(darker, ROI), reference) > 0.95
    assert fp.similarity(fp.roi_fingerprint(removed(frame), ROI), reference) < 0.3


@pytest.mark.parametrize("roi", [(-0.1, 0, 0.2, 0.2), (0.9, 0, 0.2, 0.2), (0, 0, 0.01, 0.5), (0, 0, float("nan"), 0.2)])
def test_invalid_roi_rejected(roi):
    with pytest.raises(ValueError):
        fp.validate_roi(*roi)


def test_steady_asset_reports_ok_without_events():
    frame = scene()
    monitor = AssetMonitor([spec(frame)])
    results = run(monitor, [frame] * 6)
    assert all(not transitions for transitions, _ in results)
    assert {status["state"] for _, statuses in results for status in statuses} == {"OK"}


def test_change_fires_once_only_after_duration_and_observations_then_restores():
    frame = scene()
    monitor = AssetMonitor([spec(frame)])
    gone = removed(frame)
    results = run(monitor, [gone] * 6)
    fired = [t for transitions, _ in results for t in transitions]
    # Fires at the 4th check (t=30s, 4 observations), never again while still gone.
    assert [t["route"] for t in fired] == ["events.asset_area_changed"]
    assert results[3][0] and not results[2][0]
    assert fired[0]["similarity"] < 0.6 and fired[0]["scene_similarity"] > 0.5
    back = run(monitor, [frame] * 2, start=60)
    assert not back[0][0] and back[1][0][0]["route"] == "events.asset_restored"


def test_brief_change_never_fires():
    frame = scene()
    monitor = AssetMonitor([spec(frame)])
    gone = removed(frame)
    results = run(monitor, [gone, gone, frame, gone, gone, frame])
    assert not any(transitions for transitions, _ in results)


def test_person_in_front_holds_timer_and_reports_occluded():
    frame = scene()
    monitor = AssetMonitor([spec(frame)])
    x0, y0, x1, y1 = fp.roi_box(frame.shape, ROI)
    person = (x0 - 5, y0 - 5, x1, y1)
    results = run(monitor, [removed(frame)] * 5, persons=[person])
    assert not any(transitions for transitions, _ in results)
    assert {status["state"] for _, statuses in results for status in statuses} == {"Occluded"}


def test_covered_or_moved_camera_is_view_change_not_missing_asset():
    frame = scene()
    monitor = AssetMonitor([spec(frame)])
    dark = np.zeros_like(frame)
    results = run(monitor, [dark] * 5)
    routes = [t["route"] for transitions, _ in results for t in transitions]
    assert routes == ["events.asset_view_changed"]
    assert results[0][1][0]["state"] == "ViewChanged" and results[0][1][0]["similarity"] is None


def test_interval_gates_checks():
    frame = scene()
    monitor = AssetMonitor([spec(frame, check_interval_seconds=60)])
    assert monitor.due(0)
    monitor.evaluate(frame, [], 0)
    assert not monitor.due(59) and monitor.due(60)
    assert monitor.evaluate(frame, [], 30) == ([], [])


def test_unchanged_spec_keeps_timers_across_policy_reapply():
    frame = scene()
    first = AssetMonitor([spec(frame)])
    run(first, [removed(frame)] * MIN_CHANGED_OBSERVATIONS)
    second = AssetMonitor([spec(frame)], previous=first)
    assert second.checks[0].pending_count == MIN_CHANGED_OBSERVATIONS
    changed = AssetMonitor([spec(frame, similarity_threshold=0.5)], previous=first)
    assert changed.checks[0].pending_count == 0


def test_malformed_spec_is_skipped_without_dropping_others():
    frame = scene()
    bad = spec(frame, asset_id="bad", roi_fingerprint="not-base64!")
    monitor = AssetMonitor([bad, spec(frame, asset_id="good"), {"asset_id": "x"}])
    assert [check.asset_id for check in monitor.checks] == ["good"]


def test_state_machine_switches_kind_with_fresh_timer():
    check = AssetCheck(spec(scene()))
    for t in (0, 10):
        assert check.observe("changed", t) is None
    for t in (20, 30, 40):
        assert check.observe("view_changed", t) is None
    assert check.observe("view_changed", 50) == "view_changed"
    assert check.observe("occluded", 60) is None and check.active == "view_changed"
