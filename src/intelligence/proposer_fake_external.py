"""
Fake external proposer for testing fallback behavior.
Simulates an external service (Gemini) that can fail on demand.
"""
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal, ActionType


class FakeExternalProposer(ProposerBase):
    """
    Test-only proposer that simulates external service behavior.
    
    Usage:
        fake = FakeExternalProposer()
        fake.set_available(False)  # Simulate API down
        fake.set_fail_on_next()    # Simulate API error
    """
    
    def __init__(self):
        self._available = True
        self._fail_on_next = False
        self._call_count = 0
    
    def propose(self, scene: SceneSummary) -> IntentProposal:
        self._call_count += 1
        
        if self._fail_on_next:
            self._fail_on_next = False
            raise ConnectionError("Simulated external service failure")
        
        # Return same as heuristic but with different source
        if scene.is_messy:
            return IntentProposal(
                action=ActionType.CLEAN_TABLE,
                description=f"[FAKE EXTERNAL] Clean {len(scene.objects_on_table)} objects",
                source="fake_external",
                confidence=0.85,
                metadata={'simulated': True}
            )
        
        return IntentProposal(
            action=ActionType.IDLE,
            description="[FAKE EXTERNAL] Table clean",
            source="fake_external",
            confidence=0.9
        )
    
    def name(self) -> str:
        return "fake_external"
    
    def is_available(self) -> bool:
        return self._available
    
    # Test control methods
    def set_available(self, available: bool):
        self._available = available
    
    def set_fail_on_next(self):
        self._fail_on_next = True
    
    def get_call_count(self) -> int:
        return self._call_count



