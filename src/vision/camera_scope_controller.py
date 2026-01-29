"""Camera Scope Controller - Bridge from camera pipeline to core system."""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
import logging

from intent_core.schema import SystemState
from vision.focus_selector import FocusSelector, FocusResult
from vision.object_detector import DetectionResult
from vision.object_tracker import ObjectTracker
from vision.scope_stability import ScopeStability, StableScopeResult
from vision.focus_commitment import FocusCommitment, CommitmentResult
from vision.tracking_schema import TrackingResult

logger = logging.getLogger(__name__)


@dataclass
class CameraScopeSignal:
    """
    Signal sent from camera pipeline to core system.
    
    This is a SUGGESTION, not a command.
    Core system decides if it accepts the suggestion.
    """
    # What was detected
    scoped_object_id: Optional[str]
    object_label: Optional[str]
    object_category: Optional[str]  # NEW: Object category (lamp, door, phone, etc.)
    bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    
    # Why this decision
    focus_reason: str
    ambiguity_detected: bool
    
    # Metadata
    frame_id: int
    timestamp: float
    
    # Suggested system state (core decides if it accepts)
    suggested_state: SystemState  # IDLE, SCOPED, or PAUSED
    
    # Week 2: Additional tracking metadata
    tracking_metadata: Dict = field(default_factory=dict)


@dataclass
class CameraScopeState:
    """
    Controller's internal state (read-only from outside).
    
    Used for monitoring and logging only.
    """
    current_scope: Optional[CameraScopeSignal]
    last_update: float
    frames_processed: int
    scopes_created: int
    ambiguities_detected: int


class CameraScopeController:
    """
    Bridge between camera/tracking and core system (ENHANCED for Week 2)
    
    New pipeline:
    Detections → Tracker → FocusSelector → Commitment → Stability → Signal
    
    Key properties:
    - SUGGESTER, not COMMANDER: Suggests state, core decides
    - Read-only: Never mutates core system state
    - No execution: Camera scope ≠ execution permission
    - Safety-aware: Enforces camera-specific safety rules
    """
    
    def __init__(self, config: dict, seed: int = 42):
        """
        Initialize camera scope controller.
        
        Args:
            config: Controller configuration
            seed: Random seed for deterministic tracking
        """
        self.config = config
        self.min_scope_confidence = config.get('min_scope_confidence', 0.6)
        
        # NEW: Tracking components
        self.tracker = ObjectTracker(
            config=config.get('tracking', {}),
            seed=seed
        )
        self.focus_selector = FocusSelector(
            config=config.get('focus_selection', {})
        )
        self.stability_gate = ScopeStability(
            config=config.get('scope_stability', {})
        )
        self.commitment_gate = FocusCommitment(
            config=config.get('focus_commitment', {})
        )
        
        # State tracking
        self.current_stable_scope_id: Optional[str] = None
        self.last_tracking_result: Optional[TrackingResult] = None
        self.last_focus_result: Optional[FocusResult] = None
        self.last_commitment_result: Optional[CommitmentResult] = None
        self.last_stability_result: Optional[StableScopeResult] = None
        
        self.state = CameraScopeState(
            current_scope=None,
            last_update=0.0,
            frames_processed=0,
            scopes_created=0,
            ambiguities_detected=0
        )
    
    def process_frame(self,
                     detection_result: DetectionResult,
                     frame_width: int,
                     frame_height: int,
                     frame_id: int,
                     timestamp: float) -> CameraScopeSignal:
        """
        Process detections through full tracking pipeline (Week 2)
        
        Pipeline:
        1. Track objects (ID persistence)
        2. Select focus (scored selection)
        3. Apply commitment (anti-thrash)
        4. Validate stability (N-frame confirmation)
        5. Emit signal
        
        Args:
            detection_result: Detection result from object detector
            frame_width: Frame width in pixels
            frame_height: Frame height in pixels
            frame_id: Frame ID from camera
            timestamp: Timestamp of frame
            
        Returns:
            CameraScopeSignal with suggested state
        """
        self.state.frames_processed += 1
        self.state.last_update = timestamp
        
        # 1. Update tracker
        tracking_result = self.tracker.update(
            detections=detection_result.objects,
            timestamp=timestamp
        )
        self.last_tracking_result = tracking_result  # Store for visualization
        
        # 2. Select focus from tracked objects
        focus_result = self.focus_selector.select(
            tracked_objects=tracking_result.tracked_objects,
            frame_width=frame_width,
            frame_height=frame_height,
            timestamp=timestamp
        )
        self.last_focus_result = focus_result
        
        # 3. Apply focus commitment
        commitment_result = self.commitment_gate.apply(
            current_scoped_id=self.current_stable_scope_id,
            focus_result=focus_result,
            timestamp=timestamp
        )
        self.last_commitment_result = commitment_result
        
        # 4. Check stability
        stability_result = self.stability_gate.step(
            primary=commitment_result.allowed_primary,
            ambiguity=focus_result.ambiguity_detected or commitment_result.oscillation_detected,
            timestamp=timestamp
        )
        self.last_stability_result = stability_result
        
        # 5. Update current scope
        if stability_result.stable:
            self.current_stable_scope_id = stability_result.scoped_track_id
            self.state.scopes_created += 1
        elif stability_result.ambiguity:
            self.state.ambiguities_detected += 1
        
        # 6. Emit signal based on stability
        signal = self._create_signal(
            stability_result=stability_result,
            commitment_result=commitment_result,
            focus_result=focus_result,
            tracking_result=tracking_result,
            frame_id=frame_id,
            timestamp=timestamp
        )
        
        self.state.current_scope = signal
        return signal
    
    def _create_signal(self,
                      stability_result: StableScopeResult,
                      commitment_result: CommitmentResult,
                      focus_result: FocusResult,
                      tracking_result: TrackingResult,
                      frame_id: int,
                      timestamp: float) -> CameraScopeSignal:
        """Create camera scope signal from pipeline results"""
        # Determine suggested state
        if stability_result.ambiguity or commitment_result.oscillation_detected:
            suggested_state = SystemState.PAUSED
            reason = stability_result.reason
        elif stability_result.stable:
            suggested_state = SystemState.SCOPED
            reason = f"stable scope: {stability_result.scoped_label}"
        else:
            suggested_state = SystemState.IDLE
            reason = stability_result.reason
        
        # Infer category from label (simple heuristic)
        object_category = None
        if stability_result.scoped_label:
            # Map common labels to categories
            label_lower = stability_result.scoped_label.lower()
            if 'lamp' in label_lower or 'light' in label_lower:
                object_category = 'lamp'
            elif 'door' in label_lower:
                object_category = 'door'
            elif 'phone' in label_lower:
                object_category = 'phone'
            elif 'cup' in label_lower or 'mug' in label_lower:
                object_category = 'cup'
            else:
                # Default to the label itself
                object_category = stability_result.scoped_label
        
        return CameraScopeSignal(
            scoped_object_id=stability_result.scoped_track_id,
            object_label=stability_result.scoped_label,
            object_category=object_category,
            bbox=stability_result.scoped_bbox,
            confidence=stability_result.scoped_confidence,
            focus_reason=reason,
            ambiguity_detected=stability_result.ambiguity,
            frame_id=frame_id,
            timestamp=timestamp,
            suggested_state=suggested_state,
            
            # Additional Week 2 metadata
            tracking_metadata={
                'num_active_tracks': tracking_result.num_active_tracks,
                'num_confirmed_tracks': tracking_result.num_confirmed_tracks,
                'stability_counter': stability_result.stability_counter,
                'candidate_track_id': stability_result.candidate_track_id,
                'commitment_active': commitment_result.commitment_active,
                'switch_blocked': commitment_result.switch_blocked,
                'oscillation_detected': commitment_result.oscillation_detected
            }
        )
    
    def get_state(self) -> CameraScopeState:
        """
        Get read-only access to controller state.
        
        Returns:
            Copy of current state (for monitoring/logging)
        """
        # Return a copy to prevent external mutation
        return CameraScopeState(
            current_scope=self.state.current_scope,
            last_update=self.state.last_update,
            frames_processed=self.state.frames_processed,
            scopes_created=self.state.scopes_created,
            ambiguities_detected=self.state.ambiguities_detected
        )
    
    def reset(self):
        """
        Reset controller state (for testing/recovery).
        
        Does NOT affect core system state.
        """
        self.tracker.reset()
        self.stability_gate.force_clear()
        self.commitment_gate.reset()
        self.current_stable_scope_id = None
        
        self.state = CameraScopeState(
            current_scope=None,
            last_update=0.0,
            frames_processed=0,
            scopes_created=0,
            ambiguities_detected=0
        )
        logger.info("CameraScopeController: State reset")

