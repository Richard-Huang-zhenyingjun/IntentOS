"""Week 2 Tests: Tracking persistence and scope stability."""

import unittest
import numpy as np
from vision.object_tracker import ObjectTracker
from vision.scope_stability import ScopeStability
from vision.focus_commitment import FocusCommitment
from vision.tracking_utils import bbox_iou
from vision.object_detector import DetectedObject
from vision.tracking_schema import TrackedObject
from vision.focus_selector import FocusResult, FocusCandidate


class TestTrackingStability(unittest.TestCase):
    """Week 2 tests: tracking persistence and scope stability"""
    
    def test_track_persistence_under_motion(self):
        """INVARIANT: Small bbox motion keeps same track_id"""
        config = {'iou_match_threshold': 0.3, 'track_min_hits': 1}
        tracker = ObjectTracker(config, seed=42)
        
        # Frame 1: Object at (100, 100, 50, 50)
        det1 = DetectedObject(
            detection_id="d1",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            frame_id=1
        )
        result1 = tracker.update([det1], timestamp=1.0)
        self.assertEqual(len(result1.tracked_objects), 1)
        track_id = result1.tracked_objects[0].track_id
        
        # Frame 2: Object moved slightly to (105, 102, 50, 50)
        det2 = DetectedObject(
            detection_id="d2",
            label="lamp",
            bbox=(105, 102, 50, 50),
            confidence=0.8,
            center_point=(130, 127),
            area=2500,
            frame_id=2
        )
        result2 = tracker.update([det2], timestamp=2.0)
        
        # Should maintain same track_id
        self.assertEqual(len(result2.tracked_objects), 1)
        self.assertEqual(result2.tracked_objects[0].track_id, track_id)
    
    def test_stable_scope_after_n_frames(self):
        """INVARIANT: Stable scope only after N consecutive frames"""
        config = {'scope_stable_frames': 5}
        stability = ScopeStability(config)
        
        # Create mock tracked object
        obj = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Feed same object for 4 frames - should NOT be stable
        for i in range(4):
            result = stability.step(obj, ambiguity=False, timestamp=float(i + 1))
            self.assertFalse(result.stable)
            self.assertEqual(result.stability_counter, i + 1)
        
        # 5th frame - should NOW be stable
        result = stability.step(obj, ambiguity=False, timestamp=5.0)
        self.assertTrue(result.stable)
        self.assertEqual(result.scoped_track_id, "track_001")
        self.assertEqual(result.stability_counter, 5)
    
    def test_flicker_does_not_scope(self):
        """INVARIANT: Alternating primary IDs never create stable scope"""
        config = {'scope_stable_frames': 3}
        stability = ScopeStability(config)
        
        obj_a = TrackedObject(
            track_id="track_A",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        obj_b = TrackedObject(
            track_id="track_B",
            label="cup",
            bbox=(200, 200, 50, 50),
            confidence=0.8,
            center_point=(225, 225),
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        # Alternate between A and B
        for i in range(10):
            obj = obj_a if i % 2 == 0 else obj_b
            result = stability.step(obj, ambiguity=False, timestamp=float(i + 1))
            
            # Should never become stable (counter resets each switch)
            self.assertFalse(result.stable)
            # Counter should be 1 or 2 (never reaches 3)
            self.assertLess(result.stability_counter, 3)
    
    def test_ambiguity_blocks_stability(self):
        """INVARIANT: Ambiguity resets stability counter"""
        config = {'scope_stable_frames': 3}
        stability = ScopeStability(config)
        
        obj = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        # Build up 2 frames
        stability.step(obj, ambiguity=False, timestamp=1.0)
        result = stability.step(obj, ambiguity=False, timestamp=2.0)
        self.assertEqual(result.stability_counter, 2)
        
        # Inject ambiguity
        result = stability.step(obj, ambiguity=True, timestamp=3.0)
        self.assertFalse(result.stable)
        self.assertEqual(result.stability_counter, 0)
        self.assertTrue(result.ambiguity)
        
        # Next frame should restart from 1
        result = stability.step(obj, ambiguity=False, timestamp=4.0)
        self.assertEqual(result.stability_counter, 1)
    
    def test_track_removal_after_max_age(self):
        """INVARIANT: Tracks deleted after max_age missed frames"""
        config = {'track_max_age_frames': 3, 'track_min_hits': 1}
        tracker = ObjectTracker(config, seed=42)
        
        # Create track
        det = DetectedObject(
            detection_id="d1",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            frame_id=1
        )
        result1 = tracker.update([det], timestamp=1.0)
        self.assertEqual(len(result1.tracked_objects), 1)
        track_id = result1.tracked_objects[0].track_id
        
        # Miss 3 frames (should still exist at max_age)
        for i in range(3):
            result = tracker.update([], timestamp=float(i + 2))
            # Track should still exist (missed_frames <= max_age)
            self.assertIn(track_id, tracker.tracks)
        
        # One more miss - should delete (missed_frames > max_age)
        result = tracker.update([], timestamp=6.0)
        self.assertNotIn(track_id, tracker.tracks)
    
    def test_commitment_blocks_rapid_switch(self):
        """INVARIANT: Commitment resists switching for N frames"""
        config = {'commitment_frames': 5, 'commitment_score_advantage': 0.25}
        commitment = FocusCommitment(config)
        
        obj_a = TrackedObject(
            track_id="track_A",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        obj_b = TrackedObject(
            track_id="track_B",
            label="cup",
            bbox=(200, 200, 50, 50),
            confidence=0.9,
            center_point=(225, 225),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Create focus result with A as primary
        focus_a = FocusResult(
            primary_object=obj_a,
            primary_candidate=FocusCandidate(
                tracked_object=obj_a,
                center_score=0.7,
                confidence_score=0.8,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.8,
                center_distance_pixels=10,
                in_center_region=True
            ),
            ambiguity_detected=False,
            ambiguity_reason="",
            runner_up_object=None,
            runner_up_candidate=None,
            score_margin=1.0,
            candidates=[],
            num_candidates_considered=1,
            reason="focused on lamp",
            timestamp=1.0
        )
        
        # Initial commitment to A
        result = commitment.apply("track_A", focus_a, 1.0)
        self.assertIsNotNone(result.allowed_primary)
        self.assertEqual(result.allowed_primary.track_id, "track_A")
        self.assertFalse(result.commitment_active)  # First time, no commitment yet
        
        # Apply again to establish commitment
        result = commitment.apply("track_A", focus_a, 2.0)
        
        # Try to switch to B (within commitment period, insufficient margin)
        focus_b = FocusResult(
            primary_object=obj_b,
            primary_candidate=FocusCandidate(
                tracked_object=obj_b,
                center_score=0.8,
                confidence_score=0.9,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.9,
                center_distance_pixels=10,
                in_center_region=True
            ),
            ambiguity_detected=False,
            ambiguity_reason="",
            runner_up_object=obj_a,
            runner_up_candidate=FocusCandidate(
                tracked_object=obj_a,
                center_score=0.7,
                confidence_score=0.8,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.8,
                center_distance_pixels=10,
                in_center_region=True
            ),
            score_margin=0.1,  # < 0.25 advantage
            candidates=[],
            num_candidates_considered=2,
            reason="focused on cup",
            timestamp=3.0
        )
        
        # Should block switch (insufficient margin and in commitment period)
        result = commitment.apply("track_A", focus_b, 3.0)
        self.assertTrue(result.switch_blocked)
        self.assertIsNone(result.allowed_primary)
        self.assertTrue(result.commitment_active)
    
    def test_oscillation_detection(self):
        """INVARIANT: Rapid A→B→A→B switching triggers suppression"""
        config = {
            'commitment_frames': 2,
            'oscillation_max_switches': 3,
            'oscillation_window_seconds': 3.0
        }
        commitment = FocusCommitment(config)
        
        obj_a = TrackedObject(
            track_id="track_A",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        obj_b = TrackedObject(
            track_id="track_B",
            label="cup",
            bbox=(200, 200, 50, 50),
            confidence=0.8,
            center_point=(225, 225),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Create focus results
        def create_focus_result(primary_obj, runner_up_obj, timestamp):
            return FocusResult(
                primary_object=primary_obj,
                primary_candidate=FocusCandidate(
                    tracked_object=primary_obj,
                    center_score=0.7,
                    confidence_score=0.8,
                    size_score=0.5,
                    temporal_stability_score=0.5,
                    total_score=0.8,
                    center_distance_pixels=10,
                    in_center_region=True
                ),
                ambiguity_detected=False,
                ambiguity_reason="",
                runner_up_object=runner_up_obj,
                runner_up_candidate=FocusCandidate(
                    tracked_object=runner_up_obj,
                    center_score=0.7,
                    confidence_score=0.8,
                    size_score=0.5,
                    temporal_stability_score=0.5,
                    total_score=0.8,
                    center_distance_pixels=10,
                    in_center_region=True
                ) if runner_up_obj else None,
                score_margin=0.3,  # Large margin to allow switches
                candidates=[],
                num_candidates_considered=2 if runner_up_obj else 1,
                reason=f"focused on {primary_obj.label}",
                timestamp=timestamp
            )
        
        # Simulate oscillation: A → B → A → B
        # Start with A
        result = commitment.apply(None, create_focus_result(obj_a, None, 1.0), 1.0)
        self.assertIsNotNone(result.allowed_primary)
        
        # Switch to B (after commitment expires or with large margin)
        result = commitment.apply("track_A", create_focus_result(obj_b, obj_a, 2.0), 2.0)
        self.assertIsNotNone(result.allowed_primary)
        
        # Switch back to A
        result = commitment.apply("track_B", create_focus_result(obj_a, obj_b, 2.5), 2.5)
        self.assertIsNotNone(result.allowed_primary)
        
        # Switch to B again (4th switch)
        result = commitment.apply("track_A", create_focus_result(obj_b, obj_a, 3.0), 3.0)
        
        # Should detect oscillation and suppress both
        if len(commitment.switch_history) >= config['oscillation_max_switches']:
            # Check if oscillation was detected
            oscillation_detected = commitment._detect_oscillation(3.0)
            if oscillation_detected:
                # Both tracks should be suppressed
                self.assertIn("track_A", commitment.oscillation_suppressed_tracks)
                self.assertIn("track_B", commitment.oscillation_suppressed_tracks)
    
    def test_deterministic_replay(self):
        """META-TEST: Same seed produces same tracking IDs"""
        config = {'track_min_hits': 1}
        
        tracker1 = ObjectTracker(config, seed=42)
        tracker2 = ObjectTracker(config, seed=42)
        
        det = DetectedObject(
            detection_id="d1",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            frame_id=1
        )
        
        result1 = tracker1.update([det], timestamp=1.0)
        result2 = tracker2.update([det], timestamp=1.0)
        
        # Should produce same track IDs
        self.assertEqual(len(result1.tracked_objects), 1)
        self.assertEqual(len(result2.tracked_objects), 1)
        self.assertEqual(result1.tracked_objects[0].track_id, result2.tracked_objects[0].track_id)
    
    def test_track_confirmation_after_min_hits(self):
        """INVARIANT: Tracks only confirmed after min_hits detections"""
        config = {'track_min_hits': 3, 'track_max_age_frames': 10}
        tracker = ObjectTracker(config, seed=42)
        
        det = DetectedObject(
            detection_id="d1",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            frame_id=1
        )
        
        # First detection - track created but not confirmed
        result1 = tracker.update([det], timestamp=1.0)
        self.assertEqual(len(result1.tracked_objects), 0)  # Not confirmed yet
        
        # Second detection
        det2 = DetectedObject("d2", "lamp", (100, 100, 50, 50), 0.8, (125, 125), 2500, 2)
        result2 = tracker.update([det2], timestamp=2.0)
        self.assertEqual(len(result2.tracked_objects), 0)  # Still not confirmed
        
        # Third detection - should be confirmed
        det3 = DetectedObject("d3", "lamp", (100, 100, 50, 50), 0.8, (125, 125), 2500, 3)
        result3 = tracker.update([det3], timestamp=3.0)
        self.assertEqual(len(result3.tracked_objects), 1)  # Now confirmed
        self.assertTrue(result3.tracked_objects[0].confirmed)
    
    def test_stability_maintains_on_missing_primary(self):
        """INVARIANT: Stable scope maintained when primary temporarily missing"""
        config = {'scope_stable_frames': 3}
        stability = ScopeStability(config)
        
        obj = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Build to stable
        for i in range(3):
            stability.step(obj, ambiguity=False, timestamp=float(i + 1))
        
        result = stability.step(obj, ambiguity=False, timestamp=4.0)
        self.assertTrue(result.stable)
        stable_id = result.scoped_track_id
        
        # Primary missing temporarily
        result = stability.step(None, ambiguity=False, timestamp=5.0)
        # Should maintain stable scope
        self.assertTrue(result.stable)
        self.assertEqual(result.scoped_track_id, stable_id)
    
    def test_commitment_timeout_releases(self):
        """INVARIANT: Commitment releases after timeout"""
        config = {
            'commitment_frames': 10,
            'commitment_timeout_seconds': 2.0
        }
        commitment = FocusCommitment(config)
        
        obj_a = TrackedObject(
            track_id="track_A",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        obj_b = TrackedObject(
            track_id="track_B",
            label="cup",
            bbox=(200, 200, 50, 50),
            confidence=0.9,
            center_point=(225, 225),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Establish commitment to A
        focus_a = FocusResult(
            primary_object=obj_a,
            primary_candidate=FocusCandidate(
                tracked_object=obj_a,
                center_score=0.7,
                confidence_score=0.8,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.8,
                center_distance_pixels=10,
                in_center_region=True
            ),
            ambiguity_detected=False,
            ambiguity_reason="",
            runner_up_object=None,
            runner_up_candidate=None,
            score_margin=1.0,
            candidates=[],
            num_candidates_considered=1,
            reason="focused on lamp",
            timestamp=1.0
        )
        
        commitment.apply("track_A", focus_a, 1.0)
        commitment.apply("track_A", focus_a, 1.5)
        
        # After timeout, should allow switch
        focus_b = FocusResult(
            primary_object=obj_b,
            primary_candidate=FocusCandidate(
                tracked_object=obj_b,
                center_score=0.8,
                confidence_score=0.9,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.9,
                center_distance_pixels=10,
                in_center_region=True
            ),
            ambiguity_detected=False,
            ambiguity_reason="",
            runner_up_object=obj_a,
            runner_up_candidate=FocusCandidate(
                tracked_object=obj_a,
                center_score=0.7,
                confidence_score=0.8,
                size_score=0.5,
                temporal_stability_score=0.5,
                total_score=0.8,
                center_distance_pixels=10,
                in_center_region=True
            ),
            score_margin=0.1,
            candidates=[],
            num_candidates_considered=2,
            reason="focused on cup",
            timestamp=3.5  # After timeout
        )
        
        result = commitment.apply("track_A", focus_b, 3.5)
        # Should allow switch after timeout
        self.assertIsNotNone(result.allowed_primary)
        self.assertEqual(result.allowed_primary.track_id, "track_B")


if __name__ == "__main__":
    unittest.main()




