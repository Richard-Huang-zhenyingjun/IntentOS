"""Focus Selector - Core logic for selecting ONE object as primary focus."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
import logging

from vision.tracking_schema import TrackedObject

logger = logging.getLogger(__name__)


@dataclass
class FocusCandidate:
    """Scored candidate for focus selection"""
    tracked_object: TrackedObject
    
    # Individual scores
    center_score: float  # 0.0-1.0 (proximity to center)
    confidence_score: float  # 0.0-1.0 (detection confidence)
    size_score: float  # 0.0-1.0 (normalized area)
    temporal_stability_score: float  # 0.0-1.0 (age/hits)
    
    # Combined
    total_score: float
    
    # Debug info
    center_distance_pixels: float
    in_center_region: bool


@dataclass
class FocusResult:
    """Result of focus selection (ENHANCED from Week 1)"""
    # Primary selection
    primary_object: Optional[TrackedObject]
    primary_candidate: Optional[FocusCandidate]
    
    # Ambiguity detection
    ambiguity_detected: bool
    ambiguity_reason: str
    
    # Runner-up (for margin calculation)
    runner_up_object: Optional[TrackedObject]
    runner_up_candidate: Optional[FocusCandidate]
    score_margin: float
    
    # All candidates considered
    candidates: List[FocusCandidate]
    num_candidates_considered: int
    
    # Decision reason
    reason: str
    timestamp: float


class FocusSelector:
    """
    Select ONE tracked object as primary focus (ENHANCED for Week 2)
    
    Changes from Week 1:
    - Works on TrackedObject (persistent IDs) instead of DetectedObject
    - Incorporates temporal stability in scoring
    - Explicit ambiguity margin checking
    - Richer debug output
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Thresholds
        self.min_confidence = config.get('min_confidence', 0.5)
        self.ambiguity_margin = config.get('ambiguity_margin', 0.15)
        self.ambiguity_absolute_threshold = config.get('ambiguity_absolute_threshold', 0.05)
        
        # Center region definition
        self.center_width_frac = config.get('center_region_width_fraction', 0.3)
        self.center_height_frac = config.get('center_region_height_fraction', 0.3)
        
        # Scoring weights (must sum to 1.0)
        self.weight_center = config.get('weight_center', 0.5)
        self.weight_confidence = config.get('weight_confidence', 0.3)
        self.weight_size = config.get('weight_size', 0.1)
        self.weight_temporal = config.get('weight_temporal_stability', 0.1)
        
        # Validate weights
        total = self.weight_center + self.weight_confidence + self.weight_size + self.weight_temporal
        assert abs(total - 1.0) < 0.01, f"Weights must sum to 1.0, got {total}"
    
    def select(self,
               tracked_objects: List[TrackedObject],
               frame_width: int,
               frame_height: int,
               timestamp: float) -> FocusResult:
        """
        Select primary focus from tracked objects
        
        Algorithm:
        1. Filter: confidence >= threshold
        2. Score: center + confidence + size + temporal
        3. Rank: sort by total_score
        4. Ambiguity check: if top2 margin < threshold → None
        5. Return: primary or None with reason
        """
        
        # Frame geometry
        frame_center_x = frame_width / 2
        frame_center_y = frame_height / 2
        frame_diagonal = np.sqrt(frame_width**2 + frame_height**2)
        
        center_region_width = frame_width * self.center_width_frac
        center_region_height = frame_height * self.center_height_frac
        
        # 1. Filter candidates
        candidates = []
        for obj in tracked_objects:
            if obj.confidence < self.min_confidence:
                continue
            
            # Score this candidate
            candidate = self._score_candidate(
                obj=obj,
                frame_center=(frame_center_x, frame_center_y),
                frame_diagonal=frame_diagonal,
                center_region=(center_region_width, center_region_height)
            )
            candidates.append(candidate)
        
        # 2. Handle empty case
        if len(candidates) == 0:
            return FocusResult(
                primary_object=None,
                primary_candidate=None,
                ambiguity_detected=False,
                ambiguity_reason="",
                runner_up_object=None,
                runner_up_candidate=None,
                score_margin=0.0,
                candidates=[],
                num_candidates_considered=len(tracked_objects),
                reason="no candidates pass confidence threshold",
                timestamp=timestamp
            )
        
        # 3. Sort by score
        candidates.sort(key=lambda c: c.total_score, reverse=True)
        
        # 4. Ambiguity check
        if len(candidates) >= 2:
            top1 = candidates[0]
            top2 = candidates[1]
            margin = top1.total_score - top2.total_score
            
            # Check if scores are too close
            if margin < self.ambiguity_margin:
                # Additional check: ignore if both scores are very low
                if top1.total_score >= self.ambiguity_absolute_threshold:
                    return FocusResult(
                        primary_object=None,
                        primary_candidate=None,
                        ambiguity_detected=True,
                        ambiguity_reason=f"two objects competing (margin={margin:.3f})",
                        runner_up_object=top2.tracked_object,
                        runner_up_candidate=top2,
                        score_margin=margin,
                        candidates=candidates,
                        num_candidates_considered=len(tracked_objects),
                        reason=f"ambiguous: {top1.tracked_object.label} vs {top2.tracked_object.label}",
                        timestamp=timestamp
                    )
        
        # 5. Return primary
        primary = candidates[0]
        runner_up = candidates[1] if len(candidates) >= 2 else None
        
        return FocusResult(
            primary_object=primary.tracked_object,
            primary_candidate=primary,
            ambiguity_detected=False,
            ambiguity_reason="",
            runner_up_object=runner_up.tracked_object if runner_up else None,
            runner_up_candidate=runner_up,
            score_margin=primary.total_score - runner_up.total_score if runner_up else 1.0,
            candidates=candidates,
            num_candidates_considered=len(tracked_objects),
            reason=f"focused on {primary.tracked_object.label} (score={primary.total_score:.3f})",
            timestamp=timestamp
        )
    
    def _score_candidate(self,
                        obj: TrackedObject,
                        frame_center: Tuple[float, float],
                        frame_diagonal: float,
                        center_region: Tuple[float, float]) -> FocusCandidate:
        """Compute all scores for a candidate"""
        
        # Center score (proximity to frame center)
        cx, cy = obj.center_point
        fcx, fcy = frame_center
        distance = np.sqrt((cx - fcx)**2 + (cy - fcy)**2)
        center_score = 1.0 / (1.0 + distance / frame_diagonal)
        
        # Check if in center region
        in_center = (abs(cx - fcx) < center_region[0] / 2 and
                    abs(cy - fcy) < center_region[1] / 2)
        
        # Confidence score (already 0-1)
        confidence_score = obj.confidence
        
        # Size score (normalized by typical object size)
        # Assume typical object is 10% of frame
        typical_area = (center_region[0] * center_region[1]) / 4
        size_score = min(1.0, obj.area / typical_area) if typical_area > 0 else 0.0
        
        # Temporal stability score (prefer older, more stable tracks)
        # hits / (hits + missed_frames) with age boost
        temporal_score = min(1.0, obj.hits / max(1, obj.age_frames))
        
        # Combined score
        total_score = (
            self.weight_center * center_score +
            self.weight_confidence * confidence_score +
            self.weight_size * size_score +
            self.weight_temporal * temporal_score
        )
        
        return FocusCandidate(
            tracked_object=obj,
            center_score=center_score,
            confidence_score=confidence_score,
            size_score=size_score,
            temporal_stability_score=temporal_score,
            total_score=total_score,
            center_distance_pixels=distance,
            in_center_region=in_center
        )

