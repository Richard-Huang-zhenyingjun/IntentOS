"""
Decision router — combines multiple sources according to policy.

Reads from all enabled sources, applies routing policy,
then passes result to the filter.
"""
import time
import logging
from typing import Dict, List, Optional
from src.input.source_base import DecisionSourceBase
from src.input.types import (
    RawSourceReading, DecisionIntent, SourceType,
)
from src.input.policies import DecisionPolicy, RoutingMode

logger = logging.getLogger(__name__)


class DecisionRouter:
    """
    Routes decisions from multiple sources according to policy.
    
    Rules:
    - CANCEL from any allowed source always takes priority
    - CONFIRM routing depends on mode (KEYBOARD_ONLY, ANY, DUAL, etc.)
    - NONE if no source signals anything
    
    INVARIANT: Router never creates CONFIRM if no source confirmed.
    """
    
    def __init__(self, policy: DecisionPolicy):
        self.policy = policy
        self._sources: Dict[str, DecisionSourceBase] = {}
        
        # DUAL mode state
        self._dual_confirm_times: Dict[str, float] = {}  # source_name → timestamp
        
        # Metrics
        self.total_reads: int = 0
        self.confirms_routed: int = 0
        self.cancels_routed: int = 0
    
    def register_source(self, name: str, source: DecisionSourceBase):
        """Register a decision source"""
        self._sources[name] = source
        logger.info(f"[ROUTER] Registered source '{name}' (type={source.source_type().value})")
    
    def get_source(self, name: str) -> Optional[DecisionSourceBase]:
        """Get a registered source by name, or None if missing."""
        return self._sources.get(name)
    
    def read_all(self) -> tuple:
        """
        Read from all sources and apply routing policy.
        
        Returns:
            (intent, source_type, quality, raw_intents_debug)
        """
        self.total_reads += 1
        
        # Step 1: Read all enabled sources
        readings: Dict[str, RawSourceReading] = {}
        for name, source in self._sources.items():
            if name not in self.policy.allowed_sources:
                continue
            if not source.is_available():
                continue
            readings[name] = source.read_raw()
        
        # Build debug dict
        raw_intents = {
            name: reading.intent.value
            for name, reading in readings.items()
        }
        
        # Step 2: Check for CANCEL (always takes priority)
        for name, reading in readings.items():
            if reading.intent == DecisionIntent.CANCEL:
                self.cancels_routed += 1
                return (
                    DecisionIntent.CANCEL,
                    reading.source_type,
                    reading.quality,
                    raw_intents,
                )
        
        # Step 3: Route CONFIRM based on policy mode
        if self.policy.mode == RoutingMode.KEYBOARD_ONLY:
            return self._route_single_source(readings, 'keyboard', raw_intents)
        
        elif self.policy.mode == RoutingMode.EEG_ONLY:
            # Accept any EEG-type source
            for name, reading in readings.items():
                if reading.source_type in [SourceType.EEG, SourceType.MOCK_EEG]:
                    if reading.intent == DecisionIntent.CONFIRM:
                        self.confirms_routed += 1
                        return (
                            DecisionIntent.CONFIRM,
                            reading.source_type,
                            reading.quality,
                            raw_intents,
                        )
            return (DecisionIntent.NONE, SourceType.UNKNOWN, 0.0, raw_intents)
        
        elif self.policy.mode == RoutingMode.ANY:
            return self._route_any(readings, raw_intents)
        
        elif self.policy.mode == RoutingMode.DUAL:
            return self._route_dual(readings, raw_intents)
        
        return (DecisionIntent.NONE, SourceType.UNKNOWN, 0.0, raw_intents)
    
    def _route_single_source(
        self,
        readings: Dict[str, RawSourceReading],
        source_name: str,
        raw_intents: dict,
    ) -> tuple:
        """Route from a single named source"""
        reading = readings.get(source_name)
        if reading and reading.intent == DecisionIntent.CONFIRM:
            self.confirms_routed += 1
            return (
                DecisionIntent.CONFIRM,
                reading.source_type,
                reading.quality,
                raw_intents,
            )
        return (DecisionIntent.NONE, SourceType.KEYBOARD, 1.0, raw_intents)
    
    def _route_any(
        self,
        readings: Dict[str, RawSourceReading],
        raw_intents: dict,
    ) -> tuple:
        """Confirm if any source confirms (highest quality wins)"""
        best_confirm = None
        
        for name, reading in readings.items():
            if reading.intent == DecisionIntent.CONFIRM:
                if best_confirm is None or reading.quality > best_confirm.quality:
                    best_confirm = reading
        
        if best_confirm is not None:
            self.confirms_routed += 1
            return (
                DecisionIntent.CONFIRM,
                best_confirm.source_type,
                best_confirm.quality,
                raw_intents,
            )
        
        return (DecisionIntent.NONE, SourceType.COMBINED, 0.0, raw_intents)
    
    def _route_dual(
        self,
        readings: Dict[str, RawSourceReading],
        raw_intents: dict,
    ) -> tuple:
        """
        DUAL mode: both specified sources must confirm within time window.
        
        Algorithm:
        - When a source confirms, record its timestamp
        - If both sources have confirmed within window_ms, emit CONFIRM
        - Quality is the minimum of both sources
        """
        now = time.time()
        window_sec = self.policy.dual_window_ms / 1000.0
        
        # Record new confirms
        for name, reading in readings.items():
            if name in self.policy.dual_sources and reading.intent == DecisionIntent.CONFIRM:
                self._dual_confirm_times[name] = now
        
        # Check if both sources confirmed within window
        required_sources = set(self.policy.dual_sources)
        confirmed_in_window = set()
        min_quality = 1.0
        
        for source_name in required_sources:
            confirm_time = self._dual_confirm_times.get(source_name)
            if confirm_time is not None and (now - confirm_time) <= window_sec:
                confirmed_in_window.add(source_name)
                # Get quality from reading if available
                reading = readings.get(source_name)
                if reading:
                    min_quality = min(min_quality, reading.quality)
        
        if confirmed_in_window == required_sources:
            # Both confirmed within window — emit CONFIRM
            self.confirms_routed += 1
            # Reset timestamps to prevent repeated dual-confirms
            self._dual_confirm_times.clear()
            
            return (
                DecisionIntent.CONFIRM,
                SourceType.COMBINED,
                min_quality,
                raw_intents,
            )
        
        return (DecisionIntent.NONE, SourceType.COMBINED, 0.0, raw_intents)
    
    def get_stats(self) -> dict:
        return {
            'total_reads': self.total_reads,
            'confirms_routed': self.confirms_routed,
            'cancels_routed': self.cancels_routed,
            'registered_sources': list(self._sources.keys()),
            'mode': self.policy.mode.value,
        }

