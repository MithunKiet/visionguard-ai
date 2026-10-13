from src.pipeline.ppe_validator import PPEValidator
from src.pipeline.types import Detection

PERSON = Detection("person", 0.95, (0, 0, 100, 200), False)
HELMET = Detection("no_helmet", 0.95, (0, 0, 100, 200), True)


def test_clean_and_uncertain_frames_break_consecutive_streaks():
    for gap in [[PERSON], [PERSON, Detection("no_helmet", 0.5, PERSON.bbox, True)]]:
        validator = PPEValidator()
        config = {"required_consecutive_frames": 3}
        for _ in range(4):
            assert not any(not event["review"] for event in validator.evaluate([PERSON, HELMET], config))
            validator.evaluate(gap, config)


def test_multiple_boxes_do_not_count_as_multiple_frames():
    validator = PPEValidator()
    assert validator.evaluate([PERSON, HELMET, HELMET, HELMET], {"required_consecutive_frames": 3}) == []


def test_empty_ppe_list_disables_ppe_detection():
    validator = PPEValidator()
    assert validator.evaluate([PERSON, HELMET], {"ppe_required": [], "required_consecutive_frames": 1}) == []


def test_shoes_threshold_and_mask_mapping():
    validator = PPEValidator()
    results = validator.evaluate([PERSON, Detection("no_safety_shoes", 0.8, PERSON.bbox, True)],
        {"ppe_required": ["shoes"], "shoes_threshold": 0.99, "required_consecutive_frames": 1})
    assert all(event["review"] for event in results)
    results = validator.evaluate([PERSON, Detection("no_mask", 0.9, PERSON.bbox, True)],
        {"ppe_required": ["mask"], "required_consecutive_frames": 1})
    assert results[0]["event"] == "mask_missing_detected"
    assert results[0]["track_id"] is not None


def test_cooldown_begins_after_delivery_acknowledgement():
    validator = PPEValidator()
    config = {"required_consecutive_frames": 1}
    first = validator.evaluate([PERSON, HELMET], config, auto_mark=False)
    assert first
    assert validator.evaluate([PERSON, HELMET], config, auto_mark=False)
    validator.acknowledge(first[0])
    assert validator.evaluate([PERSON, HELMET], config, auto_mark=False) == []
