"""State Estimator - Estimate object state from visual + world information."""

from typing import Optional, Dict, Any
import numpy as np
import cv2
from affordances.state_schema import (
    ObjectStateEstimate, LampState, DoorState, PhoneState
)
from execution.smart_world_sim import SmartWorldSim


class StateEstimator:
    """
    Estimate object state from visual + world information
    
    Week 6: Pragmatic approach
    - Primary: Use world state (simulator) if available
    - Fallback: Simple visual heuristics
    - Conservative: Low confidence when uncertain
    
    Week 8+: Could add ML-based perception
    """
    
    def __init__(self, config: dict, world: Optional[SmartWorldSim] = None):
        self.config = config
        self.world = world
        
        # General thresholds
        self.min_state_confidence = config.get('min_state_confidence', 0.7)
        self.fallback_confidence = config.get('fallback_confidence', 0.4)
        self.use_world_state = config.get('use_world_state_hint', True)
        
        # Per-category config
        self.lamp_config = config.get('lamp', {})
        self.door_config = config.get('door', {})
        self.phone_config = config.get('phone', {})
        
        # Statistics
        self.total_estimates = 0
        self.world_state_hits = 0
        self.visual_estimates = 0
        self.unknown_estimates = 0
    
    def estimate(self,
                 object_id: str,
                 category: str,
                 bbox: tuple,
                 frame: Optional[np.ndarray],
                 timestamp: float,
                 frame_id: int) -> ObjectStateEstimate:
        """
        Estimate object state
        
        Strategy:
        1. Try world state (high confidence if available)
        2. Fall back to visual heuristics (medium confidence)
        3. Default to unknown (low confidence)
        
        Args:
            object_id: Object track ID
            category: Object category
            bbox: Bounding box (x, y, w, h)
            frame: Camera frame (optional)
            timestamp: Current timestamp
            frame_id: Current frame ID
        
        Returns:
            ObjectStateEstimate
        """
        self.total_estimates += 1
        
        # === STRATEGY 1: World State Hint (Highest Confidence) ===
        if self.use_world_state and self.world:
            world_estimate = self._estimate_from_world(
                object_id, category, timestamp, frame_id
            )
            if world_estimate and world_estimate.confidence >= self.min_state_confidence:
                self.world_state_hits += 1
                return world_estimate
        
        # === STRATEGY 2: Visual Heuristics (Medium Confidence) ===
        if frame is not None and bbox is not None:
            visual_estimate = self._estimate_from_visual(
                object_id, category, bbox, frame, timestamp, frame_id
            )
            if visual_estimate and visual_estimate.confidence >= self.fallback_confidence:
                self.visual_estimates += 1
                return visual_estimate
        
        # === STRATEGY 3: Unknown (Low Confidence) ===
        self.unknown_estimates += 1
        return ObjectStateEstimate.create_unknown(
            object_id=object_id,
            category=category,
            reason="No world state or visual evidence available",
            timestamp=timestamp,
            frame_id=frame_id
        )
    
    def _estimate_from_world(self,
                           object_id: str,
                           category: str,
                           timestamp: float,
                           frame_id: int) -> Optional[ObjectStateEstimate]:
        """Estimate state from world simulator"""
        if not self.world:
            return None
        
        world_state = self.world.get_object_state(object_id)
        if not world_state:
            return None
        
        # Convert to state enum
        if category == 'lamp':
            state_enum = LampState.from_world_state(world_state)
            confidence = self.lamp_config.get('world_state_confidence', 0.9)
        elif category == 'door':
            state_enum = DoorState.from_world_state(world_state)
            confidence = self.door_config.get('world_state_confidence', 0.9)
        elif category == 'phone':
            state_enum = PhoneState.from_world_state(world_state)
            confidence = self.phone_config.get('world_state_confidence', 0.9)
        else:
            return None
        
        if state_enum.value == 'unknown':
            return None
        
        return ObjectStateEstimate(
            object_id=object_id,
            category=category,
            state=state_enum.value,
            confidence=confidence,
            method='world_state_hint',
            reason=f"State from simulator: {state_enum.value}",
            evidence={'world_state': world_state},
            timestamp=timestamp,
            frame_id=frame_id,
            uncertain=False,
            too_uncertain=False
        )
    
    def _estimate_from_visual(self,
                            object_id: str,
                            category: str,
                            bbox: tuple,
                            frame: np.ndarray,
                            timestamp: float,
                            frame_id: int) -> Optional[ObjectStateEstimate]:
        """Estimate state from visual features"""
        
        if category == 'lamp':
            return self._estimate_lamp_visual(object_id, bbox, frame, timestamp, frame_id)
        elif category == 'door':
            return self._estimate_door_visual(object_id, bbox, frame, timestamp, frame_id)
        elif category == 'phone':
            return self._estimate_phone_visual(object_id, bbox, frame, timestamp, frame_id)
        else:
            return None
    
    def _estimate_lamp_visual(self,
                            object_id: str,
                            bbox: tuple,
                            frame: np.ndarray,
                            timestamp: float,
                            frame_id: int) -> Optional[ObjectStateEstimate]:
        """
        Estimate lamp state from visual brightness
        
        Heuristic: Lamp is ON if bbox region is brighter than surroundings
        """
        x, y, w, h = bbox
        
        # Extract bbox region
        bbox_region = frame[y:y+h, x:x+w]
        if bbox_region.size == 0:
            return None
        
        # Convert to grayscale
        if len(bbox_region.shape) == 3:
            bbox_gray = cv2.cvtColor(bbox_region, cv2.COLOR_BGR2GRAY)
        else:
            bbox_gray = bbox_region
        
        # Calculate mean brightness
        bbox_brightness = np.mean(bbox_gray) / 255.0
        
        # Get surrounding region brightness (for comparison)
        margin = 20
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(frame.shape[1], x + w + margin)
        y2 = min(frame.shape[0], y + h + margin)
        
        surround_region = frame[y1:y2, x1:x2]
        if len(surround_region.shape) == 3:
            surround_gray = cv2.cvtColor(surround_region, cv2.COLOR_BGR2GRAY)
        else:
            surround_gray = surround_region
        
        surround_brightness = np.mean(surround_gray) / 255.0
        
        # Relative brightness
        relative_brightness = bbox_brightness - surround_brightness
        
        # Threshold
        threshold = self.lamp_config.get('brightness_threshold', 0.5)
        visual_confidence = self.lamp_config.get('visual_confidence', 0.6)
        
        # Determine state
        if bbox_brightness > threshold and relative_brightness > 0.1:
            state = LampState.ON.value
            reason = f"Bright region (brightness={bbox_brightness:.2f}, relative={relative_brightness:.2f})"
            confidence = visual_confidence
        elif bbox_brightness <= threshold:
            state = LampState.OFF.value
            reason = f"Dark region (brightness={bbox_brightness:.2f})"
            confidence = visual_confidence
        else:
            # Uncertain
            state = LampState.UNKNOWN.value
            reason = f"Ambiguous brightness (brightness={bbox_brightness:.2f})"
            confidence = 0.3
        
        return ObjectStateEstimate(
            object_id=object_id,
            category='lamp',
            state=state,
            confidence=confidence,
            method='visual_heuristic',
            reason=reason,
            evidence={
                'bbox_brightness': bbox_brightness,
                'surround_brightness': surround_brightness,
                'relative_brightness': relative_brightness
            },
            timestamp=timestamp,
            frame_id=frame_id,
            uncertain=(confidence < self.min_state_confidence),
            too_uncertain=(confidence < self.fallback_confidence)
        )
    
    def _estimate_door_visual(self,
                            object_id: str,
                            bbox: tuple,
                            frame: np.ndarray,
                            timestamp: float,
                            frame_id: int) -> Optional[ObjectStateEstimate]:
        """
        Estimate door state from visual edges
        
        Heuristic: Open door has vertical edge gap, closed door is solid
        
        Note: This is very weak - doors are hard to infer visually
        Week 6: Conservative (low confidence)
        """
        x, y, w, h = bbox
        
        # Extract bbox region
        bbox_region = frame[y:y+h, x:x+w]
        if bbox_region.size == 0:
            return None
        
        # Convert to grayscale
        if len(bbox_region.shape) == 3:
            bbox_gray = cv2.cvtColor(bbox_region, cv2.COLOR_BGR2GRAY)
        else:
            bbox_gray = bbox_region
        
        # Detect vertical edges (Sobel)
        sobel_x = cv2.Sobel(bbox_gray, cv2.CV_64F, 1, 0, ksize=3)
        edge_strength = np.mean(np.abs(sobel_x))
        
        # Threshold (very rough)
        threshold = self.door_config.get('edge_detection_threshold', 0.3)
        visual_confidence = self.door_config.get('visual_confidence', 0.4)
        
        # Door visual heuristics are weak - be conservative
        if edge_strength > threshold * 255:
            state = DoorState.OPEN.value
            reason = f"Vertical edges detected (strength={edge_strength:.1f})"
            confidence = visual_confidence  # Low confidence
        else:
            state = DoorState.CLOSED.value
            reason = f"Solid region (edge_strength={edge_strength:.1f})"
            confidence = visual_confidence  # Low confidence
        
        return ObjectStateEstimate(
            object_id=object_id,
            category='door',
            state=state,
            confidence=confidence,
            method='visual_heuristic',
            reason=reason,
            evidence={'edge_strength': edge_strength},
            timestamp=timestamp,
            frame_id=frame_id,
            uncertain=True,  # Door visuals always uncertain
            too_uncertain=(confidence < self.fallback_confidence)
        )
    
    def _estimate_phone_visual(self,
                             object_id: str,
                             bbox: tuple,
                             frame: np.ndarray,
                             timestamp: float,
                             frame_id: int) -> Optional[ObjectStateEstimate]:
        """
        Estimate phone screen state from brightness
        
        Heuristic: Screen ON if bbox is bright and uniform
        """
        x, y, w, h = bbox
        
        # Extract bbox region
        bbox_region = frame[y:y+h, x:x+w]
        if bbox_region.size == 0:
            return None
        
        # Convert to grayscale
        if len(bbox_region.shape) == 3:
            bbox_gray = cv2.cvtColor(bbox_region, cv2.COLOR_BGR2GRAY)
        else:
            bbox_gray = bbox_region
        
        # Mean brightness
        brightness = np.mean(bbox_gray) / 255.0
        
        # Uniformity (low std = uniform)
        std = np.std(bbox_gray) / 255.0
        uniformity = 1.0 - std
        
        # Threshold
        threshold = self.phone_config.get('screen_brightness_threshold', 0.6)
        visual_confidence = self.phone_config.get('visual_confidence', 0.7)
        
        # Determine state
        if brightness > threshold and uniformity > 0.7:
            state = PhoneState.SCREEN_ON.value
            reason = f"Bright uniform region (brightness={brightness:.2f}, uniformity={uniformity:.2f})"
            confidence = visual_confidence
        elif brightness <= threshold:
            state = PhoneState.SCREEN_OFF.value
            reason = f"Dark screen (brightness={brightness:.2f})"
            confidence = visual_confidence
        else:
            state = PhoneState.UNKNOWN.value
            reason = f"Uncertain screen state"
            confidence = 0.3
        
        return ObjectStateEstimate(
            object_id=object_id,
            category='phone',
            state=state,
            confidence=confidence,
            method='visual_heuristic',
            reason=reason,
            evidence={
                'brightness': brightness,
                'uniformity': uniformity,
                'std': std
            },
            timestamp=timestamp,
            frame_id=frame_id,
            uncertain=(confidence < self.min_state_confidence),
            too_uncertain=(confidence < self.fallback_confidence)
        )
    
    def get_statistics(self) -> dict:
        """Get estimation statistics"""
        return {
            'total_estimates': self.total_estimates,
            'world_state_hits': self.world_state_hits,
            'visual_estimates': self.visual_estimates,
            'unknown_estimates': self.unknown_estimates,
            'world_state_rate': self.world_state_hits / max(1, self.total_estimates),
            'visual_rate': self.visual_estimates / max(1, self.total_estimates),
            'unknown_rate': self.unknown_estimates / max(1, self.total_estimates)
        }




