"""Abstract decision source interface."""

from abc import ABC, abstractmethod
from src.core.schema import ArmDecision


class DecisionSource(ABC):
    """Abstract interface for input sources (keyboard or EEG)."""
    
    @abstractmethod
    def read_decision(self) -> ArmDecision:
        """Read current decision from input source.
        
        Returns:
            ArmDecision with signal, confidence, source, timestamp
        """
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Get human-readable source name."""
        pass
    
    @abstractmethod
    def reset(self):
        """Reset source state (for recovery)."""
        pass

