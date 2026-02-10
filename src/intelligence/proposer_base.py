from abc import ABC, abstractmethod
from typing import Optional
from src.core.schema import ArmProposal
from src.robot.world_state import WorldState
from src.intelligence.scene_summary import SceneSummary

class ProposerBase(ABC):
    """Base interface for all proposers (heuristic, Gemini, etc.)"""
    
    @abstractmethod
    def propose(self, world: WorldState, scene: Optional[SceneSummary]) -> Optional[ArmProposal]:
        """
        Generate a proposal based on world state and scene understanding.
        
        Args:
            world: Current world state
            scene: Scene summary (may be None if not computed)
        
        Returns:
            ArmProposal with action type and metadata, or None if no action proposed
        """
        pass


