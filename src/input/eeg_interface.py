"""
EEG interface - abstract protocol for decision sources.
Week 6: Define interface (mock implementation).
Week 7+: Real BrainLink integration.
"""

from abc import ABC, abstractmethod
from intent_core.arm_intent_schema import DecisionSignal


class EEGDecisionSource(ABC):
    """
    Abstract interface for EEG/BCI decision sources.
    
    Week 6: Implemented by MockEEG (keyboard passthrough).
    Week 7+: Implemented by BrainLinkEEG (real BCI).
    
    Contract: Always outputs CONFIRM / CANCEL / IDLE only.
    Never outputs direct motor commands or action selection.
    """
    
    @abstractmethod
    def start(self) -> bool:
        """
        Initialize and start the decision source.
        
        Returns:
            True if started successfully
        """
        pass
    
    @abstractmethod
    def read_signal(self) -> DecisionSignal:
        """
        Read current decision signal.
        
        Returns:
            DecisionSignal (CONFIRM / CANCEL / IDLE)
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Release resources and stop."""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """
        Get human-readable source name.
        
        Returns:
            Source name (e.g., "MockEEG", "BrainLink")
        """
        pass
    
    @abstractmethod
    def get_confidence(self) -> float:
        """
        Get confidence of last reading (if applicable).
        
        Returns:
            Confidence [0, 1], or 1.0 if not applicable
        """
        pass

