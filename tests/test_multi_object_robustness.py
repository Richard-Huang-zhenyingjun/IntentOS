"""
Multi-Object Robustness Tests - Week 7

Tests for:
- Candidate ranking
- Ambiguity detection
- Oscillation detection
- Multi-object safety invariants
"""

import pytest
from vision.candidate_ranker import CandidateRanker, ScoredCandidate
from vision.oscillation_detector import OscillationDetector
from vision.tracking_schema import TrackedObject


class TestMultiObjectRobustness:
    """Week 7 tests: multi-object handling"""
    
    def test_two_objects_close_score_causes_ambiguity(self):
        """INVARIANT: Two objects with close scores → ambiguity"""
        config = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.5,
                'weight_recency': 0.0,
                'weight_size': 0.0,
                'weight_stability': 0.0
            },
            'ambiguity': {
                'min_rank_margin': 0.2,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # Create two objects with very similar scores
        obj1 = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(300, 200, 50, 50),
            confidence=0.8,
            center_point=(325, 225),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        obj2 = TrackedObject(
            track_id="track_002",
            label="cup",
            bbox=(350, 200, 50, 50),
            confidence=0.75,
            center_point=(375, 225),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        result = ranker.rank(
            tracked_objects=[obj1, obj2],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # Should detect ambiguity
        assert result.ambiguity_detected == True
        assert result.primary_choice is None
        assert result.margin < 0.2
    
    def test_one_object_clear_winner_no_ambiguity(self):
        """INVARIANT: One object clearly winning → no ambiguity"""
        config = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.3,
                'weight_recency': 0.1,
                'weight_size': 0.05,
                'weight_stability': 0.05
            },
            'ambiguity': {
                'min_rank_margin': 0.2,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # Object at center (high score)
        obj1 = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(295, 215, 50, 50),  # Very close to center (320, 240)
            confidence=0.9,
            center_point=(320, 240),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Object far from center (low score)
        obj2 = TrackedObject(
            track_id="track_002",
            label="cup",
            bbox=(50, 50, 40, 40),
            confidence=0.6,
            center_point=(70, 70),
            area=1600,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        result = ranker.rank(
            tracked_objects=[obj1, obj2],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # Should be clear choice
        assert result.ambiguity_detected == False
        assert result.primary_choice is not None
        assert result.primary_choice.track_id == "track_001"
        assert result.margin >= 0.2
    
    def test_rapid_switching_triggers_oscillation(self):
        """INVARIANT: Rapid switching → oscillation detected"""
        config = {
            'oscillation': {
                'window_seconds': 3.0,
                'switch_threshold': 3,
                'suppress_duration_seconds': 2.0
            }
        }
        
        detector = OscillationDetector(config)
        
        # Simulate rapid switching
        switches = [
            ("track_001", 0.0),
            ("track_002", 0.5),
            ("track_001", 1.0),
            ("track_002", 1.5),
        ]
        
        results = []
        for track_id, timestamp in switches:
            result = detector.update(track_id, timestamp)
            results.append(result)
        
        # Should detect oscillation
        final_result = results[-1]
        assert final_result.oscillating == True
        assert len(final_result.suppressed_ids) == 2
        assert "track_001" in final_result.suppressed_ids
        assert "track_002" in final_result.suppressed_ids
    
    def test_suppressed_objects_not_selectable(self):
        """INVARIANT: Suppressed objects cannot become primary"""
        config = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.3,
                'weight_recency': 0.1,
                'weight_size': 0.05,
                'weight_stability': 0.05
            },
            'ambiguity': {
                'min_rank_margin': 0.1,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        obj1 = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(320, 240, 50, 50),
            confidence=0.9,
            center_point=(345, 265),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        # Rank with suppression
        result = ranker.rank(
            tracked_objects=[obj1],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1,
            suppressed_ids=["track_001"]  # Suppressed
        )
        
        # Should have no primary (suppressed)
        assert result.primary_choice is None
        assert result.num_candidates == 0
    
    def test_only_one_primary_at_any_time(self):
        """META-INVARIANT: Never more than one primary object"""
        config = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.3,
                'weight_recency': 0.1,
                'weight_size': 0.05,
                'weight_stability': 0.05
            },
            'ambiguity': {
                'min_rank_margin': 0.2,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # Many objects
        objects = []
        for i in range(10):
            objects.append(TrackedObject(
                track_id=f"track_{i:03d}",
                label="object",
                bbox=(i * 50, i * 40, 40, 40),
                confidence=0.7 + i * 0.01,
                center_point=(i * 50 + 20, i * 40 + 20),
                area=1600,
                age_frames=10,
                hits=10,
                confirmed=True
            ))
        
        result = ranker.rank(
            tracked_objects=objects,
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # Either 0 or 1 primary
        if result.primary_choice:
            assert result.num_candidates >= 1
            # Verify only one primary in result
            primaries = [c for c in result.candidates if c.rank == 1]
            assert len(primaries) == 1
        else:
            # Ambiguity - no primary
            assert result.ambiguity_detected == True
    
    def test_oscillation_cooldown_prevents_immediate_reselection(self):
        """INVARIANT: After oscillation, cooldown prevents immediate reselection"""
        config = {
            'oscillation': {
                'window_seconds': 3.0,
                'switch_threshold': 3,
                'suppress_duration_seconds': 2.0,
                'cooldown_frames': 10
            }
        }
        
        detector = OscillationDetector(config)
        
        # Trigger oscillation
        switches = [
            ("track_001", 0.0),
            ("track_002", 0.3),
            ("track_001", 0.6),
            ("track_002", 0.9),
        ]
        
        for track_id, timestamp in switches:
            result = detector.update(track_id, timestamp)
        
        # Should be oscillating
        assert result.oscillating == True
        assert result.suppressed_until is not None
        
        # Check suppression persists
        suppression_end = result.suppressed_until
        
        # Try updating before suppression ends
        result2 = detector.update("track_001", suppression_end - 0.5)
        assert len(result2.suppressed_ids) > 0  # Still suppressed
    
    def test_no_candidates_returns_none_safely(self):
        """INVARIANT: No candidates → None (not error)"""
        config = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.5,
                'weight_recency': 0.0,
                'weight_size': 0.0,
                'weight_stability': 0.0
            },
            'ambiguity': {
                'min_rank_margin': 0.2,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        result = ranker.rank(
            tracked_objects=[],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        assert result.primary_choice is None
        assert result.ambiguity_detected == False
        assert result.num_candidates == 0
        assert result.reason == "No active candidates"
    
    def test_ranking_weights_sum_to_one(self):
        """INVARIANT: Ranking weights must sum to 1.0"""
        # Valid weights
        config1 = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.3,
                'weight_recency': 0.1,
                'weight_size': 0.05,
                'weight_stability': 0.05
            }
        }
        
        ranker1 = CandidateRanker(config1)
        # Should not raise
        
        # Invalid weights (sum != 1.0)
        config2 = {
            'ranking': {
                'weight_center': 0.5,
                'weight_confidence': 0.5,
                'weight_recency': 0.5,  # Sum > 1.0
                'weight_size': 0.0,
                'weight_stability': 0.0
            }
        }
        
        with pytest.raises(AssertionError):
            ranker2 = CandidateRanker(config2)
    
    def test_ambiguity_margin_threshold_respected(self):
        """INVARIANT: Margin threshold enforced consistently"""
        config = {
            'ranking': {
                'weight_center': 1.0,
                'weight_confidence': 0.0,
                'weight_recency': 0.0,
                'weight_size': 0.0,
                'weight_stability': 0.0
            },
            'ambiguity': {
                'min_rank_margin': 0.15,  # 15% margin required
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # Two objects with 10% margin (below threshold)
        obj1 = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(315, 235, 50, 50),
            confidence=0.8,
            center_point=(340, 260),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        obj2 = TrackedObject(
            track_id="track_002",
            label="cup",
            bbox=(330, 245, 50, 50),
            confidence=0.8,
            center_point=(355, 270),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        result = ranker.rank(
            tracked_objects=[obj1, obj2],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # Should detect ambiguity (margin too small)
        if result.margin < 0.15:
            assert result.ambiguity_detected == True
            assert result.primary_choice is None
    
    def test_oscillation_requires_minimum_switches(self):
        """INVARIANT: Oscillation requires threshold switches"""
        config = {
            'oscillation': {
                'window_seconds': 3.0,
                'switch_threshold': 4,  # Requires 4 switches
                'suppress_duration_seconds': 2.0
            }
        }
        
        detector = OscillationDetector(config)
        
        # Only 3 switches (below threshold)
        switches = [
            ("track_001", 0.0),
            ("track_002", 0.5),
            ("track_001", 1.0),
        ]
        
        for track_id, timestamp in switches:
            result = detector.update(track_id, timestamp)
        
        # Should NOT be oscillating (only 2 switches in history)
        assert result.oscillating == False
        assert len(result.suppressed_ids) == 0


class TestRankingScoring:
    """Test candidate scoring components"""
    
    def test_center_score_higher_near_center(self):
        """Center proximity increases score"""
        config = {
            'ranking': {
                'weight_center': 1.0,
                'weight_confidence': 0.0,
                'weight_recency': 0.0,
                'weight_size': 0.0,
                'weight_stability': 0.0
            },
            'ambiguity': {
                'min_rank_margin': 0.5,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # Object at center
        obj_center = TrackedObject(
            track_id="track_center",
            label="lamp",
            bbox=(295, 215, 50, 50),
            confidence=0.5,
            center_point=(320, 240),  # Exact center
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        # Object at edge
        obj_edge = TrackedObject(
            track_id="track_edge",
            label="cup",
            bbox=(0, 0, 50, 50),
            confidence=0.5,
            center_point=(25, 25),  # Far from center
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        result = ranker.rank(
            tracked_objects=[obj_center, obj_edge],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # Center object should win
        assert result.primary_choice.track_id == "track_center"
        assert result.margin > 0.5  # Large margin
    
    def test_confidence_score_matters(self):
        """Higher confidence increases score"""
        config = {
            'ranking': {
                'weight_center': 0.0,
                'weight_confidence': 1.0,
                'weight_recency': 0.0,
                'weight_size': 0.0,
                'weight_stability': 0.0
            },
            'ambiguity': {
                'min_rank_margin': 0.2,
                'absolute_threshold': 0.05
            }
        }
        
        ranker = CandidateRanker(config)
        
        # High confidence
        obj_high = TrackedObject(
            track_id="track_high",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.95,
            center_point=(125, 125),
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        # Low confidence
        obj_low = TrackedObject(
            track_id="track_low",
            label="cup",
            bbox=(200, 200, 50, 50),
            confidence=0.55,
            center_point=(225, 225),
            area=2500,
            age_frames=5,
            hits=5,
            confirmed=True
        )
        
        result = ranker.rank(
            tracked_objects=[obj_high, obj_low],
            frame_width=640,
            frame_height=480,
            timestamp=1.0,
            frame_id=1
        )
        
        # High confidence object should win
        assert result.primary_choice.track_id == "track_high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




