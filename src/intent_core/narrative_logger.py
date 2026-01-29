"""
Narrative Logger - Story-Level Event Tracking (Week 9)

Maintains recent narrative events for UI display.
Complements detailed JSONL logging with human-readable stories.
"""

from collections import deque
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import time


class NarrativeEventType(str, Enum):
    """Types of narrative events"""
    # Scope
    SCOPE_ACQUIRED = "scope_acquired"
    SCOPE_LOST = "scope_lost"
    SCOPE_CHANGED = "scope_changed"
    
    # Affordances
    AFFORDANCES_AVAILABLE = "affordances_available"
    AFFORDANCES_BLOCKED = "affordances_blocked"
    
    # Confirmation
    CONFIRMATION_STARTED = "confirmation_started"
    CONFIRMATION_PROGRESS = "confirmation_progress"
    CONFIRMATION_COMPLETED = "confirmation_completed"
    CONFIRMATION_CANCELLED = "confirmation_cancelled"
    
    # Execution
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_REFUSED = "execution_refused"
    
    # Recovery
    PAUSE_TRIGGERED = "pause_triggered"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    
    # Undo
    UNDO_AVAILABLE = "undo_available"
    UNDO_REQUESTED = "undo_requested"
    UNDO_APPLIED = "undo_applied"
    UNDO_REFUSED = "undo_refused"
    
    # Ambiguity & Oscillation
    AMBIGUITY_DETECTED = "ambiguity_detected"
    OSCILLATION_DETECTED = "oscillation_detected"
    WAIT_FOR_CLARITY = "wait_for_clarity"


@dataclass
class NarrativeEvent:
    """A human-readable narrative event"""
    event_type: NarrativeEventType
    timestamp: float
    narrative: str  # Human-readable sentence
    details: Dict[str, Any]
    icon: str  # Emoji/symbol for UI
    severity: str  # 'info', 'success', 'warning', 'error'


class NarrativeLogger:
    """
    Generate human-readable narratives from system events (Week 9)
    
    Purpose:
    - Translate technical events into plain English
    - Provide context and reasoning
    - Support transparency and trust
    
    Used by:
    - UI live feed
    - Console output
    - Replay explanation
    - Demo narration
    """
    
    def __init__(self, config: dict):
        """
        Initialize narrative logger
        
        Args:
            config: Configuration dict with:
                - max_recent_events: Max events to keep (default 10)
        """
        self.config = config
        
        # Recent events (ring buffer)
        self.max_recent = config.get('max_recent_events', 10)
        self.recent_events: deque = deque(maxlen=self.max_recent)
        
        # Current system narrative (one-sentence status)
        self.current_narrative = "System initializing..."
        
        # Session summary
        self.session_start_time: Optional[float] = None
        self.total_events = 0
        
        # Event counts
        self.event_counts: Dict[str, int] = {}
    
    def log_scope_acquired(self, object_label: str, category: str, confidence: float, timestamp: float):
        """Log scope acquisition"""
        narrative = f"Focused on {object_label} ({category}) with {confidence:.0%} confidence"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.SCOPE_ACQUIRED,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'object_label': object_label,
                'category': category,
                'confidence': confidence
            },
            icon="🎯",
            severity="info"
        )
        
        self._add_event(event)
        self.current_narrative = f"Focused: {object_label}"
    
    def log_affordances_available(self, options: List[str], state_aware: bool, timestamp: float):
        """Log affordance availability"""
        options_text = ", ".join(options[:2])  # First 2 options
        if len(options) > 2:
            options_text += f" (+{len(options)-2} more)"
        
        method = "state-aware" if state_aware else "fallback"
        narrative = f"Available actions ({method}): {options_text}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.AFFORDANCES_AVAILABLE,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'options': options,
                'state_aware': state_aware,
                'count': len(options)
            },
            icon="✨",
            severity="success"
        )
        
        self._add_event(event)
        self.current_narrative = f"Ready to act on {options[0] if options else 'object'}"
    
    def log_affordances_blocked(self, reason: str, timestamp: float):
        """Log affordance blocking"""
        narrative = f"Actions blocked: {reason}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.AFFORDANCES_BLOCKED,
            timestamp=timestamp,
            narrative=narrative,
            details={'reason': reason},
            icon="🚫",
            severity="warning"
        )
        
        self._add_event(event)
        self.current_narrative = f"Waiting: {reason}"
    
    def log_confirmation_progress(self, frames_held: int, frames_required: int, timestamp: float):
        """Log confirmation progress"""
        percentage = (frames_held / frames_required) * 100
        narrative = f"Confirming action: {frames_held}/{frames_required} ({percentage:.0f}%)"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.CONFIRMATION_PROGRESS,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'frames_held': frames_held,
                'frames_required': frames_required,
                'percentage': percentage
            },
            icon="👆",
            severity="info"
        )
        
        self._add_event(event)
        self.current_narrative = f"Confirming... {percentage:.0f}%"
    
    def log_confirmation_completed(self, action_type: str, object_label: str, timestamp: float):
        """Log successful confirmation"""
        narrative = f"Confirmed: {action_type} on {object_label}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.CONFIRMATION_COMPLETED,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'action_type': action_type,
                'object_label': object_label
            },
            icon="✓",
            severity="success"
        )
        
        self._add_event(event)
        self.current_narrative = f"Confirmed: {action_type}"
    
    def log_execution_succeeded(self, 
                                action_type: str, 
                                object_label: str, 
                                before_state: Dict, 
                                after_state: Dict,
                                timestamp: float):
        """Log successful execution"""
        # Describe state change
        state_change = self._describe_state_change(before_state, after_state)
        narrative = f"Executed: {action_type} on {object_label} → {state_change}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.EXECUTION_SUCCEEDED,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'action_type': action_type,
                'object_label': object_label,
                'before_state': before_state,
                'after_state': after_state,
                'state_change': state_change
            },
            icon="▶️",
            severity="success"
        )
        
        self._add_event(event)
        self.current_narrative = f"Action complete: {state_change}"
    
    def log_execution_refused(self, reason: str, timestamp: float):
        """Log execution refusal"""
        narrative = f"Refused to execute: {reason}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.EXECUTION_REFUSED,
            timestamp=timestamp,
            narrative=narrative,
            details={'reason': reason},
            icon="❌",
            severity="warning"
        )
        
        self._add_event(event)
        self.current_narrative = f"Action blocked: {reason}"
    
    def log_pause_triggered(self, trigger: str, reason: str, timestamp: float):
        """Log pause trigger"""
        narrative = f"System paused ({trigger}): {reason}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.PAUSE_TRIGGERED,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'trigger': trigger,
                'reason': reason
            },
            icon="⏸",
            severity="warning"
        )
        
        self._add_event(event)
        self.current_narrative = f"PAUSED: {reason}"
    
    def log_recovery_started(self, timestamp: float):
        """Log recovery process start"""
        narrative = "Recovery process started - re-establishing safe state"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.RECOVERY_STARTED,
            timestamp=timestamp,
            narrative=narrative,
            details={},
            icon="🔄",
            severity="info"
        )
        
        self._add_event(event)
        self.current_narrative = "Recovering..."
    
    def log_undo_available(self, action_type: str, object_label: str, time_remaining: float, timestamp: float):
        """Log undo availability"""
        narrative = f"Undo available: {action_type} on {object_label} ({time_remaining:.1f}s remaining)"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.UNDO_AVAILABLE,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'action_type': action_type,
                'object_label': object_label,
                'time_remaining': time_remaining
            },
            icon="↩️",
            severity="info"
        )
        
        self._add_event(event)
        self.current_narrative = f"Undo ready: {action_type}"
    
    def log_undo_applied(self, action_type: str, object_label: str, timestamp: float):
        """Log successful undo"""
        narrative = f"Undone: {action_type} on {object_label}"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.UNDO_APPLIED,
            timestamp=timestamp,
            narrative=narrative,
            details={
                'action_type': action_type,
                'object_label': object_label
            },
            icon="↩️",
            severity="success"
        )
        
        self._add_event(event)
        self.current_narrative = "Undo complete"
    
    def log_ambiguity_detected(self, num_objects: int, timestamp: float):
        """Log ambiguity detection"""
        narrative = f"Multiple objects ({num_objects}) competing for focus - waiting for clarity"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.AMBIGUITY_DETECTED,
            timestamp=timestamp,
            narrative=narrative,
            details={'num_objects': num_objects},
            icon="⚠️",
            severity="warning"
        )
        
        self._add_event(event)
        self.current_narrative = "Waiting: ambiguity"
    
    def log_oscillation_detected(self, suppressed_count: int, timestamp: float):
        """Log oscillation detection"""
        narrative = f"Rapid attention switching detected - suppressing {suppressed_count} objects"
        
        event = NarrativeEvent(
            event_type=NarrativeEventType.OSCILLATION_DETECTED,
            timestamp=timestamp,
            narrative=narrative,
            details={'suppressed_count': suppressed_count},
            icon="⚠️",
            severity="warning"
        )
        
        self._add_event(event)
        self.current_narrative = "Waiting: oscillation cooldown"
    
    def _add_event(self, event: NarrativeEvent):
        """Add event to recent list"""
        self.recent_events.append(event)
        self.total_events += 1
        
        # Update counts
        event_type = event.event_type.value
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
    
    def _describe_state_change(self, before: Dict, after: Dict) -> str:
        """Describe state change in human terms"""
        # Common patterns
        if 'power' in before and 'power' in after:
            return f"{before['power']} → {after['power']}"
        
        if 'position' in before and 'position' in after:
            return f"{before['position']} → {after['position']}"
        
        if 'screen' in before and 'screen' in after:
            return f"{before['screen']} → {after['screen']}"
        
        # Generic
        return "state changed"
    
    def get_recent_events(self, n: int = 5) -> List[NarrativeEvent]:
        """Get N most recent events"""
        return list(self.recent_events)[-n:]
    
    def get_current_narrative(self) -> str:
        """Get current one-sentence status"""
        return self.current_narrative
    
    def summarize_session(self) -> str:
        """Generate session summary"""
        if self.total_events == 0:
            return "No events recorded"
        
        # Count key event types
        executions = self.event_counts.get('execution_succeeded', 0)
        refusals = self.event_counts.get('execution_refused', 0)
        pauses = self.event_counts.get('pause_triggered', 0)
        undos = self.event_counts.get('undo_applied', 0)
        
        summary = f"Session Summary:\n"
        summary += f"  Total Events: {self.total_events}\n"
        summary += f"  Executions: {executions}\n"
        summary += f"  Refusals: {refusals}\n"
        summary += f"  Pauses: {pauses}\n"
        summary += f"  Undos: {undos}\n"
        
        return summary
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get narrative statistics"""
        return {
            'total_events': self.total_events,
            'event_counts': self.event_counts.copy(),
            'recent_count': len(self.recent_events)
        }

