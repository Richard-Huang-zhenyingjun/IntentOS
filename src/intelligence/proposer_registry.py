"""
Proposer registry with automatic fallback.

Design:
- Register multiple proposers with priority
- Active proposer is highest-priority available proposer
- If active proposer fails, fall back to next available
- Heuristic proposer is ALWAYS registered as lowest priority (can't fail)
"""
import logging
from typing import Dict, Optional, List
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal, ActionType

logger = logging.getLogger(__name__)


class ProposerRegistry:
    """
    Manages proposer selection with automatic fallback.
    
    Priority order (highest first):
    - External proposers (Gemini, etc.) - may fail
    - Heuristic proposer - always works
    
    Usage:
        registry = ProposerRegistry()
        registry.register("heuristic", heuristic_proposer, priority=0)
        registry.register("gemini", gemini_proposer, priority=10)  # Week 4
        
        proposal = registry.propose(scene)  # Tries gemini first, falls back
    """
    
    def __init__(self):
        self._proposers: Dict[str, ProposerBase] = {}
        self._priorities: Dict[str, int] = {}
        self._fallback_name: Optional[str] = None
        
        # Week 4: FSM-state gating
        self._blocked_states: set = set()
        self._current_fsm_state: str = "IDLE"
        
        # Metrics
        self.total_proposals: int = 0
        self.fallback_count: int = 0
        self.failure_log: List[dict] = []
    
    def register(
        self,
        name: str,
        proposer: ProposerBase,
        priority: int = 0,
        is_fallback: bool = False
    ):
        """
        Register a proposer.
        
        Args:
            name: Unique identifier
            proposer: ProposerBase implementation
            priority: Higher = tried first
            is_fallback: If True, this is the last-resort proposer
        """
        self._proposers[name] = proposer
        self._priorities[name] = priority
        
        if is_fallback:
            self._fallback_name = name
        
        logger.info(f"[REGISTRY] Registered proposer '{name}' (priority={priority}, fallback={is_fallback})")
    
    def set_blocked_states(self, states: set):
        """
        Set FSM states during which external proposers are blocked.
        Only fallback (heuristic) can be used during these states.
        
        Args:
            states: Set of state names (e.g., {"EXECUTING", "CONFIRMING"})
        """
        self._blocked_states = states
        logger.info(f"[REGISTRY] External proposers blocked during: {states}")
    
    def update_fsm_state(self, state: str):
        """Update current FSM state (called by orchestrator each frame)"""
        self._current_fsm_state = state
    
    def propose(self, scene: SceneSummary) -> IntentProposal:
        """
        Get proposal with FSM-state gating.
        
        If current state is blocked, skip external proposers
        and go directly to fallback.
        
        Returns:
            IntentProposal (guaranteed non-None)
        """
        self.total_proposals += 1
        
        # Check if external proposers are blocked
        in_blocked_state = self._current_fsm_state in self._blocked_states
        
        # Sort by priority (highest first)
        sorted_names = sorted(
            self._proposers.keys(),
            key=lambda n: self._priorities[n],
            reverse=True
        )
        
        for name in sorted_names:
            proposer = self._proposers[name]
            
            # Week 4: Skip external proposers during blocked states
            if in_blocked_state and name != self._fallback_name:
                logger.debug(f"[REGISTRY] Skipping '{name}' (blocked state: {self._current_fsm_state})")
                continue
            
            # Check availability
            if not proposer.is_available():
                logger.debug(f"[REGISTRY] Proposer '{name}' not available, skipping")
                continue
            
            # Try to get proposal
            try:
                proposal = proposer.propose(scene)
                
                if proposal is not None:
                    # Week 4: Check if proposal indicates failure (IDLE with confidence=0.0)
                    # This allows Gemini to signal fallback while satisfying interface contract
                    if proposal.action == ActionType.IDLE and proposal.confidence == 0.0:
                        logger.debug(f"[REGISTRY] Proposer '{name}' returned failure signal (IDLE, confidence=0.0), trying next")
                        continue
                    
                    logger.debug(f"[REGISTRY] Proposal from '{name}': {proposal.action.value}")
                    return proposal
                    
            except Exception as e:
                logger.warning(f"[REGISTRY] Proposer '{name}' failed: {e}")
                self.failure_log.append({
                    'proposer': name,
                    'error': str(e),
                    'frame': scene.timestamp_frame
                })
                continue
        
        # All proposers failed - use fallback
        if self._fallback_name and self._fallback_name in self._proposers:
            self.fallback_count += 1
            logger.warning(f"[REGISTRY] All proposers failed, using fallback '{self._fallback_name}'")
            
            try:
                return self._proposers[self._fallback_name].propose(scene)
            except Exception as e:
                logger.error(f"[REGISTRY] Even fallback failed: {e}")
        
        # Absolute last resort
        logger.error("[REGISTRY] No proposer available, returning IDLE")
        return IntentProposal(
            action=ActionType.IDLE,
            description="No proposer available",
            source="registry_fallback",
            confidence=0.0
        )
    
    def get_active_proposer_name(self) -> str:
        """Get name of highest-priority available proposer"""
        sorted_names = sorted(
            self._proposers.keys(),
            key=lambda n: self._priorities[n],
            reverse=True
        )
        
        for name in sorted_names:
            if self._proposers[name].is_available():
                return name
        
        return self._fallback_name or "none"
    
    def get_stats(self) -> dict:
        """Get registry statistics"""
        return {
            'total_proposals': self.total_proposals,
            'fallback_count': self.fallback_count,
            'fallback_rate': (
                self.fallback_count / self.total_proposals
                if self.total_proposals > 0 else 0.0
            ),
            'registered_proposers': list(self._proposers.keys()),
            'active_proposer': self.get_active_proposer_name(),
            'recent_failures': self.failure_log[-5:]  # Last 5
        }

