"""
Deterministic fake source for headless testing.
Replaces Week 2's FakeDecisionSource with DecisionFrame interface.
"""
from src.input.source_base import DecisionSourceBase
from src.input.types import RawSourceReading, DecisionIntent, SourceType


class FakeSource(DecisionSourceBase):
    """
    Programmatic decision source for tests.
    Schedules confirms/cancels on specific frames.
    """
    
    def __init__(self):
        self.frame = 0
        self.confirm_frames = set()
        self.cancel_frames = set()
    
    def set_confirm_on_frame(self, frame: int):
        self.confirm_frames.add(frame)
    
    def set_cancel_on_frame(self, frame: int):
        self.cancel_frames.add(frame)
    
    def read_raw(self) -> RawSourceReading:
        self.frame += 1
        
        if self.frame in self.cancel_frames:
            return RawSourceReading(
                intent=DecisionIntent.CANCEL,
                source_type=SourceType.TEST,
                quality=1.0,
                raw_pressed=True,
            )
        
        if self.frame in self.confirm_frames:
            return RawSourceReading(
                intent=DecisionIntent.CONFIRM,
                source_type=SourceType.TEST,
                quality=1.0,
                raw_pressed=True,
            )
        
        return RawSourceReading(
            intent=DecisionIntent.NONE,
            source_type=SourceType.TEST,
            quality=1.0,
        )
    
    def source_type(self) -> SourceType:
        return SourceType.TEST
    
    def name(self) -> str:
        return "fake_test"


