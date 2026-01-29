"""
Candidate Ranking System - Week 7

Ranks all tracked objects to select primary focus.
Handles multi-object scenes conservatively (prefer ambiguity over forced choice).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np
from vision.tracking_schema import TrackedObject

@dataclass
class ScoredCandidate:
    """
    Tracked object with computed relevance score
    
    Score components:
    - Center proximity (how close to frame center?)
    - Detection confidence (how reliable?)
    - Recency (was this recently focused?)
    - Size (visibility/salience)
    - Stability (track quality)
    """
    tracked_object: TrackedObject
    
    # Score components
    center_score: float  # 0.0-1.0
    confidence_score: float  # 0.0-1.0
    recency_score: float  # 0.0-1.0
    size_score: float  # 0.0-1.0
    stability_score: float  # 0.0-1.0
    
    # Combined
    total_score: float
    
    # Metadata
    center_distance_pixels: float
    rank: int  # 1 = best, 2 = runner-up, etc.
    
    def __lt__(self, other):
        """Sort by total_score descending"""
        return self.total_score > other.total_score

@dataclass
class RankedCandidates:
    """
    Result of candidate ranking
    
    Either:
    - primary_choice is set (clear winner)
    - ambiguity_detected is True (no clear winner)
    """
    # Selection
    primary_choice: Optional[TrackedObject]  # Best candidate or None
    primary_candidate: Optional[ScoredCandidate]  # Full scoring info
    
    # Runner-up (for margin calculation)
    runner_up: Optional[TrackedObject]
    runner_up_candidate: Optional[ScoredCandidate]
    
    # Ambiguity
    ambiguity_detected: bool
    margin: float  # Score difference between 1st and 2nd
    is_clear_choice: bool
    
    # All candidates
    candidates: List[ScoredCandidate]  # Sorted by score
    num_candidates: int
    
    # Reasoning
    reason: str
    timestamp: float
    frame_id: int

class CandidateRanker:
    """
    Rank all tracked objects to select primary focus
    
    Week 7: Critical component for multi-object handling
    Design: Conservative (prefer ambiguity over forced choice)
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Scoring weights
        ranking_config = config.get('ranking', {})
        self.weight_center = ranking_config.get('weight_center', 0.5)
        self.weight_confidence = ranking_config.get('weight_confidence', 0.3)
        self.weight_recency = ranking_config.get('weight_recency', 0.1)
        self.weight_size = ranking_config.get('weight_size', 0.05)
        self.weight_stability = ranking_config.get('weight_stability', 0.05)
        
        # Validate weights sum to 1.0
        total = sum([self.weight_center, self.weight_confidence, 
                    self.weight_recency, self.weight_size, self.weight_stability])
        assert abs(total - 1.0) < 0.01, f"Weights must sum to 1.0, got {total}"
        
        # Ambiguity detection
        ambiguity_config = config.get('ambiguity', {})
        self.min_rank_margin = ambiguity_config.get('min_rank_margin', 0.2)
        self.absolute_threshold = ambiguity_config.get('absolute_threshold', 0.05)
        self.grace_period = ambiguity_config.get('grace_period_seconds', 0.5)
        
        # Recent focus tracking (for recency bonus)
        self.recent_focus_id: Optional[str] = None
        self.recent_focus_until: Optional[float] = None
        
        # Statistics
        self.total_rankings = 0
        self.ambiguous_rankings = 0
        self.clear_choices = 0
    
    def rank(self,
             tracked_objects: List[TrackedObject],
             frame_width: int,
             frame_height: int,
             timestamp: float,
             frame_id: int,
             suppressed_ids: Optional[List[str]] = None) -> RankedCandidates:
        """
        Rank tracked objects to select primary focus
        
        Args:
            tracked_objects: All tracked objects (from tracker)
            frame_width, frame_height: Frame dimensions
            timestamp: Current timestamp
            frame_id: Current frame ID
            suppressed_ids: Objects to suppress (from oscillation detector)
        
        Returns:
            RankedCandidates with primary choice or ambiguity flag
        """
        self.total_rankings += 1
        
        # Filter out suppressed objects
        suppressed_ids = suppressed_ids or []
        active_objects = [
            obj for obj in tracked_objects
            if obj.track_id not in suppressed_ids
        ]
        
        # No objects → no choice
        if len(active_objects) == 0:
            return RankedCandidates(
                primary_choice=None,
                primary_candidate=None,
                runner_up=None,
                runner_up_candidate=None,
                ambiguity_detected=False,
                margin=0.0,
                is_clear_choice=False,
                candidates=[],
                num_candidates=0,
                reason="No active candidates" if len(suppressed_ids) == 0 else f"{len(suppressed_ids)} candidates suppressed",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # Score all candidates
        frame_center = (frame_width / 2, frame_height / 2)
        frame_diagonal = np.sqrt(frame_width**2 + frame_height**2)
        
        scored_candidates = []
        for obj in active_objects:
            scored = self._score_candidate(
                obj=obj,
                frame_center=frame_center,
                frame_diagonal=frame_diagonal,
                timestamp=timestamp
            )
            scored_candidates.append(scored)
        
        # Sort by total score (descending)
        scored_candidates.sort()
        
        # Assign ranks
        for i, candidate in enumerate(scored_candidates):
            candidate.rank = i + 1
        
        # Check for ambiguity
        if len(scored_candidates) >= 2:
            top1 = scored_candidates[0]
            top2 = scored_candidates[1]
            margin = top1.total_score - top2.total_score
            
            # Ambiguity conditions:
            # 1. Margin too small
            # 2. Both scores above threshold (not just noise)
            if margin < self.min_rank_margin and top1.total_score >= self.absolute_threshold:
                self.ambiguous_rankings += 1
                return RankedCandidates(
                    primary_choice=None,
                    primary_candidate=None,
                    runner_up=top2.tracked_object,
                    runner_up_candidate=top2,
                    ambiguity_detected=True,
                    margin=margin,
                    is_clear_choice=False,
                    candidates=scored_candidates,
                    num_candidates=len(scored_candidates),
                    reason=f"Ambiguous: {top1.tracked_object.label} ({top1.total_score:.3f}) vs {top2.tracked_object.label} ({top2.total_score:.3f}), margin={margin:.3f}",
                    timestamp=timestamp,
                    frame_id=frame_id
                )
        
        # Clear choice
        self.clear_choices += 1
        primary = scored_candidates[0]
        runner_up = scored_candidates[1] if len(scored_candidates) >= 2 else None
        
        # Update recent focus
        self.recent_focus_id = primary.tracked_object.track_id
        self.recent_focus_until = timestamp + self.grace_period
        
        return RankedCandidates(
            primary_choice=primary.tracked_object,
            primary_candidate=primary,
            runner_up=runner_up.tracked_object if runner_up else None,
            runner_up_candidate=runner_up,
            ambiguity_detected=False,
            margin=primary.total_score - runner_up.total_score if runner_up else 1.0,
            is_clear_choice=True,
            candidates=scored_candidates,
            num_candidates=len(scored_candidates),
            reason=f"Clear choice: {primary.tracked_object.label} (score={primary.total_score:.3f})",
            timestamp=timestamp,
            frame_id=frame_id
        )
    
    def _score_candidate(self,
                        obj: TrackedObject,
                        frame_center: Tuple[float, float],
                        frame_diagonal: float,
                        timestamp: float) -> ScoredCandidate:
        """Compute all scores for a candidate"""
        
        # 1. Center score (proximity to frame center)
        cx, cy = obj.center_point
        fcx, fcy = frame_center
        distance = np.sqrt((cx - fcx)**2 + (cy - fcy)**2)
        center_score = 1.0 / (1.0 + distance / frame_diagonal)
        
        # 2. Confidence score (detection confidence)
        confidence_score = obj.confidence
        
        # 3. Recency score (was this recently focused?)
        if (self.recent_focus_id == obj.track_id and 
            self.recent_focus_until and 
            timestamp < self.recent_focus_until):
            recency_score = 1.0
        else:
            recency_score = 0.0
        
        # 4. Size score (larger = more salient)
        # Normalize by typical object size (10% of frame)
        typical_area = (frame_diagonal / 10) ** 2
        size_score = min(1.0, obj.area / typical_area)
        
        # 5. Stability score (track quality)
        # hits / (hits + age - hits) = hits / age
        stability_score = obj.hits / max(1, obj.age_frames)
        
        # Combined score
        total_score = (
            self.weight_center * center_score +
            self.weight_confidence * confidence_score +
            self.weight_recency * recency_score +
            self.weight_size * size_score +
            self.weight_stability * stability_score
        )
        
        return ScoredCandidate(
            tracked_object=obj,
            center_score=center_score,
            confidence_score=confidence_score,
            recency_score=recency_score,
            size_score=size_score,
            stability_score=stability_score,
            total_score=total_score,
            center_distance_pixels=distance,
            rank=0  # Will be set later
        )
    
    def get_statistics(self) -> dict:
        """Get ranking statistics"""
        return {
            'total_rankings': self.total_rankings,
            'ambiguous_rankings': self.ambiguous_rankings,
            'clear_choices': self.clear_choices,
            'ambiguity_rate': self.ambiguous_rankings / max(1, self.total_rankings),
            'clarity_rate': self.clear_choices / max(1, self.total_rankings)
        }
    
    def reset(self):
        """Reset ranker state"""
        self.recent_focus_id = None
        self.recent_focus_until = None
        self.total_rankings = 0
        self.ambiguous_rankings = 0
        self.clear_choices = 0




