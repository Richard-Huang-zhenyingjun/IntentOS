"""
Heuristic proposer - deterministic, no external dependencies.
Always registered as fallback in the registry.
"""
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal, ActionType


class HeuristicProposer(ProposerBase):
    """
    Deterministic rule-based proposer.
    
    This is the FALLBACK proposer - it must NEVER fail.
    No external calls, no network, no ML models.
    """
    
    def __init__(self, config: dict):
        self.config = config
        messy_cfg = config.get('scene_understanding', {}).get('messy_detection', {})
        self.min_objects = messy_cfg.get('min_objects', 3)
        self.spread_threshold = messy_cfg.get('spread_threshold', 0.18)
    
    def propose(self, scene: SceneSummary) -> IntentProposal:
        """
        Simple rule: If messy → propose CLEAN_TABLE
        Guaranteed to return valid proposal, never raises.
        """
        if scene.is_messy:
            return IntentProposal(
                action=ActionType.CLEAN_TABLE,
                description=f"Clear {len(scene.objects_on_table)} objects from table",
                source="heuristic",
                confidence=1.0,
                metadata={
                    'clutter_score': scene.clutter_score,
                    'n_objects': len(scene.objects_on_table),
                    'reason': 'messy_table_detected'
                }
            )
        
        return IntentProposal(
            action=ActionType.IDLE,
            description="Table is clean",
            source="heuristic",
            confidence=1.0,
            metadata={'reason': 'table_clean'}
        )
    
    def name(self) -> str:
        return "heuristic"
    
    def is_available(self) -> bool:
        return True  # Always available - this is the fallback
