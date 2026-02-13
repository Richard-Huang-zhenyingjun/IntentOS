"""
Abstract decision source interface.

Sources are "dumb" — they read raw input and report it.
Sources do NOT filter, debounce, or make policy decisions.
That's the router's and filter's job.
"""
from abc import ABC, abstractmethod
from src.input.types import RawSourceReading, SourceType


class DecisionSourceBase(ABC):
    """
    Base interface for all decision input sources.
    
    Contract:
    - read_raw() MUST NOT block
    - read_raw() returns raw input state (may be noisy)
    - Sources report what they see, not what should happen
    - Quality is source-estimated confidence (keyboard=1.0, EEG=variable)
    """
    
    @abstractmethod
    def read_raw(self) -> RawSourceReading:
        """Read current raw input state (non-blocking)"""
        pass
    
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return source type identifier"""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging"""
        pass
    
    def is_available(self) -> bool:
        """Check if source is connected and ready"""
        return True



