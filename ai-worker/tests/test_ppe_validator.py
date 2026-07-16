"""Unit tests — PPEValidator multi-frame voting, cooldown throttling, and
low-confidence review routing (AI Worker rules #14, #16)."""
from src.pipeline.ppe_validator import PPEValidator, ViolationTracker
from src.pipeline.types import Detection


ZONE_CONFIG = {
    "helmet_threshold": 0.75,
    "vest_threshold": 0.75,
    "cooldown_seconds": 120,
    "required_consecutive_frames": 3,
    "low_confidence_floor": 0.40,
    "ppe_required": ["helmet", "vest"],
}


def _no_helmet(confidence: float, bbox: tuple = (0, 0, 10, 10)) -> Detection:
    return Detection(class_name="no_helmet", confidence=confidence,
                     bbox=bbox, is_violation=True)


def _no_vest(confidence: float, bbox: tuple = (0, 0, 10, 10)) -> Detection:
    return Detection(class_name="no_vest", confidence=confidence,
                     bbox=bbox, is_violation=True)


def _person(bbox: tuple) -> Detection:
    return Detection(class_name="person", confidence=0.95, bbox=bbox, is_violation=False)


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


class TestMultiPersonTracking:
    """Regression tests for the shared-key bug: two people violating the same
    PPE rule in one frame used to share a single counter/cooldown, so the
    second person's violation could be silently dropped and the first could
    fire a frame early. See person_tracker.py for the tracking design."""

    PERSON_A = (0, 0, 50, 100)
    PERSON_B = (200, 0, 250, 100)

    def test_two_people_different_violations_both_confirm(self):
        validator = PPEValidator()
        frame = [
            _person(self.PERSON_A), _person(self.PERSON_B),
            _no_helmet(0.9, bbox=self.PERSON_A),
            _no_vest(0.9, bbox=self.PERSON_B),
        ]
        assert validator.evaluate(frame, ZONE_CONFIG) == []
        assert validator.evaluate(frame, ZONE_CONFIG) == []
        confirmed = validator.evaluate(frame, ZONE_CONFIG)
        events = {c["event"] for c in confirmed}
        assert events == {"helmet_missing_detected", "vest_missing_detected"}

    def test_two_people_same_violation_are_independent(self):
        """The exact bug scenario: both people missing a helmet at once."""
        validator = PPEValidator()
        frame = [
            _person(self.PERSON_A), _person(self.PERSON_B),
            _no_helmet(0.9, bbox=self.PERSON_A),
            _no_helmet(0.9, bbox=self.PERSON_B),
        ]
        # Neither confirms early — each needs their own 3 consecutive frames,
        # not a combined count from both people hitting the threshold sooner.
        assert validator.evaluate(frame, ZONE_CONFIG) == []
        assert validator.evaluate(frame, ZONE_CONFIG) == []
        confirmed = validator.evaluate(frame, ZONE_CONFIG)
        # Both fire on the same (3rd) frame — neither is dropped in favor of
        # the other, unlike the old shared-key behavior.
        assert len(confirmed) == 2
        assert all(c["event"] == "helmet_missing_detected" for c in confirmed)

    def test_one_person_leaving_does_not_affect_the_other(self):
        validator = PPEValidator()
        both = [
            _person(self.PERSON_A), _person(self.PERSON_B),
            _no_helmet(0.9, bbox=self.PERSON_A),
            _no_helmet(0.9, bbox=self.PERSON_B),
        ]
        validator.evaluate(both, ZONE_CONFIG)
        validator.evaluate(both, ZONE_CONFIG)
        # Person A leaves the frame entirely; only B remains, still violating.
        only_b = [_person(self.PERSON_B), _no_helmet(0.9, bbox=self.PERSON_B)]
        confirmed = validator.evaluate(only_b, ZONE_CONFIG)
        assert len(confirmed) == 1
        assert confirmed[0]["event"] == "helmet_missing_detected"


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
