"""
Abstract proposer interface.
Every proposer (heuristic, Gemini, future) implements this.
"""
from abc import ABC, abstractmethod
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal


class ProposerBase(ABC):
    """
    Base interface for all proposers.
    
    Contract:
    - propose() MUST return an IntentProposal (never None)
    - propose() MUST NOT have side effects
    - propose() MUST be deterministic for same inputs (heuristic)
      OR clearly non-deterministic (Gemini) with fallback
    - propose() MUST NOT raise exceptions (catch internally, return IDLE)
    """
    
    @abstractmethod
    def propose(self, scene: SceneSummary) -> IntentProposal:
        """
        Generate a proposal based on scene understanding.
        
        Args:
            scene: Frozen scene summary
            
        Returns:
            IntentProposal (never None, use IDLE for "no action")
        """
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Human-readable proposer name for logging"""
        pass
    
    def is_available(self) -> bool:
        """
        Check if proposer is ready to use.
        Override for external services (Gemini: check API key, MNE: check device).
        Default: always available.
        """
        return True



