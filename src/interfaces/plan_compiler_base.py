"""
Abstract plan compiler interface.
"""
from abc import ABC, abstractmethod
from typing import List
from src.interfaces.intent_proposal import IntentProposal
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.primitive import Primitive


class PlanCompilerBase(ABC):
    """
    Compiles proposals into validated primitive sequences.
    
    Contract:
    - compile() returns empty list if proposal is invalid
    - compile() MUST validate all targets (workspace bounds, reachability)
    - compile() MUST NOT call external services
    - compile() is deterministic
    """
    
    @abstractmethod
    def compile(
        self,
        proposal: IntentProposal,
        scene: SceneSummary
    ) -> List[Primitive]:
        """
        Compile proposal into validated primitives.
        
        Returns:
            List of primitives (empty if validation fails)
        """
        pass
    
    @abstractmethod
    def compile_for_object(
        self,
        object_id: int,
        scene: SceneSummary
    ) -> List[Primitive]:
        """
        Compile primitives for a specific object.
        Used by TaskExecutor for multi-object loop.
        
        Returns:
            List of primitives (empty if object unreachable)
        """
        pass

