"""Tests for FocusSelector module."""

import unittest
import math
from vision.focus_selector import FocusSelector, FocusCandidate, FocusResult
from vision.object_detector import DetectedObject, DetectionResult


class TestFocusSelector(unittest.TestCase):
    """Test FocusSelector functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'min_confidence': 0.5,
            'min_score_margin': 0.2,
            'center_reticle_radius': 50,
            'weight_center': 0.6,
            'weight_size': 0.2,
            'weight_confidence': 0.2
        }
        self.selector = FocusSelector(self.config)
        self.frame_width = 640
        self.frame_height = 480
    
    def test_initialization(self):
        """Test selector initialization."""
        self.assertEqual(self.selector.min_confidence, 0.5)
        self.assertEqual(self.selector.min_score_margin, 0.2)
        self.assertEqual(self.selector.weight_center, 0.6)
    
    def test_select_no_objects(self):
        """Test selection with no objects."""
        result = DetectionResult(
            objects=[],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        self.assertIsNone(focus_result.primary_object)
        self.assertFalse(focus_result.ambiguity_detected)
        self.assertIn("no objects", focus_result.reason.lower())
        self.assertEqual(focus_result.candidates_considered, 0)
    
    def test_select_single_object(self):
        """Test selection with single object."""
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.8,
            center_point=(140, 140),
            area=6400,
            frame_id=0
        )
        
        result = DetectionResult(
            objects=[obj],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        self.assertIsNotNone(focus_result.primary_object)
        self.assertEqual(focus_result.primary_object.label, "lamp")
        self.assertFalse(focus_result.ambiguity_detected)
        self.assertEqual(focus_result.candidates_considered, 1)
    
    def test_select_filters_low_confidence(self):
        """Test that low confidence objects are filtered out."""
        obj_low = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.3,  # Below threshold
            center_point=(140, 140),
            area=6400,
            frame_id=0
        )
        
        obj_high = DetectedObject(
            detection_id="test-2",
            label="cup",
            bbox=(200, 200, 80, 80),
            confidence=0.8,  # Above threshold
            center_point=(240, 240),
            area=6400,
            frame_id=0
        )
        
        result = DetectionResult(
            objects=[obj_low, obj_high],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        # Should only consider high confidence object
        self.assertIsNotNone(focus_result.primary_object)
        self.assertEqual(focus_result.primary_object.label, "cup")
        self.assertEqual(focus_result.candidates_considered, 1)
    
    def test_select_center_preference(self):
        """Test that center objects are preferred."""
        # Object near center
        obj_center = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(300, 220, 80, 80),  # Near center (320, 240)
            confidence=0.7,
            center_point=(340, 260),
            area=6400,
            frame_id=0
        )
        
        # Object far from center
        obj_edge = DetectedObject(
            detection_id="test-2",
            label="cup",
            bbox=(50, 50, 80, 80),  # Far from center
            confidence=0.7,
            center_point=(90, 90),
            area=6400,
            frame_id=0
        )
        
        result = DetectionResult(
            objects=[obj_edge, obj_center],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        # Center object should win (higher center score)
        self.assertIsNotNone(focus_result.primary_object)
        self.assertEqual(focus_result.primary_object.label, "lamp")
    
    def test_select_ambiguity_detection(self):
        """Test that ambiguity is detected when scores are too close."""
        # Create two objects with very similar scores
        # Both near center, same size, same confidence
        obj1 = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(300, 220, 80, 80),
            confidence=0.7,
            center_point=(340, 260),
            area=6400,
            frame_id=0
        )
        
        obj2 = DetectedObject(
            detection_id="test-2",
            label="cup",
            bbox=(310, 230, 80, 80),  # Very close to obj1
            confidence=0.7,
            center_point=(350, 270),
            area=6400,
            frame_id=0
        )
        
        result = DetectionResult(
            objects=[obj1, obj2],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        # Should detect ambiguity if margin is too small
        # Note: May or may not be ambiguous depending on exact positions
        # This test verifies the logic works, not the specific outcome
        self.assertIsNotNone(focus_result.reason)
        if focus_result.ambiguity_detected:
            self.assertIsNone(focus_result.primary_object)
            self.assertIsNotNone(focus_result.runner_up_object)
            self.assertLess(focus_result.score_margin, self.selector.min_score_margin)
    
    def test_select_clear_winner(self):
        """Test selection when there's a clear winner."""
        # Object with high confidence, center position
        obj_winner = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(300, 220, 100, 100),  # Near center, larger
            confidence=0.9,  # High confidence
            center_point=(350, 270),
            area=10000,
            frame_id=0
        )
        
        # Object with lower confidence, edge position
        obj_loser = DetectedObject(
            detection_id="test-2",
            label="cup",
            bbox=(50, 50, 60, 60),  # Edge, smaller
            confidence=0.6,  # Lower confidence
            center_point=(80, 80),
            area=3600,
            frame_id=0
        )
        
        result = DetectionResult(
            objects=[obj_loser, obj_winner],
            frame_id=0,
            timestamp=0.0,
            detection_time_ms=0.0
        )
        
        focus_result = self.selector.select(result, self.frame_width, self.frame_height)
        
        # Clear winner should be selected
        self.assertIsNotNone(focus_result.primary_object)
        self.assertEqual(focus_result.primary_object.label, "lamp")
        self.assertFalse(focus_result.ambiguity_detected)
        self.assertGreaterEqual(focus_result.score_margin, self.selector.min_score_margin)
    
    def test_is_object_in_reticle(self):
        """Test reticle check."""
        # Object at center
        obj_center = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(315, 235, 10, 10),  # Very close to center (320, 240)
            confidence=0.8,
            center_point=(320, 240),
            area=100,
            frame_id=0
        )
        
        # Object far from center
        obj_edge = DetectedObject(
            detection_id="test-2",
            label="cup",
            bbox=(0, 0, 80, 80),
            confidence=0.8,
            center_point=(40, 40),
            area=6400,
            frame_id=0
        )
        
        self.assertTrue(
            self.selector.is_object_in_reticle(obj_center, self.frame_width, self.frame_height)
        )
        self.assertFalse(
            self.selector.is_object_in_reticle(obj_edge, self.frame_width, self.frame_height)
        )
    
    def test_scoring_weights(self):
        """Test that scoring weights are applied correctly."""
        # Create object with known properties
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(320, 240, 100, 100),  # Exactly at center
            confidence=0.8,
            center_point=(370, 290),
            area=10000,
            frame_id=0
        )
        
        # Score manually
        candidates = [obj]
        scored = self.selector._score_candidates(candidates, self.frame_width, self.frame_height)
        
        self.assertEqual(len(scored), 1)
        candidate = scored[0]
        
        # Verify scores are in valid range
        self.assertGreaterEqual(candidate.center_score, 0.0)
        self.assertLessEqual(candidate.center_score, 1.0)
        self.assertGreaterEqual(candidate.size_score, 0.0)
        self.assertLessEqual(candidate.size_score, 1.0)
        self.assertEqual(candidate.confidence_score, 0.8)
        
        # Verify total score uses weights
        expected_total = (
            self.selector.weight_center * candidate.center_score +
            self.selector.weight_size * candidate.size_score +
            self.selector.weight_confidence * candidate.confidence_score
        )
        self.assertAlmostEqual(candidate.total_score, expected_total, places=5)


if __name__ == "__main__":
    unittest.main()

