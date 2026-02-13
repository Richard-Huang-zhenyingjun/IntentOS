"""
Abstract EEG device interface.
Real BrainLink and replay both implement this.
"""
from abc import ABC, abstractmethod
from typing import Optional, Callable
from src.input.eeg.types import EEGSample


class EEGDeviceBase(ABC):
    """
    Base interface for EEG data sources.
    
    Contract:
    - start() begins data acquisition (may spawn thread)
    - stop() cleanly stops
    - set_callback() registers sample handler
    - Implementations handle connection, reconnection, errors internally
    """
    
    @abstractmethod
    def start(self):
        """Begin data acquisition"""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop data acquisition and clean up"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if device is actively streaming"""
        pass
    
    @abstractmethod
    def set_callback(self, callback: Callable[[EEGSample], None]):
        """Register callback for each new sample"""
        pass
    
    @abstractmethod
    def get_sfreq(self) -> float:
        """Return actual/expected sampling frequency"""
        pass



