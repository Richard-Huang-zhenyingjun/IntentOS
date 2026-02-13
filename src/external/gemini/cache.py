"""
Scene-based caching and rate limiting for Gemini calls.

Prevents:
- Calling Gemini 60x/second (once per frame)
- Re-calling when scene hasn't changed
- Cost explosion during development/testing
"""
import hashlib
import json
import time
import logging
from typing import Optional
from src.interfaces.scene_summary import SceneSummary
from src.interfaces.intent_proposal import IntentProposal

logger = logging.getLogger(__name__)


class GeminiCache:
    """
    Cache Gemini proposals based on scene hash.
    Also enforces minimum interval between API calls.
    """
    
    def __init__(self, config: dict):
        cache_cfg = config.get('gemini', {}).get('cache', {})
        
        self.min_interval_sec = cache_cfg.get('min_interval_sec', 2.0)
        self.max_entries = cache_cfg.get('max_entries', 50)
        
        # State
        self._cache: dict = {}  # scene_hash → IntentProposal
        self._last_call_time: float = 0.0
        
        # Metrics
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.rate_limit_blocks: int = 0
    
    def get_cached(self, scene: SceneSummary) -> Optional[IntentProposal]:
        """
        Check if we have a cached proposal for this scene.
        
        Returns:
            Cached IntentProposal if hit, None if miss
        """
        scene_hash = self._compute_scene_hash(scene)
        
        if scene_hash in self._cache:
            self.cache_hits += 1
            logger.debug(f"[CACHE] Hit for hash {scene_hash[:8]}")
            return self._cache[scene_hash]
        
        self.cache_misses += 1
        return None
    
    def is_rate_limited(self) -> bool:
        """Check if we should wait before calling Gemini again"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self.min_interval_sec:
            self.rate_limit_blocks += 1
            return True
        return False
    
    def store(self, scene: SceneSummary, proposal: IntentProposal):
        """Store proposal in cache"""
        scene_hash = self._compute_scene_hash(scene)
        
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_entries:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[scene_hash] = proposal
        self._last_call_time = time.time()
    
    def invalidate(self):
        """Clear cache (e.g., after execution changes the scene)"""
        self._cache.clear()
        logger.debug("[CACHE] Invalidated")
    
    def _compute_scene_hash(self, scene: SceneSummary) -> str:
        """
        Hash scene state for cache key.
        
        Includes: object count, object positions (rounded), clutter score bucket.
        Excludes: timestamp, rgb_snapshot (too expensive to hash).
        """
        key_parts = {
            'n_objects': len(scene.objects_on_table),
            'clutter_bucket': round(scene.clutter_score, 1),  # 0.1 buckets
            'object_ids': sorted(obj.object_id for obj in scene.objects_on_table),
            'positions': [
                (round(obj.pos_xyz[0], 2), round(obj.pos_xyz[1], 2))
                for obj in sorted(scene.objects_on_table, key=lambda o: o.object_id)
            ],
        }
        
        key_str = json.dumps(key_parts, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get_stats(self) -> dict:
        return {
            'cache_size': len(self._cache),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': (
                self.cache_hits / (self.cache_hits + self.cache_misses)
                if (self.cache_hits + self.cache_misses) > 0 else 0.0
            ),
            'rate_limit_blocks': self.rate_limit_blocks,
        }



