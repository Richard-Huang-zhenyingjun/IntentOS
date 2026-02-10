"""
Abstract decision source interface.
Keyboard, EEG, and test fakes all implement this.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """
    Immutable decision from any input source.
    
    Replaces Week 1-2's ArmDecision with a cleaner name.
    
    Why frozen=True:
    - Prevents accidental mutation mid-pipeline
    - Ensures decision state is stable
    - Forces creating new Decision each read (which you should anyway)
    """
    confirm: bool = False
    cancel: bool = False
    quality: float = 1.0  # 1.0 for keyboard, variable for EEG
    source: str = "unknown"  # "keyboard", "eeg", "test"


class DecisionSourceBase(ABC):
    """
    Base interface for all decision input sources.
    
    Contract:
    - read() MUST NOT block (return immediately)
    - read() MUST return a Decision (never None)
    - quality indicates confidence (keyboard always 1.0)
    """
    
    @abstractmethod
    def read(self) -> Decision:
        """Read current decision state (non-blocking)"""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name"""
        pass


