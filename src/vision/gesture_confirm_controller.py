"""Gesture Confirmation Controller - Bridge between gesture detection and intent system."""

from dataclasses import dataclass
from typing import Optional
from vision.pinch_stability import PinchState
from intent_core.schema import SystemState, Intent, IntentType
from affordances.affordance_schema import AffordanceSet


@dataclass
class GestureConfirmSignal:
    """
    Output signal from gesture confirmation controller
    
    Either:
    - confirmed=True with Intent to inject
    - confirmed=False with block_reason
    """
    confirmed: bool
    intent: Optional[Intent]  # CONFIRM intent if confirmed=True
    
    # Blocking
    blocked: bool
    block_reason: str
    
    # Context at confirmation time
    scoped_object_id: Optional[str]
    affordance_count: int
    
    # Metadata
    timestamp: float
    frame_id: int


class GestureConfirmController:
    """
    Bridge between gesture detection and intent system
    
    Responsibilities:
    - Validate confirmation context (scope, affordances, state)
    - Generate CONFIRM intent (or block with reason)
    - Enforce safety rules (no confirmation during ambiguity/pause)
    
    CRITICAL: This does NOT execute anything
    It only creates a CONFIRM intent that feeds into the existing pipeline
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Context requirements
        self.require_stable_scope = config.get('require_stable_scope', True)
        self.require_affordances = config.get('require_affordances', True)
        self.block_during_ambiguity = config.get('block_during_ambiguity', True)
        self.block_during_pause = config.get('block_during_pause', True)
        self.min_scope_age_frames = config.get('min_scope_age_frames', 3)
        
        # Statistics
        self.total_confirmations = 0
        self.total_blocks = 0
        self.block_reasons_count = {}
    
    def process(self,
                pinch_state: PinchState,
                system_state: SystemState,
                scoped_object_id: Optional[str],
                affordances: Optional[AffordanceSet],
                scope_age_frames: int,
                ambiguity_detected: bool,
                frame_id: int,
                timestamp: float) -> GestureConfirmSignal:
        """
        Process pinch state and generate confirmation signal
        
        Args:
            pinch_state: Current pinch stability state
            system_state: Current system state
            scoped_object_id: Current scoped object (or None)
            affordances: Current affordance set (or None)
            scope_age_frames: How long current scope has been stable
            ambiguity_detected: Is ambiguity present?
            frame_id: Current frame ID
            timestamp: Current timestamp
        
        Returns:
            GestureConfirmSignal (confirmed or blocked)
        """
        
        # === NO CONFIRMATION IF NOT JUST_CONFIRMED ===
        if not pinch_state.just_confirmed:
            return GestureConfirmSignal(
                confirmed=False,
                intent=None,
                blocked=False,
                block_reason="",
                scoped_object_id=scoped_object_id,
                affordance_count=len(affordances.options) if affordances else 0,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # === CONFIRMATION REQUESTED - VALIDATE CONTEXT ===
        
        # Check 1: Scope present?
        if self.require_stable_scope and scoped_object_id is None:
            return self._block(
                reason="No scoped object",
                scoped_object_id=None,
                affordances=affordances,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # Check 2: Scope stable long enough?
        if self.min_scope_age_frames > 0 and scope_age_frames < self.min_scope_age_frames:
            return self._block(
                reason=f"Scope too new ({scope_age_frames}/{self.min_scope_age_frames} frames)",
                scoped_object_id=scoped_object_id,
                affordances=affordances,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # Check 3: Affordances available?
        if self.require_affordances:
            if affordances is None or affordances.blocked:
                return self._block(
                    reason="No affordances available",
                    scoped_object_id=scoped_object_id,
                    affordances=affordances,
                    timestamp=timestamp,
                    frame_id=frame_id
                )
            
            if len(affordances.options) == 0:
                return self._block(
                    reason="No affordance options",
                    scoped_object_id=scoped_object_id,
                    affordances=affordances,
                    timestamp=timestamp,
                    frame_id=frame_id
                )
        
        # Check 4: Ambiguity?
        if self.block_during_ambiguity and ambiguity_detected:
            return self._block(
                reason="Ambiguity detected",
                scoped_object_id=scoped_object_id,
                affordances=affordances,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # Check 5: System state appropriate?
        if system_state == SystemState.PAUSED:
            if self.block_during_pause:
                return self._block(
                    reason="System paused",
                    scoped_object_id=scoped_object_id,
                    affordances=affordances,
                    timestamp=timestamp,
                    frame_id=frame_id
                )
        
        if system_state == SystemState.ERROR:
            return self._block(
                reason="System in error state",
                scoped_object_id=scoped_object_id,
                affordances=affordances,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        if system_state == SystemState.EXECUTING:
            return self._block(
                reason="Already executing",
                scoped_object_id=scoped_object_id,
                affordances=affordances,
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # === ALL CHECKS PASSED - GENERATE CONFIRM INTENT ===
        self.total_confirmations += 1
        
        confirm_intent = Intent(
            type=IntentType.CONFIRM,
            confidence=pinch_state.last_observation.confidence if pinch_state.last_observation else 1.0,
            timestamp=timestamp,
            source="gesture_pinch",
            payload={
                'scoped_object_id': scoped_object_id,
                'affordance_count': len(affordances.options) if affordances else 0,
                'pinch_frames_held': pinch_state.frames_held,
                'gesture_type': 'pinch'
            }
        )
        
        return GestureConfirmSignal(
            confirmed=True,
            intent=confirm_intent,
            blocked=False,
            block_reason="",
            scoped_object_id=scoped_object_id,
            affordance_count=len(affordances.options) if affordances else 0,
            timestamp=timestamp,
            frame_id=frame_id
        )
    
    def _block(self, reason: str, scoped_object_id: Optional[str],
               affordances: Optional[AffordanceSet], timestamp: float, frame_id: int) -> GestureConfirmSignal:
        """Helper to create blocked signal"""
        self.total_blocks += 1
        self.block_reasons_count[reason] = self.block_reasons_count.get(reason, 0) + 1
        
        return GestureConfirmSignal(
            confirmed=False,
            intent=None,
            blocked=True,
            block_reason=reason,
            scoped_object_id=scoped_object_id,
            affordance_count=len(affordances.options) if affordances and not affordances.blocked else 0,
            timestamp=timestamp,
            frame_id=frame_id
        )
    
    def get_statistics(self) -> dict:
        """Get controller statistics"""
        return {
            'total_confirmations': self.total_confirmations,
            'total_blocks': self.total_blocks,
            'block_rate': self.total_blocks / max(1, self.total_confirmations + self.total_blocks),
            'block_reasons': self.block_reasons_count
        }




