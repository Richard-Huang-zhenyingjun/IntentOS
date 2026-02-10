"""
Decision filter — input hygiene + quality gating.

This is the safety boundary for the decision pipeline.
It can only REDUCE confirms (block/downgrade), never CREATE them.

Pipeline position: Router → [Filter] → Orchestrator
"""
import logging
from typing import Optional
from src.input.types import (
    DecisionFrame, DecisionIntent, SourceType,
    FilterAction, RawSourceReading,
)

logger = logging.getLogger(__name__)


class DecisionFilter:
    """
    Filters raw decisions for safety and quality.
    
    Responsibilities:
    1. Debounce: prevent repeated confirms within N frames
    2. Hold-to-confirm: require N consecutive confirm frames (optional)
    3. Quality gate: block confirm if quality < threshold
    4. CANCEL always passes (never gated)
    
    INVARIANT: Filter can only REDUCE confirms, never CREATE them.
    If input intent is NONE, output intent is NONE. Always.
    """
    
    def __init__(self, config: dict):
        input_cfg = config.get('input', {})
        
        self.debounce_frames = input_cfg.get('debounce_frames', 6)
        self.hold_frames = input_cfg.get('confirm_hold_frames', 1)
        self.min_quality = input_cfg.get('min_quality', 0.65)
        
        # State
        self._frames_since_last_confirm: int = 999  # Start high (no recent confirm)
        self._consecutive_confirm_frames: int = 0
        self._last_raw_intent: DecisionIntent = DecisionIntent.NONE
        
        # Metrics
        self.total_received: int = 0
        self.confirms_passed: int = 0
        self.confirms_blocked_quality: int = 0
        self.confirms_blocked_debounce: int = 0
        self.confirms_blocked_hold: int = 0
        self.cancels_passed: int = 0
    
    def filter(
        self,
        intent: DecisionIntent,
        source_type: SourceType,
        quality: float,
        frame_number: int,
        raw_intents: dict = None,
        metadata: dict = None,
    ) -> DecisionFrame:
        """
        Apply all filter stages to a routed decision.
        
        Args:
            intent: Routed intent (from DecisionRouter)
            source_type: Which source provided the intent
            quality: Signal quality (0.0-1.0)
            frame_number: Current global frame
            raw_intents: Debug info from router
            metadata: Additional debug info
            
        Returns:
            DecisionFrame with potentially downgraded intent
        """
        self.total_received += 1
        self._frames_since_last_confirm += 1
        
        # CANCEL always passes (safety)
        if intent == DecisionIntent.CANCEL:
            self.cancels_passed += 1
            self._consecutive_confirm_frames = 0
            return DecisionFrame(
                intent=DecisionIntent.CANCEL,
                source_type=source_type,
                quality=quality,
                frame_number=frame_number,
                raw_intents=raw_intents or {},
                filter_action=FilterAction.PASSED,
                metadata=metadata or {},
            )
        
        # NONE passes through (no action to filter)
        if intent == DecisionIntent.NONE:
            self._consecutive_confirm_frames = 0
            return DecisionFrame(
                intent=DecisionIntent.NONE,
                source_type=source_type,
                quality=quality,
                frame_number=frame_number,
                raw_intents=raw_intents or {},
                filter_action=FilterAction.PASSED,
                metadata=metadata or {},
            )
        
        # CONFIRM — apply filter stages
        assert intent == DecisionIntent.CONFIRM
        
        # Stage 1: Quality gate
        if quality < self.min_quality:
            self.confirms_blocked_quality += 1
            self._consecutive_confirm_frames = 0
            logger.debug(
                f"[FILTER] Blocked confirm: quality={quality:.2f} < {self.min_quality}"
            )
            return DecisionFrame(
                intent=DecisionIntent.NONE,  # Downgrade
                source_type=source_type,
                quality=quality,
                frame_number=frame_number,
                raw_intents=raw_intents or {},
                filter_action=FilterAction.BLOCKED_QUALITY,
                filter_reason=f"quality={quality:.2f} < threshold={self.min_quality}",
                metadata=metadata or {},
            )
        
        # Stage 2: Debounce
        if self._frames_since_last_confirm < self.debounce_frames:
            self.confirms_blocked_debounce += 1
            logger.debug(
                f"[FILTER] Blocked confirm: debounce "
                f"({self._frames_since_last_confirm} < {self.debounce_frames} frames)"
            )
            return DecisionFrame(
                intent=DecisionIntent.NONE,
                source_type=source_type,
                quality=quality,
                frame_number=frame_number,
                raw_intents=raw_intents or {},
                filter_action=FilterAction.BLOCKED_DEBOUNCE,
                filter_reason=f"debounce: {self._frames_since_last_confirm}/{self.debounce_frames} frames",
                metadata=metadata or {},
            )
        
        # Stage 3: Hold-to-confirm
        self._consecutive_confirm_frames += 1
        if self._consecutive_confirm_frames < self.hold_frames:
            self.confirms_blocked_hold += 1
            logger.debug(
                f"[FILTER] Blocked confirm: hold "
                f"({self._consecutive_confirm_frames}/{self.hold_frames} frames)"
            )
            return DecisionFrame(
                intent=DecisionIntent.NONE,
                source_type=source_type,
                quality=quality,
                frame_number=frame_number,
                raw_intents=raw_intents or {},
                filter_action=FilterAction.BLOCKED_HOLD,
                filter_reason=f"hold: {self._consecutive_confirm_frames}/{self.hold_frames}",
                metadata=metadata or {},
            )
        
        # All stages passed — confirm is valid
        self.confirms_passed += 1
        self._frames_since_last_confirm = 0
        self._consecutive_confirm_frames = 0
        
        logger.debug(f"[FILTER] Confirm PASSED (quality={quality:.2f}, source={source_type.value})")
        
        return DecisionFrame(
            intent=DecisionIntent.CONFIRM,
            source_type=source_type,
            quality=quality,
            frame_number=frame_number,
            raw_intents=raw_intents or {},
            filter_action=FilterAction.PASSED,
            metadata=metadata or {},
        )
    
    def get_stats(self) -> dict:
        return {
            'total_received': self.total_received,
            'confirms_passed': self.confirms_passed,
            'confirms_blocked_quality': self.confirms_blocked_quality,
            'confirms_blocked_debounce': self.confirms_blocked_debounce,
            'confirms_blocked_hold': self.confirms_blocked_hold,
            'cancels_passed': self.cancels_passed,
        }


