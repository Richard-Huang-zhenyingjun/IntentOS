"""Constraint Evaluator - Evaluate safety constraints based on state estimate."""

from typing import Set
from affordances.state_schema import (
    ObjectStateEstimate, SafetyConstraints, LampState, DoorState, PhoneState
)
from affordances.affordance_schema import AffordanceType


class ConstraintEvaluator:
    """
    Evaluate safety constraints based on state estimate
    
    Determines:
    - Which actions are safe given current state and confidence
    - Whether to use specific actions, toggles, or block entirely
    
    Week 6: Conservative approach
    - High confidence (≥0.7) → specific actions
    - Medium confidence (0.4-0.7) → toggle fallback
    - Low confidence (<0.4) → block with explanation
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Thresholds
        self.min_state_confidence = config.get('min_state_confidence', 0.7)
        self.fallback_confidence = config.get('fallback_confidence', 0.4)
        self.prefer_specific = config.get('prefer_specific_over_toggle', True)
        
        # Statistics
        self.total_evaluations = 0
        self.specific_allowed = 0
        self.toggle_fallback = 0
        self.blocked = 0
    
    def evaluate(self, state_estimate: ObjectStateEstimate) -> SafetyConstraints:
        """
        Evaluate safety constraints for state estimate
        
        Args:
            state_estimate: Current state estimate
        
        Returns:
            SafetyConstraints with allowed actions
        """
        self.total_evaluations += 1
        
        category = state_estimate.category
        state = state_estimate.state
        confidence = state_estimate.confidence
        
        # === BLOCKING CONDITION: Too uncertain ===
        if confidence < self.fallback_confidence:
            self.blocked += 1
            return SafetyConstraints.create_blocked(
                reason=f"State confidence too low ({confidence:.2f} < {self.fallback_confidence}): {state_estimate.reason}"
            )
        
        # === FALLBACK CONDITION: Uncertain ===
        if confidence < self.min_state_confidence:
            self.toggle_fallback += 1
            return self._fallback_to_toggle(category, state_estimate)
        
        # === SPECIFIC ACTIONS: High confidence ===
        self.specific_allowed += 1
        return self._specific_actions(category, state, state_estimate)
    
    def _specific_actions(self,
                         category: str,
                         state: str,
                         state_estimate: ObjectStateEstimate) -> SafetyConstraints:
        """Determine specific actions based on state"""
        
        if category == 'lamp':
            if state == LampState.ON.value:
                # Lamp is ON → only TURN_OFF makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.TURN_OFF},
                    reason=f"Lamp is ON (conf={state_estimate.confidence:.2f}) → Turn Off",
                    confidence=state_estimate.confidence
                )
            elif state == LampState.OFF.value:
                # Lamp is OFF → only TURN_ON makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.TURN_ON},
                    reason=f"Lamp is OFF (conf={state_estimate.confidence:.2f}) → Turn On",
                    confidence=state_estimate.confidence
                )
            else:
                # Unknown state → fallback
                return self._fallback_to_toggle('lamp', state_estimate)
        
        elif category == 'door':
            if state == DoorState.OPEN.value:
                # Door is OPEN → only CLOSE makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.CLOSE},
                    reason=f"Door is OPEN (conf={state_estimate.confidence:.2f}) → Close",
                    confidence=state_estimate.confidence
                )
            elif state == DoorState.CLOSED.value:
                # Door is CLOSED → only OPEN makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.OPEN},
                    reason=f"Door is CLOSED (conf={state_estimate.confidence:.2f}) → Open",
                    confidence=state_estimate.confidence
                )
            else:
                # Unknown state → fallback
                return self._fallback_to_toggle('door', state_estimate)
        
        elif category == 'phone':
            if state == PhoneState.SCREEN_ON.value:
                # Screen is ON → only SLEEP makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.SLEEP},
                    reason=f"Screen is ON (conf={state_estimate.confidence:.2f}) → Sleep",
                    confidence=state_estimate.confidence
                )
            elif state == PhoneState.SCREEN_OFF.value:
                # Screen is OFF → only WAKE makes sense
                return SafetyConstraints.create_specific(
                    specific_actions={AffordanceType.WAKE},
                    reason=f"Screen is OFF (conf={state_estimate.confidence:.2f}) → Wake",
                    confidence=state_estimate.confidence
                )
            else:
                # Unknown state → fallback
                return self._fallback_to_toggle('phone', state_estimate)
        
        else:
            # Unknown category → block
            return SafetyConstraints.create_blocked(
                reason=f"Unknown category: {category}"
            )
    
    def _fallback_to_toggle(self,
                           category: str,
                           state_estimate: ObjectStateEstimate) -> SafetyConstraints:
        """Fallback to safe toggle action when state uncertain"""
        
        if category == 'lamp':
            toggle = AffordanceType.TOGGLE_POWER
            reason = f"Lamp state uncertain (conf={state_estimate.confidence:.2f}) → Toggle Power"
        elif category == 'door':
            toggle = AffordanceType.TOGGLE_OPEN
            reason = f"Door state uncertain (conf={state_estimate.confidence:.2f}) → Toggle Open/Close"
        elif category == 'phone':
            toggle = AffordanceType.TOGGLE_SCREEN
            reason = f"Phone state uncertain (conf={state_estimate.confidence:.2f}) → Toggle Screen"
        else:
            return SafetyConstraints.create_blocked(
                reason=f"Unknown category: {category}"
            )
        
        return SafetyConstraints.create_toggle_only(
            toggle_action=toggle,
            reason=reason,
            confidence=state_estimate.confidence
        )
    
    def get_statistics(self) -> dict:
        """Get evaluation statistics"""
        return {
            'total_evaluations': self.total_evaluations,
            'specific_allowed': self.specific_allowed,
            'toggle_fallback': self.toggle_fallback,
            'blocked': self.blocked,
            'specific_rate': self.specific_allowed / max(1, self.total_evaluations),
            'fallback_rate': self.toggle_fallback / max(1, self.total_evaluations),
            'block_rate': self.blocked / max(1, self.total_evaluations)
        }




