"""Focus Commitment - Anti-thrash mechanism for camera scope (ENHANCED Week 7)."""

from dataclasses import dataclass
from typing import Optional, Deque
from collections import deque
from vision.focus_selector import FocusResult
from vision.tracking_schema import TrackedObject

# Week 7: New import for RankedCandidates
try:
    from src.vision.candidate_ranker import RankedCandidates
except ImportError:
    RankedCandidates = None  # Fallback for backward compatibility


@dataclass
class SwitchEvent:
    """Record of focus switch"""
    from_track_id: Optional[str]
    to_track_id: str
    timestamp: float


@dataclass
class CommitmentResult:
    """Result of commitment check"""
    allowed_primary: Optional[TrackedObject]
    commitment_active: bool
    switch_blocked: bool
    oscillation_detected: bool
    reason: str


class FocusCommitment:
    """
    Resist rapid switching between objects after stable scope established (ENHANCED Week 7)
    
    Week 2: Basic commitment to prevent thrashing
    Week 7: Add suppression awareness, stricter switching rules, RankedCandidates support
    
    Rules:
    - Once scoped, resist switching for N frames
    - New object must win decisively (score advantage)
    - Respects oscillation suppression from OscillationDetector
    - Handles ambiguity from CandidateRanker
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Week 7: Updated config keys (backward compatible)
        commitment_config = config.get('commitment', {})
        self.commitment_frames = commitment_config.get('frames_required', 
                                                       config.get('commitment_frames', 8))
        self.score_advantage = commitment_config.get('score_advantage_required',
                                                     config.get('commitment_score_advantage', 0.25))
        self.commitment_timeout = commitment_config.get('timeout_seconds',
                                                       config.get('commitment_timeout_seconds', 5.0))
        
        # Week 7: Oscillation detection now delegated to OscillationDetector
        # Keep minimal oscillation tracking for backward compatibility
        self.oscillation_window = config.get('oscillation_window_seconds', 3.0)
        self.max_switches = config.get('oscillation_max_switches', 3)
        self.oscillation_cooldown = config.get('oscillation_cooldown_seconds', 2.0)
        
        # State
        self.committed_track_id: Optional[str] = None
        self.commitment_start_time: Optional[float] = None
        self.commitment_frame_counter = 0
        
        # Switch tracking
        self.switch_history: Deque[SwitchEvent] = deque(maxlen=10)
        self.oscillation_suppressed_tracks = set()
        self.oscillation_suppressed_until: Optional[float] = None
        
        # Switch request tracking (Week 7: stricter persistence)
        self.switch_request_track_id: Optional[str] = None
        self.switch_request_counter = 0
        
        # Week 7: Additional state
        self.frames_required = self.commitment_frames  # Alias for clarity
    
    def apply_ranked(self,
                     current_scoped_id: Optional[str],
                     ranked_candidates: 'RankedCandidates',
                     timestamp: float) -> CommitmentResult:
        """
        Apply commitment rules (ENHANCED Week 7)
        
        New for Week 7:
        - Uses RankedCandidates instead of FocusResult
        - Respects oscillation suppression (from external OscillationDetector)
        - Requires decisive score advantage for switch
        - Handles ambiguity detection
        
        Args:
            current_scoped_id: Currently scoped object ID (or None)
            ranked_candidates: Result from CandidateRanker
            timestamp: Current timestamp
        
        Returns:
            CommitmentResult with allowed primary or block reason
        """
        
        # === CASE 1: Ambiguity detected ===
        if ranked_candidates.ambiguity_detected:
            self._reset_commitment()
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=False,
                switch_blocked=False,
                oscillation_detected=False,
                reason="Ambiguity detected - waiting for clarity"
            )
        
        # === CASE 2: No primary candidate ===
        if ranked_candidates.primary_choice is None:
            self._reset_commitment()
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=False,
                switch_blocked=False,
                oscillation_detected=False,
                reason=ranked_candidates.reason
            )
        
        primary_id = ranked_candidates.primary_choice.track_id
        
        # === CASE 3: Same as committed → allow ===
        if primary_id == self.committed_track_id or self.committed_track_id is None:
            # Update commitment
            if self.committed_track_id is None:
                self.committed_track_id = primary_id
                self.commitment_start_time = timestamp
                self.commitment_frame_counter = 1
            else:
                self.commitment_frame_counter += 1
            
            # Check timeout
            if (self.commitment_start_time and 
                (timestamp - self.commitment_start_time) > self.commitment_timeout):
                self._reset_commitment()
            
            return CommitmentResult(
                allowed_primary=ranked_candidates.primary_choice,
                commitment_active=True,
                switch_blocked=False,
                oscillation_detected=False,
                reason=f"Committed to {primary_id}"
            )
        
        # === CASE 4: Different from committed → check if switch allowed ===
        
        # Check if in commitment period
        if self.commitment_frame_counter < self.frames_required:
            # In commitment period - need decisive advantage to switch
            
            # Check if current committed object is runner-up
            if (ranked_candidates.runner_up and 
                ranked_candidates.runner_up.track_id == self.committed_track_id):
                
                # Check score advantage (Week 7: stricter requirement)
                if ranked_candidates.margin >= self.score_advantage:
                    # New object wins decisively - allow switch
                    self._record_switch(self.committed_track_id, primary_id, timestamp)
                    return CommitmentResult(
                        allowed_primary=ranked_candidates.primary_choice,
                        commitment_active=False,  # New commitment starts
                        switch_blocked=False,
                        oscillation_detected=False,
                        reason=f"Decisive switch: margin={ranked_candidates.margin:.3f} > {self.score_advantage}"
                    )
            
            # Track switch requests
            if primary_id == self.switch_request_track_id:
                self.switch_request_counter += 1
            else:
                self.switch_request_track_id = primary_id
                self.switch_request_counter = 1
            
            # Allow switch if requested persistently
            if self.switch_request_counter >= self.frames_required:
                self._record_switch(self.committed_track_id, primary_id, timestamp)
                return CommitmentResult(
                    allowed_primary=ranked_candidates.primary_choice,
                    commitment_active=False,
                    switch_blocked=False,
                    oscillation_detected=False,
                    reason=f"Persistent switch request granted ({self.switch_request_counter} frames)"
                )
            
            # Block switch
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=True,
                switch_blocked=True,
                oscillation_detected=False,
                reason=f"Commitment hold: {self.commitment_frame_counter}/{self.frames_required} frames, switch requests: {self.switch_request_counter}"
            )
        
        # Commitment period expired - allow switch
        self._record_switch(self.committed_track_id, primary_id, timestamp)
        return CommitmentResult(
            allowed_primary=ranked_candidates.primary_choice,
            commitment_active=False,
            switch_blocked=False,
            oscillation_detected=False,
            reason="Commitment expired - switch allowed"
        )
    
    def apply(self,
              current_scoped_id: Optional[str],
              focus_result: FocusResult,
              timestamp: float) -> CommitmentResult:
        """
        Apply commitment rules to focus result (LEGACY Week 2 method)
        
        Kept for backward compatibility with existing code.
        New code should use apply_ranked() with RankedCandidates.
        
        May block switching if:
        - In commitment period
        - New object doesn't win decisively
        - Oscillation detected
        """
        
        # Update commitment state
        if current_scoped_id != self.committed_track_id:
            # New scope or no scope
            if current_scoped_id is not None:
                self.committed_track_id = current_scoped_id
                self.commitment_start_time = timestamp
                self.commitment_frame_counter = 0
        
        # Increment commitment counter
        if self.committed_track_id is not None and current_scoped_id == self.committed_track_id:
            self.commitment_frame_counter += 1
        
        # Check commitment timeout
        if (self.commitment_start_time and 
            (timestamp - self.commitment_start_time) > self.commitment_timeout):
            # Release commitment
            self.committed_track_id = None
            self.commitment_frame_counter = 0
        
        # Check oscillation cooldown
        if (self.oscillation_suppressed_until and 
            timestamp > self.oscillation_suppressed_until):
            # Clear suppression
            self.oscillation_suppressed_tracks.clear()
            self.oscillation_suppressed_until = None
        
        # Case 1: No primary in focus result
        if focus_result.primary_object is None:
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=self.committed_track_id is not None,
                switch_blocked=False,
                oscillation_detected=False,
                reason=focus_result.reason
            )
        
        primary_id = focus_result.primary_object.track_id
        
        # Case 2: Check oscillation suppression
        if primary_id in self.oscillation_suppressed_tracks:
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=self.committed_track_id is not None,
                switch_blocked=True,
                oscillation_detected=True,
                reason=f"oscillation suppression active for {primary_id}"
            )
        
        # Case 3: Same as committed → allow
        if primary_id == self.committed_track_id or self.committed_track_id is None:
            return CommitmentResult(
                allowed_primary=focus_result.primary_object,
                commitment_active=self.committed_track_id is not None,
                switch_blocked=False,
                oscillation_detected=False,
                reason=focus_result.reason
            )
        
        # Case 4: Different from committed → check if switch allowed
        # Must be in commitment period
        if self.commitment_frame_counter < self.commitment_frames:
            # In commitment - check if new object wins decisively
            if focus_result.primary_candidate and focus_result.runner_up_candidate:
                # Check if current committed track is the runner-up
                if (focus_result.runner_up_object and 
                    focus_result.runner_up_object.track_id == self.committed_track_id):
                    # Check score advantage
                    if focus_result.score_margin >= self.score_advantage:
                        # New object wins decisively - allow switch
                        self._record_switch(
                            from_id=self.committed_track_id,
                            to_id=primary_id,
                            timestamp=timestamp
                        )
                        
                        # Check for oscillation
                        if self._detect_oscillation(timestamp):
                            return CommitmentResult(
                                allowed_primary=None,
                                commitment_active=True,
                                switch_blocked=True,
                                oscillation_detected=True,
                                reason="oscillation detected - suppressing both objects"
                            )
                        
                        return CommitmentResult(
                            allowed_primary=focus_result.primary_object,
                            commitment_active=False,  # New commitment starts
                            switch_blocked=False,
                            oscillation_detected=False,
                            reason=f"decisive switch to {primary_id}"
                        )
            
            # Track switch requests
            if primary_id == self.switch_request_track_id:
                self.switch_request_counter += 1
            else:
                self.switch_request_track_id = primary_id
                self.switch_request_counter = 1
            
            # Allow switch if requested consistently
            if self.switch_request_counter >= self.commitment_frames:
                self._record_switch(
                    from_id=self.committed_track_id,
                    to_id=primary_id,
                    timestamp=timestamp
                )
                
                # Check oscillation
                if self._detect_oscillation(timestamp):
                    return CommitmentResult(
                        allowed_primary=None,
                        commitment_active=True,
                        switch_blocked=True,
                        oscillation_detected=True,
                        reason="oscillation detected"
                    )
                
                return CommitmentResult(
                    allowed_primary=focus_result.primary_object,
                    commitment_active=False,
                    switch_blocked=False,
                    oscillation_detected=False,
                    reason=f"persistent switch request granted"
                )
            
            # Block switch
            return CommitmentResult(
                allowed_primary=None,
                commitment_active=True,
                switch_blocked=True,
                oscillation_detected=False,
                reason=f"commitment hold: {self.commitment_frame_counter}/{self.commitment_frames}"
            )
        
        # Commitment period expired - allow switch
        self._record_switch(
            from_id=self.committed_track_id,
            to_id=primary_id,
            timestamp=timestamp
        )
        
        return CommitmentResult(
            allowed_primary=focus_result.primary_object,
            commitment_active=False,
            switch_blocked=False,
            oscillation_detected=False,
            reason="commitment expired - switch allowed"
        )
    
    def _reset_commitment(self):
        """Reset commitment state (Week 7 helper)"""
        self.committed_track_id = None
        self.commitment_start_time = None
        self.commitment_frame_counter = 0
        self.switch_request_counter = 0
        self.switch_request_track_id = None
    
    def _record_switch(self, from_id: Optional[str], to_id: str, timestamp: float):
        """
        Record a focus switch (ENHANCED Week 7)
        
        Updates commitment to new object and records switch event.
        """
        # Record switch event
        self.switch_history.append(SwitchEvent(
            from_track_id=from_id,
            to_track_id=to_id,
            timestamp=timestamp
        ))
        
        # Update commitment to new object (Week 7)
        self.committed_track_id = to_id
        self.commitment_start_time = timestamp
        self.commitment_frame_counter = 1
        self.switch_request_counter = 0
        self.switch_request_track_id = None
    
    def _detect_oscillation(self, current_time: float) -> bool:
        """
        Detect rapid back-and-forth switching
        
        Returns True if oscillation detected
        """
        # Get recent switches
        recent_switches = [
            s for s in self.switch_history
            if (current_time - s.timestamp) <= self.oscillation_window
        ]
        
        if len(recent_switches) < self.max_switches:
            return False
        
        # Check if oscillating between two tracks
        track_ids = set()
        for switch in recent_switches:
            if switch.from_track_id:
                track_ids.add(switch.from_track_id)
            track_ids.add(switch.to_track_id)
        
        if len(track_ids) == 2:
            # Oscillating between exactly 2 tracks - suppress both
            self.oscillation_suppressed_tracks = track_ids
            self.oscillation_suppressed_until = current_time + self.oscillation_cooldown
            return True
        
        return False
    
    def reset(self):
        """Clear all commitment state"""
        self.committed_track_id = None
        self.commitment_start_time = None
        self.commitment_frame_counter = 0
        self.switch_history.clear()
        self.oscillation_suppressed_tracks.clear()
        self.oscillation_suppressed_until = None
        self.switch_request_track_id = None
        self.switch_request_counter = 0
    
    def get_statistics(self) -> dict:
        """Get commitment statistics (Week 7)"""
        return {
            'committed_track_id': self.committed_track_id,
            'commitment_active': self.committed_track_id is not None,
            'commitment_frame_counter': self.commitment_frame_counter,
            'frames_required': self.frames_required,
            'switch_request_counter': self.switch_request_counter,
            'total_switches': len(self.switch_history),
            'oscillation_suppressed_count': len(self.oscillation_suppressed_tracks)
        }

