"""Unit tests — PPEValidator multi-frame voting, cooldown throttling, and
low-confidence review routing (AI Worker rules #14, #16)."""
from src.pipeline.ppe_validator import PPEValidator, ViolationTracker
from src.pipeline.types import Detection


ZONE_CONFIG = {
    "helmet_threshold": 0.75,
    "cooldown_seconds": 120,
    "required_consecutive_frames": 3,
    "low_confidence_floor": 0.40,
}


def _no_helmet(confidence: float) -> Detection:
    return Detection(class_name="no_helmet", confidence=confidence,
                     bbox=(0, 0, 10, 10), is_violation=True)


class TestMultiFrameVoting:

    def test_requires_three_consecutive_frames(self):
        validator = PPEValidator()
        assert validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG) == []
        assert validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG) == []
        confirmed = validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG)
        assert len(confirmed) == 1
        assert confirmed[0]["event"] == "helmet_missing_detected"
        assert confirmed[0]["review"] is False

    def test_clean_frame_resets_count(self):
        validator = PPEValidator()
        validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG)
        validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG)
        # below the floor → treated as a clean frame, count resets
        validator.evaluate([_no_helmet(0.10)], ZONE_CONFIG)
        assert validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG) == []

    def test_cooldown_blocks_immediate_refire(self):
        validator = PPEValidator()
        for _ in range(2):
            validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG)
        assert len(validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG)) == 1
        # even 3 more confirmed frames stay silent inside the cooldown window
        for _ in range(3):
            assert validator.evaluate([_no_helmet(0.9)], ZONE_CONFIG) == []


class TestLowConfidenceRouting:

    def test_between_floor_and_threshold_goes_to_review(self):
        validator = PPEValidator()
        result = validator.evaluate([_no_helmet(0.55)], ZONE_CONFIG)
        assert len(result) == 1
        assert result[0]["review"] is True
        assert result[0]["event"] == "low_confidence_violation"

    def test_below_floor_is_ignored(self):
        validator = PPEValidator()
        assert validator.evaluate([_no_helmet(0.20)], ZONE_CONFIG) == []

    def test_non_violation_classes_are_ignored(self):
        validator = PPEValidator()
        person = Detection(class_name="person", confidence=0.99,
                           bbox=(0, 0, 5, 5), is_violation=False)
        assert validator.evaluate([person], ZONE_CONFIG) == []


class TestViolationTracker:

    def test_record_counts_and_resets(self):
        tracker = ViolationTracker()
        assert tracker.record("k", True, 2) is False
        assert tracker.record("k", True, 2) is True
        tracker.record("k", False, 2)
        assert tracker.record("k", True, 2) is False

    def test_mark_fired_requires_fresh_confirmation(self):
        tracker = ViolationTracker()
        tracker.record("k", True, 1)
        tracker.mark_fired("k")
        assert tracker.record("k", True, 2) is False
