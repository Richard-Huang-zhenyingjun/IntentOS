"""
Frozen proposal contract.
Every proposer (heuristic, Gemini, future) outputs this shape.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class ActionType(Enum):
    """High-level action types the system can propose"""
    IDLE = "idle"
    CLEAN_TABLE = "clean_table"
    # Week 5+: Gemini may suggest these
    ORGANIZE_BY_CATEGORY = "organize_by_category"
    CLEAR_SPECIFIC = "clear_specific"


@dataclass(frozen=True)
class IntentProposal:
    """
    Immutable proposal from any proposer.
    
    Key design: ALL proposers output the same shape.
    Gemini proposal looks identical to heuristic proposal.
    The orchestrator doesn't know (or care) which proposer generated it.
    
    Why frozen=True:
    - Prevents accidental mutation mid-pipeline
    - Ensures proposer output is stable
    - Forces creating new proposal each frame (which you should anyway)
    
    Why metadata is Dict (not frozen):
    - Dict is mutable but the dataclass itself is frozen
    - This allows proposers to attach arbitrary structured data
    - Compiler/executor can read but not modify the proposal
    """
    # Required
    action: ActionType
    description: str
    
    # Source tracking (for debugging and overlay)
    source: str = "unknown"  # "heuristic", "gemini", etc.
    confidence: float = 1.0  # 0.0-1.0, heuristic always 1.0
    
    # Metadata (proposer-specific details)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Week 5+: Gemini plan hints (compiler validates these)
    suggested_object_ids: Optional[List[int]] = None
    suggested_bin_zone: Optional[tuple] = None
    risk_flags: Optional[List[str]] = None



