import time
from src.interfaces.decision_source_base import DecisionSourceBase, Decision
from src.core.schema import ArmDecision, DecisionSignal  # For backward compatibility


class FakeDecisionSource(DecisionSourceBase):
    """Test-only decision source - implements DecisionSourceBase"""
    
    def __init__(self):
        self.frame = 0
        self.confirm_frames = []  # Frames to send CONFIRM signal
        self.cancel_frames = []   # Frames to send CANCEL signal
    
    def set_confirm_on_frame(self, frame: int):
        """Schedule a confirm signal on specific frame"""
        self.confirm_frames.append(frame)
        # Sort to ensure deterministic behavior
        self.confirm_frames.sort()
    
    def set_cancel_on_frame(self, frame: int):
        """Schedule a cancel signal on specific frame"""
        self.cancel_frames.append(frame)
        # Sort to ensure deterministic behavior
        self.cancel_frames.sort()
    
    def read(self) -> Decision:
        """Return decision for current frame (Week 3: interface method)"""
        self.frame += 1
        
        # Determine signal based on scheduled frames
        confirm = self.frame in self.confirm_frames
        cancel = self.frame in self.cancel_frames
        
        return Decision(
            confirm=confirm,
            cancel=cancel,
            quality=1.0,  # Perfect quality for testing
            source="test"
        )
    
    def read_decision(self) -> ArmDecision:
        """Backward compatibility method (Week 3: deprecated)"""
        decision = self.read()
        signal = DecisionSignal.CONFIRM if decision.confirm else (
            DecisionSignal.CANCEL if decision.cancel else DecisionSignal.IDLE
        )
        return ArmDecision(
            signal=signal,
            confidence=decision.quality,
            source=decision.source,
            timestamp=time.time()
        )
    
    def name(self) -> str:
        """Human-readable source name (Week 3: interface method)"""
        return "fake_test"
    
    def get_source_name(self) -> str:
        """Backward compatibility method (Week 3: deprecated)"""
        return "fake (testing)"
    
    def reset(self):
        """Reset source state (for recovery)."""
        self.frame = 0
        self.confirm_frames = []
        self.cancel_frames = []
    
    def reset_frame_counter(self):
        """Reset frame counter without clearing scheduled signals."""
        self.frame = 0
