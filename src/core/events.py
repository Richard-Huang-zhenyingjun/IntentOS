"""
Event system for structured logging and observability.

Week 2-3: Basic event types
Week 4: Gemini-specific events
"""
from enum import Enum
from typing import Optional, Dict, Any, Callable
import logging
import json
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event type constants for structured logging."""
    
    # Week 2-3: Core events
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    PROPOSAL_ISSUED = "proposal_issued"
    DECISION_RECEIVED = "decision_received"
    
    # Week 4: Gemini-specific events
    GEMINI_RAW_RESPONSE = "gemini_raw_response"
    PROPOSER_PARSE_REJECTED = "proposer_parse_rejected"
    PROPOSER_FAILED = "proposer_failed"
    PROPOSER_FALLBACK_USED = "proposer_fallback_used"
    GEMINI_CACHE_HIT = "gemini_cache_hit"
    
    # Week 5: Decision pipeline events
    DECISION_ACCEPTED = "decision_accepted"
    DECISION_REJECTED = "decision_rejected"
    
    # Week 7: Authorization
    AUTH_TOKEN_ISSUED = "auth_token_issued"
    AUTH_TOKEN_COMPLETED = "auth_token_completed"
    AUTH_TOKEN_INVALIDATED = "auth_token_invalidated"
    
    # Week 7: Trust
    TRUST_UPDATED = "trust_updated"
    TRUST_REAUTH_TRIGGERED = "trust_reauth_triggered"
    
    # Week 7: Autonomy
    AUTONOMY_LEVEL_SET = "autonomy_level_set"
    AUTONOMY_OBJECT_AWAIT_CONFIRM = "autonomy_object_await_confirm"
    
    # Week 7: Safe pause
    SAFE_PAUSE_STARTED = "safe_pause_started"
    SAFE_PAUSE_COMPLETED = "safe_pause_completed"


class EventEmitter:
    """
    Simple event emitter for structured logging.
    
    Week 4: Basic implementation for Gemini events.
    Week 5+: May add JSONL file logging, metrics aggregation, etc.
    """
    
    def __init__(self, enabled: bool = True, log_path: Optional[str] = None):
        self.enabled = enabled
        self._handlers: Dict[EventType, list[Callable[[EventType, Dict[str, Any]], None]]] = {}
        self.log_path = log_path
        self._file = None

        if self.enabled and self.log_path:
            try:
                path = Path(self.log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(path, "a", encoding="utf-8")
            except OSError as e:
                print(f"WARNING: Failed to open event log: {e}", file=sys.stderr)
                self._file = None
    
    def emit(
        self,
        event_type: EventType,
        frame: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Emit an event.
        
        Args:
            event_type: Type of event
            frame: Optional frame number
            data: Optional event data dictionary
        """
        if not self.enabled:
            return
        
        data = data or {}
        if frame is not None:
            data['frame'] = frame
        
        # Log to console
        logger.info(f"[EVENT] {event_type.value}: {data}")
        
        # Persist JSONL event (best effort)
        event_record = {
            "event_type": event_type.value,
            "timestamp": time.time(),
            "data": data,
        }
        if self._file is not None:
            try:
                self._file.write(json.dumps(event_record) + "\n")
                self._file.flush()
            except IOError as e:
                print(f"WARNING: Failed to write event log: {e}", file=sys.stderr)

        # Call registered handlers
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(event_type, data)
                except Exception as e:
                    logger.warning(f"[EVENT] Handler error: {e}")
    
    def on(self, event_type: EventType, handler: Callable[[EventType, Dict[str, Any]], None]):
        """Register an event handler"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def off(self, event_type: EventType, handler: Callable[[EventType, Dict[str, Any]], None]):
        """Unregister an event handler"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def flush(self):
        if self._file is not None:
            try:
                self._file.flush()
            except IOError as e:
                print(f"WARNING: Failed to flush event log: {e}", file=sys.stderr)

    def close(self):
        if self._file is not None:
            try:
                self._file.close()
            except OSError as e:
                print(f"WARNING: Failed to close event log: {e}", file=sys.stderr)
            finally:
                self._file = None
