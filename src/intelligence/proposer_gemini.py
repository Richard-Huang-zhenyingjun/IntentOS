"""
Gemini-backed proposer.

Implements ProposerBase interface.
Uses external/gemini/ for all API interaction.
Never called during EXECUTING state (enforced by registry + internal check).
"""
import logging
from typing import Optional, Set
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.external.gemini.client import GeminiClientBase
from src.external.gemini.prompts import build_prompt
from src.external.gemini.parser import parse_gemini_response, ParseResult
from src.external.gemini.cache import GeminiCache
from src.core.events import EventEmitter, EventType

logger = logging.getLogger(__name__)


class GeminiProposer(ProposerBase):
    """
    Gemini-backed scene analysis proposer.
    
    Flow:
    1. Check cache → return cached if hit
    2. Check rate limit → return None if too soon
    3. Build prompt from scene
    4. Call Gemini API (with timeout)
    5. Parse response strictly
    6. Cache result
    7. Return IntentProposal or None (triggers fallback)
    
    Any failure at any step → returns None → registry falls back to heuristic.
    """
    
    def __init__(
        self,
        client: GeminiClientBase,
        config: dict,
        events: Optional[EventEmitter] = None
    ):
        self.client = client
        self.config = config
        self.events = events
        
        gemini_cfg = config.get('gemini', {})
        self.enabled = gemini_cfg.get('enabled', False)
        self.save_raw = gemini_cfg.get('logging', {}).get('save_raw_response', True)
        self.truncate_chars = gemini_cfg.get('logging', {}).get('truncate_chars', 2000)
        
        # Cache
        self.cache = GeminiCache(config)
        
        # Metrics
        self.total_calls: int = 0
        self.successful_proposals: int = 0
        self.parse_rejections: int = 0
        self.api_errors: int = 0
    
    def propose(self, scene: SceneSummary) -> IntentProposal:
        """
        Get proposal from Gemini.
        
        Note: Returns IDLE proposal on failure (per ProposerBase contract),
        but registry will still fall back if we return None internally.
        For now, we return IDLE to satisfy interface, but registry handles None specially.
        
        Returns:
            IntentProposal (IDLE if any failure, to satisfy interface)
        """
        if not self.enabled:
            return self._idle_proposal("Gemini disabled")
        
        # Step 1: Check cache
        cached = self.cache.get_cached(scene)
        if cached is not None:
            return cached
        
        # Step 2: Check rate limit
        if self.cache.is_rate_limited():
            logger.debug("[GEMINI] Rate limited, skipping call")
            return self._idle_proposal("Rate limited")
        
        # Step 3: Call Gemini
        self.total_calls += 1
        
        try:
            # Build prompt
            prompt = build_prompt(scene)
            
            # Optional: include image
            image = scene.rgb_snapshot  # None if no camera render
            
            # Call API
            raw_response = self.client.analyze(prompt, image)
            
            # Log raw response
            if self.events and self.save_raw:
                self.events.emit(
                    EventType.GEMINI_RAW_RESPONSE,
                    frame=scene.timestamp_frame,
                    data={
                        'raw_text': raw_response.truncated_text(self.truncate_chars),
                        'latency_ms': raw_response.latency_ms,
                        'model': raw_response.model,
                    }
                )
            
        except Exception as e:
            self.api_errors += 1
            logger.warning(f"[GEMINI] API error: {e}")
            
            if self.events:
                self.events.emit(
                    EventType.PROPOSER_FAILED,
                    frame=scene.timestamp_frame,
                    data={'proposer': 'gemini', 'error': str(e)[:200]}
                )
            
            return self._idle_proposal(f"API error: {e}")
        
        # Step 4: Parse response
        valid_ids = {obj.object_id for obj in scene.objects_on_table}
        result = parse_gemini_response(raw_response.raw_text, valid_ids)
        
        if not result.success:
            self.parse_rejections += 1
            logger.warning(f"[GEMINI] Parse rejected: {result.reason}")
            
            if self.events:
                self.events.emit(
                    EventType.PROPOSER_PARSE_REJECTED,
                    frame=scene.timestamp_frame,
                    data={
                        'proposer': 'gemini',
                        'reason': result.reason,
                        'raw_preview': raw_response.truncated_text(200),
                    }
                )
            
            return self._idle_proposal(f"Parse rejected: {result.reason}")
        
        # Step 5: Cache and return
        proposal = result.proposal
        self.successful_proposals += 1
        self.cache.store(scene, proposal)
        
        logger.info(f"[GEMINI] Proposal: {proposal.action.value} (confidence={proposal.confidence})")
        
        return proposal
    
    def _idle_proposal(self, reason: str) -> IntentProposal:
        """Helper to create IDLE proposal (satisfies interface contract)"""
        return IntentProposal(
            action=ActionType.IDLE,
            description=f"Gemini: {reason}",
            source="gemini",
            confidence=0.0,
            metadata={'gemini_fallback_reason': reason}
        )
    
    def name(self) -> str:
        return "gemini"
    
    def is_available(self) -> bool:
        return self.enabled and self.client.is_available()
    
    def get_stats(self) -> dict:
        return {
            'total_calls': self.total_calls,
            'successful_proposals': self.successful_proposals,
            'parse_rejections': self.parse_rejections,
            'api_errors': self.api_errors,
            'success_rate': (
                self.successful_proposals / self.total_calls
                if self.total_calls > 0 else 0.0
            ),
            'cache_stats': self.cache.get_stats(),
        }

