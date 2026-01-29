"""
UI Snapshot - Complete System State (Week 9)

Pure data structure containing everything the UI needs to render one frame.
No logic, no side effects - just data extraction.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class UISnapshot:
    """
    Complete UI state snapshot (FINALIZED Week 9)
    
    Pure data structure - no side effects
    Everything the UI needs to render one frame
    
    Design:
    - Flat structure (no nested objects)
    - All Optional fields (graceful degradation)
    - Serializable (JSON-ready)
    - Deterministic (same system state → same snapshot)
    """
    
    # === METADATA ===
    timestamp: float
    frame_id: int
    system_time_ms: float  # Time since system start
    
    # === SYSTEM STATE ===
    system_state: str  # 'idle', 'scoped', 'confirming', 'executing', 'paused', 'recovering'
    system_state_reason: str  # Human-readable reason for current state
    execution_allowed: bool  # Can execution happen right now?
    
    # === SCOPE ===
    scope_status: str = 'none'  # 'none', 'tentative', 'stable', 'lost'
    scoped_object_id: Optional[str] = None
    scoped_object_label: Optional[str] = None
    scoped_object_category: Optional[str] = None
    scope_confidence: float = 0.0
    scope_stable_frames: int = 0
    
    # === MULTI-OBJECT SCENE ===
    num_tracked_objects: int = 0
    primary_object_id: Optional[str] = None
    ambiguity_detected: bool = False
    ambiguity_reason: str = ''
    oscillation_detected: bool = False
    oscillation_reason: str = ''
    suppressed_object_ids: List[str] = field(default_factory=list)
    
    # === STATE INFERENCE (READ-ONLY) ===
    state_estimate: Optional[Dict[str, Any]] = None
    state_confidence: float = 0.0
    state_method: str = ''
    state_reasoning: str = ''
    
    # === AFFORDANCES (READ-ONLY) ===
    affordances_available: bool = False
    affordances_blocked: bool = False
    affordances_block_reason: str = ''
    affordance_options: List[Dict[str, Any]] = field(default_factory=list)
    highlighted_option_index: Optional[int] = None
    
    # === GESTURE/CONFIRMATION ===
    hand_detected: bool = False
    hand_confidence: float = 0.0
    pinch_detected: bool = False
    pinch_stable_frames: int = 0
    pinch_required_frames: int = 6
    confirmation_state: str = 'none'  # 'none', 'requested', 'confirming', 'confirmed'
    
    # === AUTHORITY GATES (NEW Week 9 - Checklist) ===
    authority_gates: Dict[str, bool] = field(default_factory=dict)  # {gate_name: passed}
    authority_gate_reasons: Dict[str, str] = field(default_factory=dict)
    all_gates_passed: bool = False
    blocking_gates: List[str] = field(default_factory=list)
    
    # === EXECUTION ===
    execution_result: Optional[Dict[str, Any]] = None
    last_action_type: Optional[str] = None
    last_action_timestamp: Optional[float] = None
    
    # === UNDO ===
    undo_available: bool = False
    undo_action_type: Optional[str] = None
    undo_object_label: Optional[str] = None
    undo_time_remaining: Optional[float] = None
    undo_confirming: bool = False
    
    # === RECOVERY ===
    paused: bool = False
    pause_trigger: Optional[str] = None
    pause_reason: str = ''
    recovery_required: bool = False
    recovery_steps: List[str] = field(default_factory=list)
    recovery_explanation: str = ''
    
    # === NARRATIVE EVENTS (NEW Week 9) ===
    recent_events: List[Dict[str, Any]] = field(default_factory=list)  # Last 5-10 narrative events
    current_narrative: str = ''  # Current system narrative
    
    # === METRICS (NEW Week 9) ===
    session_metrics: Dict[str, Any] = field(default_factory=dict)
    safety_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization
        
        Returns:
            Dict representation of snapshot
        """
        return {
            'metadata': {
                'timestamp': self.timestamp,
                'frame_id': self.frame_id,
                'system_time_ms': self.system_time_ms
            },
            'system': {
                'state': self.system_state,
                'reason': self.system_state_reason,
                'execution_allowed': self.execution_allowed
            },
            'scope': {
                'status': self.scope_status,
                'object_id': self.scoped_object_id,
                'object_label': self.scoped_object_label,
                'category': self.scoped_object_category,
                'confidence': self.scope_confidence,
                'stable_frames': self.scope_stable_frames
            },
            'scene': {
                'num_tracked': self.num_tracked_objects,
                'primary_id': self.primary_object_id,
                'ambiguity_detected': self.ambiguity_detected,
                'ambiguity_reason': self.ambiguity_reason,
                'oscillation_detected': self.oscillation_detected,
                'oscillation_reason': self.oscillation_reason,
                'suppressed_ids': self.suppressed_object_ids
            },
            'state_inference': {
                'estimate': self.state_estimate,
                'confidence': self.state_confidence,
                'method': self.state_method,
                'reasoning': self.state_reasoning
            },
            'affordances': {
                'available': self.affordances_available,
                'blocked': self.affordances_blocked,
                'block_reason': self.affordances_block_reason,
                'options': self.affordance_options,
                'highlighted_index': self.highlighted_option_index
            },
            'gesture': {
                'hand_detected': self.hand_detected,
                'hand_confidence': self.hand_confidence,
                'pinch_detected': self.pinch_detected,
                'pinch_stable_frames': self.pinch_stable_frames,
                'pinch_required_frames': self.pinch_required_frames,
                'confirmation_state': self.confirmation_state
            },
            'authority': {
                'gates': self.authority_gates,
                'reasons': self.authority_gate_reasons,
                'all_passed': self.all_gates_passed,
                'blocking': self.blocking_gates
            },
            'execution': {
                'result': self.execution_result,
                'last_action_type': self.last_action_type,
                'last_action_timestamp': self.last_action_timestamp
            },
            'undo': {
                'available': self.undo_available,
                'action_type': self.undo_action_type,
                'object_label': self.undo_object_label,
                'time_remaining': self.undo_time_remaining,
                'confirming': self.undo_confirming
            },
            'recovery': {
                'paused': self.paused,
                'trigger': self.pause_trigger,
                'reason': self.pause_reason,
                'required': self.recovery_required,
                'steps': self.recovery_steps,
                'explanation': self.recovery_explanation
            },
            'narrative': {
                'recent_events': self.recent_events,
                'current': self.current_narrative
            },
            'metrics': {
                'session': self.session_metrics,
                'safety': self.safety_metrics
            }
        }




