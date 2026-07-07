"""
Frozen interface contracts for the Intent Interface system.

All modules depend on these interfaces.
No module outside src/interfaces/ should be imported by src/core/.
"""
from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.hand_state import HandState
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.plan_compiler_base import PlanCompilerBase
from src.interfaces.decision_source_base import DecisionSourceBase, Decision
from src.interfaces.primitive import Primitive, PrimitiveType
from src.interfaces.errors import ExecStatus, ErrorCode
from src.interfaces.world_artifacts import WorldArtifacts

__all__ = [
    'SceneSummary', 'ObjectInfo', 'HandState',
    'IntentProposal', 'ActionType',
    'ProposerBase',
    'PlanCompilerBase',
    'DecisionSourceBase', 'Decision',
    'Primitive', 'PrimitiveType',
    'ExecStatus', 'ErrorCode',
    'WorldArtifacts',
]
