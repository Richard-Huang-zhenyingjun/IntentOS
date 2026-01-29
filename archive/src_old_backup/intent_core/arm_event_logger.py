"""
Arm event logger - structured JSONL event stream.
Week 9: Record every critical event for replay and analysis.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime


class EventType:
    """Event type constants."""
    # Selection
    TARGET_HOVERED = "target_hovered"
    TARGET_LOCKED = "target_locked"
    TARGET_UNLOCKED = "target_unlocked"
    
    # Proposal
    PROPOSAL_ISSUED = "proposal_issued"
    PROPOSAL_UPDATED = "proposal_updated"
    
    # Decision
    DECISION_RECEIVED = "decision_received"
    DECISION_BLOCKED = "decision_blocked"
    
    # Execution
    EXECUTION_STARTED = "execution_started"
    EXECUTION_PROGRESS = "execution_progress"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    
    # Recovery
    PAUSE_TRIGGERED = "pause_triggered"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    
    # Actions
    CANCELLED = "cancelled"
    UNDO_APPLIED = "undo_applied"
    
    # Safety
    TRUST_VIOLATION = "trust_violation"      # Should NEVER occur
    
    # Session
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


class ArmEventLogger:
    """
    Event logger for arm control system.
    
    Writes structured JSONL (JSON Lines) for:
    - Deterministic replay
    - Performance analysis
    - Trust verification
    
    Week 9: Complete event stream for transparency.
    """
    
    def __init__(self, log_dir: str = "logs", session_id: Optional[str] = None):
        """
        Initialize event logger.
        
        Args:
            log_dir: Directory for log files
            session_id: Session identifier (auto-generated if None)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        if session_id is None:
            session_id = datetime.now().strftime("arm_%Y%m%d_%H%M%S")
        
        self.session_id = session_id
        self.log_path = self.log_dir / f"{session_id}.jsonl"
        self.event_count = 0
        
        # Open log file
        self.log_file = open(self.log_path, 'w')
        
        print(f"✓ Event logger: {self.log_path}")
    
    def emit(self, event_type: str, payload: Dict[str, Any], timestamp: Optional[float] = None) -> None:
        """
        Emit an event to the log.
        
        Args:
            event_type: Event type identifier
            payload: Event data
            timestamp: Event timestamp (auto-generated if None)
        """
        if timestamp is None:
            import time
            timestamp = time.time()
        
        event = {
            "event_id": self.event_count,
            "timestamp": timestamp,
            "event_type": event_type,
            "session_id": self.session_id,
            **payload
        }
        
        # Write JSONL line
        self.log_file.write(json.dumps(event) + '\n')
        self.log_file.flush()
        
        self.event_count += 1
    
    def close(self) -> None:
        """Close log file."""
        if self.log_file:
            self.log_file.close()
            print(f"✓ Event log closed: {self.event_count} events")
    
    def get_session_id(self) -> str:
        """Get session ID."""
        return self.session_id
    
    def get_log_path(self) -> Path:
        """Get log file path."""
        return self.log_path




