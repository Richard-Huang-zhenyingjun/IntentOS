"""
Strict parser for Gemini responses.

THIS IS THE SAFETY BOUNDARY.
Everything Gemini returns is untrusted input.
Parser must NEVER throw unhandled exceptions.
Parser returns None for ANY invalid input.
"""
import json
import logging
from typing import Optional, Set
from src.interfaces.intent_proposal import IntentProposal, ActionType

logger = logging.getLogger(__name__)

# Allowed values (whitelist, not blacklist)
ALLOWED_PROPOSAL_TYPES = {"CLEAN_TABLE", "NONE"}
ALLOWED_TOP_LEVEL_KEYS = {"proposal_type", "object_ids", "rationale"}
MAX_OBJECT_IDS = 20
MAX_RATIONALE_LENGTH = 500
MAX_RAW_LENGTH = 10000


class ParseResult:
    """Result of parsing attempt, with rejection reason if failed"""
    
    def __init__(
        self,
        proposal: Optional[IntentProposal] = None,
        rejected: bool = False,
        reason: str = ""
    ):
        self.proposal = proposal
        self.rejected = rejected
        self.reason = reason
    
    @property
    def success(self) -> bool:
        return self.proposal is not None and not self.rejected


def parse_gemini_response(
    raw_text: str,
    valid_object_ids: Optional[Set[int]] = None
) -> ParseResult:
    """
    Parse Gemini raw text into IntentProposal.
    
    This function NEVER raises exceptions.
    Returns ParseResult with rejection reason on ANY failure.
    
    Args:
        raw_text: Raw text from Gemini API
        valid_object_ids: Set of object IDs that exist in current world
                         (if provided, filters out invalid IDs)
    
    Returns:
        ParseResult with proposal or rejection reason
    """
    try:
        return _parse_inner(raw_text, valid_object_ids)
    except Exception as e:
        logger.warning(f"[PARSER] Unexpected exception: {e}")
        return ParseResult(rejected=True, reason=f"unexpected_exception: {e}")


def _parse_inner(
    raw_text: str,
    valid_object_ids: Optional[Set[int]]
) -> ParseResult:
    """Inner parsing logic (may raise, caught by outer)"""
    
    # Step 1: Length check
    if not raw_text or len(raw_text) > MAX_RAW_LENGTH:
        return ParseResult(
            rejected=True,
            reason=f"length_invalid: {len(raw_text) if raw_text else 0}"
        )
    
    # Step 2: Strip whitespace and common wrapper artifacts
    cleaned = raw_text.strip()
    
    # Remove markdown code fences if Gemini wraps in them
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    
    # Step 3: JSON parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return ParseResult(
            rejected=True,
            reason=f"json_decode_error: {e}"
        )
    
    # Step 4: Must be a dict (not list, string, etc.)
    if not isinstance(data, dict):
        return ParseResult(
            rejected=True,
            reason=f"not_object: type={type(data).__name__}"
        )
    
    # Step 5: Check for unknown keys (log warning but don't reject)
    unknown_keys = set(data.keys()) - ALLOWED_TOP_LEVEL_KEYS
    if unknown_keys:
        logger.info(f"[PARSER] Ignoring unknown keys: {unknown_keys}")
    
    # Step 6: Validate proposal_type
    proposal_type = data.get("proposal_type")
    if proposal_type not in ALLOWED_PROPOSAL_TYPES:
        return ParseResult(
            rejected=True,
            reason=f"invalid_proposal_type: {proposal_type}"
        )
    
    # Step 7: Handle NONE proposal
    if proposal_type == "NONE":
        rationale = data.get("rationale", "")
        if isinstance(rationale, str) and len(rationale) > MAX_RATIONALE_LENGTH:
            rationale = rationale[:MAX_RATIONALE_LENGTH]
        
        return ParseResult(
            proposal=IntentProposal(
                action=ActionType.IDLE,
                description=str(rationale) if rationale else "Gemini: no action needed",
                source="gemini",
                confidence=0.8,
                metadata={'gemini_rationale': str(rationale)[:200]}
            )
        )
    
    # Step 8: Handle CLEAN_TABLE proposal
    if proposal_type == "CLEAN_TABLE":
        return _parse_clean_table(data, valid_object_ids)
    
    # Should not reach here (caught by step 6)
    return ParseResult(rejected=True, reason="unknown_state")


def _parse_clean_table(
    data: dict,
    valid_object_ids: Optional[Set[int]]
) -> ParseResult:
    """Parse CLEAN_TABLE specific fields"""
    
    # Validate object_ids
    object_ids_raw = data.get("object_ids")
    
    if object_ids_raw is None:
        # No specific objects — that's okay, compiler will pick
        object_ids = None
    elif not isinstance(object_ids_raw, list):
        return ParseResult(
            rejected=True,
            reason=f"object_ids_not_list: type={type(object_ids_raw).__name__}"
        )
    else:
        # Validate each ID
        object_ids = []
        for item in object_ids_raw:
            if not isinstance(item, (int, float)):
                continue  # Skip non-numeric silently
            obj_id = int(item)
            
            # Filter against valid IDs if provided
            if valid_object_ids is not None and obj_id not in valid_object_ids:
                logger.info(f"[PARSER] Filtering out invalid object_id: {obj_id}")
                continue
            
            if obj_id not in object_ids:  # Deduplicate
                object_ids.append(obj_id)
        
        if len(object_ids) > MAX_OBJECT_IDS:
            object_ids = object_ids[:MAX_OBJECT_IDS]
        
        if not object_ids:
            object_ids = None  # All filtered out
    
    # Rationale
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = str(rationale)
    if len(rationale) > MAX_RATIONALE_LENGTH:
        rationale = rationale[:MAX_RATIONALE_LENGTH]
    
    return ParseResult(
        proposal=IntentProposal(
            action=ActionType.CLEAN_TABLE,
            description=f"Gemini: clean table" + (
                f" ({len(object_ids)} objects)" if object_ids else ""
            ),
            source="gemini",
            confidence=0.85,
            metadata={
                'gemini_rationale': rationale[:200],
                'gemini_object_ids': object_ids,
            },
            suggested_object_ids=object_ids,
        )
    )

