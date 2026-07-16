"""Unit tests — PersonTracker IOU matching and stale-track pruning."""
from src.pipeline.person_tracker import PersonTracker, containment_ratio, iou


class TestIou:

    def test_identical_boxes_score_one(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_disjoint_boxes_score_zero(self):
        assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0

    def test_partial_overlap_is_between_zero_and_one(self):
        score = iou((0, 0, 10, 10), (5, 5, 15, 15))
        assert 0.0 < score < 1.0


class TestContainmentRatio:

    def test_fully_inside_scores_one(self):
        assert containment_ratio((2, 2, 8, 8), (0, 0, 10, 10)) == 1.0

    def test_fully_outside_scores_zero(self):
        assert containment_ratio((20, 20, 30, 30), (0, 0, 10, 10)) == 0.0

    def test_small_box_mostly_inside_scores_high(self):
        # e.g. a head-region "no_helmet" box mostly within a full person box
        score = containment_ratio((0, 0, 10, 10), (0, 0, 9, 100))
        assert score > 0.8


class TestPersonTracker:

    def test_same_position_reuses_track_id(self):
        tracker = PersonTracker()
        ids1, _ = tracker.update([(0, 0, 50, 100)])
        ids2, _ = tracker.update([(0, 0, 50, 100)])
        assert ids1 == ids2

    def test_two_people_get_distinct_ids(self):
        tracker = PersonTracker()
        ids, _ = tracker.update([(0, 0, 50, 100), (200, 0, 250, 100)])
        assert len(set(ids)) == 2

    def test_slightly_moved_box_still_matches(self):
        tracker = PersonTracker()
        ids1, _ = tracker.update([(0, 0, 50, 100)])
        ids2, _ = tracker.update([(3, 2, 53, 102)])  # small shift, still high IOU
        assert ids1 == ids2

    def test_far_moved_box_is_treated_as_a_new_person(self):
        tracker = PersonTracker()
        ids1, _ = tracker.update([(0, 0, 50, 100)])
        ids2, _ = tracker.update([(500, 500, 550, 600)])  # no overlap at all
        assert ids1 != ids2

    def test_stale_track_is_pruned_and_reported_as_expired(self):
        tracker = PersonTracker()
        ids1, _ = tracker.update([(0, 0, 50, 100)])
        # Simulate the person having been gone for longer than the stale window.
        for t in tracker._tracks.values():
            t.last_seen -= PersonTracker.STALE_AFTER_SECONDS + 1
        ids2, expired = tracker.update([(200, 0, 250, 100)])
        assert expired == ids1
        assert ids2 != ids1

    def test_two_people_in_one_frame_do_not_collide_on_track_id(self):
        tracker = PersonTracker()
        ids, _ = tracker.update([(0, 0, 50, 100), (200, 0, 250, 100)])
        ids2, _ = tracker.update([(0, 0, 50, 100), (200, 0, 250, 100)])
        assert ids == ids2
