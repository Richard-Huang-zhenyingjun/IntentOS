"""
Video Session Logger - Week 7

Logs frame-by-frame system state for deterministic replay and debugging.
Enables post-hoc analysis of multi-object robustness and failure recovery.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import json
from pathlib import Path


@dataclass
class FrameSnapshot:
    """
    Complete snapshot of system state for one frame
    
    Enables deterministic replay and debugging.
    Captures all Week 7 multi-object and robustness state.
    """
    # Frame metadata
    frame_id: int
    timestamp: float
    
    # Multi-object state
    num_tracked_objects: int
    tracked_object_ids: List[str]
    
    # Ranking
    primary_id: Optional[str]
    primary_label: Optional[str]
    primary_score: Optional[float]
    runner_up_id: Optional[str]
    runner_up_score: Optional[float]
    ambiguity_detected: bool
    margin: float
    
    # Oscillation
    oscillating: bool
    suppressed_ids: List[str]
    
    # Scope
    scoped_object_id: Optional[str]
    scope_stable: bool
    
    # Gesture
    hand_detected: bool
    pinching: bool
    pinch_frames_held: int
    
    # System state
    system_state: str
    execution_allowed: bool
    
    # Pause/recovery
    paused: bool
    pause_reason: Optional[str]
    
    # State changes (events this frame)
    events: List[str]


class VideoSessionLogger:
    """
    Log frame-by-frame system state for replay
    
    Week 7: Critical for debugging multi-object robustness
    
    Design:
    - Efficient: logs only changes by default (not every frame)
    - JSONL format: one JSON object per line (easy parsing)
    - Complete state: captures all Week 7 features
    - Deterministic replay: enough info to reproduce behavior
    
    Usage:
        logger = VideoSessionLogger(config, session_id="demo_001")
        
        for frame in video:
            ui_snapshot = orchestrator.step(timestamp)
            logger.log_frame(ui_snapshot)
        
        logger.close()
    """
    
    def __init__(self, config: dict, session_id: str):
        self.config = config
        self.session_id = session_id
        
        # Config
        self.enabled = config.get('enabled', True)
        self.log_every_frame = config.get('log_every_frame', False)
        self.log_candidate_scores = config.get('log_candidate_scores', True)
        self.log_pause_triggers = config.get('log_pause_triggers', True)
        self.log_oscillation_events = config.get('log_oscillation_events', True)
        
        # Output path
        self.output_dir = Path(config.get('output_dir', './logs/video_sessions'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_file = self.output_dir / f"session_{session_id}.jsonl"
        
        # State tracking (for change detection)
        self.last_snapshot: Optional[FrameSnapshot] = None
        self.frame_count = 0
        self.snapshots_logged = 0
        
        # Open file
        if self.enabled:
            self.file_handle = open(self.session_file, 'w')
            # Write session header
            self._write_header()
    
    def _write_header(self):
        """Write session header (metadata)"""
        header = {
            '_type': 'session_header',
            'session_id': self.session_id,
            'config': {
                'log_every_frame': self.log_every_frame,
                'log_candidate_scores': self.log_candidate_scores,
                'log_pause_triggers': self.log_pause_triggers
            }
        }
        self.file_handle.write(json.dumps(header) + '\n')
        self.file_handle.flush()
    
    def log_frame(self, ui_snapshot: Dict[str, Any]) -> Optional[FrameSnapshot]:
        """
        Log frame snapshot
        
        Args:
            ui_snapshot: Current UI snapshot from orchestrator
        
        Returns:
            FrameSnapshot if logged, None if skipped
        """
        if not self.enabled:
            return None
        
        self.frame_count += 1
        
        # Extract relevant info
        snapshot = self._extract_snapshot(ui_snapshot)
        
        # Detect changes
        if not self.log_every_frame and self.last_snapshot:
            if not self._has_significant_change(self.last_snapshot, snapshot):
                # No significant change - skip
                return None
        
        # Log snapshot
        self._write_snapshot(snapshot)
        self.snapshots_logged += 1
        
        self.last_snapshot = snapshot
        return snapshot
    
    def _extract_snapshot(self, ui_snapshot: Dict[str, Any]) -> FrameSnapshot:
        """Extract FrameSnapshot from UI snapshot"""
        
        # Multi-object
        mo = ui_snapshot.get('multi_object', {})
        
        # Oscillation
        osc = ui_snapshot.get('oscillation', {})
        
        # Scope
        scope = ui_snapshot.get('scope', {})
        
        # Gesture
        gesture = ui_snapshot.get('gesture', {})
        
        # Recovery
        recovery = ui_snapshot.get('recovery', {})
        
        # Events (from last frame)
        events = ui_snapshot.get('frame_events', [])
        
        return FrameSnapshot(
            frame_id=self.frame_count,
            timestamp=ui_snapshot.get('timestamp', 0.0),
            
            # Multi-object
            num_tracked_objects=mo.get('num_candidates', 0),
            tracked_object_ids=mo.get('all_candidate_ids', []),
            
            # Ranking
            primary_id=mo.get('primary_id'),
            primary_label=mo.get('primary_label'),
            primary_score=mo.get('primary_score'),
            runner_up_id=mo.get('runner_up_id'),
            runner_up_score=mo.get('runner_up_score'),
            ambiguity_detected=mo.get('ambiguity_detected', False),
            margin=mo.get('margin', 0.0),
            
            # Oscillation
            oscillating=osc.get('oscillating', False),
            suppressed_ids=osc.get('suppressed_ids', []),
            
            # Scope
            scoped_object_id=scope.get('object_id'),
            scope_stable=scope.get('stable', False),
            
            # Gesture
            hand_detected=gesture.get('hand_detected', False),
            pinching=gesture.get('pinching', False),
            pinch_frames_held=gesture.get('frames_held', 0),
            
            # System state
            system_state=ui_snapshot.get('system_state', 'unknown'),
            execution_allowed=ui_snapshot.get('execution_allowed', False),
            
            # Pause
            paused=recovery.get('paused', False),
            pause_reason=recovery.get('reason'),
            
            # Events
            events=events
        )
    
    def _has_significant_change(self, prev: FrameSnapshot, curr: FrameSnapshot) -> bool:
        """
        Check if frame has significant changes worth logging
        
        Logs on any of:
        - System state change
        - Primary object change
        - Pause state change
        - Ambiguity state change
        - Oscillation state change
        - Any events occurred
        - Pinch state change
        
        This keeps logs small while capturing all important state transitions.
        """
        
        # System state changed
        if curr.system_state != prev.system_state:
            return True
        
        # Primary object changed
        if curr.primary_id != prev.primary_id:
            return True
        
        # Pause state changed
        if curr.paused != prev.paused:
            return True
        
        # Ambiguity state changed
        if curr.ambiguity_detected != prev.ambiguity_detected:
            return True
        
        # Oscillation state changed
        if curr.oscillating != prev.oscillating:
            return True
        
        # Pinch state changed
        if curr.pinching != prev.pinching:
            return True
        
        # Any events occurred
        if len(curr.events) > 0:
            return True
        
        # Hand detection changed
        if curr.hand_detected != prev.hand_detected:
            return True
        
        # Otherwise, skip (no significant change)
        return False
    
    def _write_snapshot(self, snapshot: FrameSnapshot):
        """Write snapshot to file as JSON line"""
        snapshot_dict = asdict(snapshot)
        snapshot_dict['_type'] = 'frame_snapshot'
        line = json.dumps(snapshot_dict)
        self.file_handle.write(line + '\n')
        self.file_handle.flush()
    
    def log_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        Log a custom event (outside of frame snapshots)
        
        Useful for logging important events that aren't tied to a specific frame.
        
        Args:
            event_type: Type of event (e.g., "oscillation_detected", "pause_triggered")
            event_data: Event-specific data
        """
        if not self.enabled:
            return
        
        event = {
            '_type': 'event',
            'event_type': event_type,
            'frame_id': self.frame_count,
            **event_data
        }
        line = json.dumps(event)
        self.file_handle.write(line + '\n')
        self.file_handle.flush()
    
    def close(self):
        """Close session log file"""
        if self.enabled and hasattr(self, 'file_handle') and self.file_handle:
            # Write session footer
            footer = {
                '_type': 'session_footer',
                'session_id': self.session_id,
                'total_frames': self.frame_count,
                'snapshots_logged': self.snapshots_logged,
                'compression_ratio': self.snapshots_logged / max(1, self.frame_count)
            }
            self.file_handle.write(json.dumps(footer) + '\n')
            self.file_handle.close()
    
    def get_statistics(self) -> dict:
        """Get logging statistics"""
        return {
            'session_id': self.session_id,
            'frame_count': self.frame_count,
            'snapshots_logged': self.snapshots_logged,
            'compression_ratio': self.snapshots_logged / max(1, self.frame_count),
            'session_file': str(self.session_file),
            'enabled': self.enabled
        }
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.close()


# Replay helper functions

def load_session(session_file: Path) -> List[Dict[str, Any]]:
    """
    Load a session log file
    
    Args:
        session_file: Path to session JSONL file
    
    Returns:
        List of parsed JSON objects (header, snapshots, events, footer)
    """
    records = []
    with open(session_file, 'r') as f:
        for line in f:
            records.append(json.loads(line.strip()))
    return records


def get_frame_snapshots(session_file: Path) -> List[FrameSnapshot]:
    """
    Load only frame snapshots from session
    
    Args:
        session_file: Path to session JSONL file
    
    Returns:
        List of FrameSnapshot objects
    """
    records = load_session(session_file)
    snapshots = []
    for record in records:
        if record.get('_type') == 'frame_snapshot':
            # Remove _type field
            record.pop('_type')
            # Convert to FrameSnapshot
            snapshot = FrameSnapshot(**record)
            snapshots.append(snapshot)
    return snapshots


def get_session_statistics(session_file: Path) -> Dict[str, Any]:
    """
    Get session statistics from log file
    
    Args:
        session_file: Path to session JSONL file
    
    Returns:
        Dictionary with session statistics
    """
    records = load_session(session_file)
    
    header = None
    footer = None
    frame_count = 0
    event_count = 0
    
    for record in records:
        if record.get('_type') == 'session_header':
            header = record
        elif record.get('_type') == 'session_footer':
            footer = record
        elif record.get('_type') == 'frame_snapshot':
            frame_count += 1
        elif record.get('_type') == 'event':
            event_count += 1
    
    return {
        'session_id': header.get('session_id') if header else None,
        'total_frames': footer.get('total_frames') if footer else frame_count,
        'snapshots_logged': frame_count,
        'events_logged': event_count,
        'compression_ratio': footer.get('compression_ratio') if footer else None
    }




