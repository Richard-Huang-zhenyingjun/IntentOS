"""
Safe PyBullet API wrappers - the ONLY way to interact with PyBullet bodies.

Core principle: No untrusted body ID reaches PyBullet.
All body-related PyBullet calls MUST go through these wrappers.
"""

import pybullet as p
from typing import Optional, Tuple, List
import traceback
from collections import defaultdict
import time


class SafePyBullet:
    """
    Safe wrapper around PyBullet body operations.
    Validates body IDs, caches results, logs violations.
    """
    
    def __init__(self, physics_client_id: int = 0):
        self.client_id = physics_client_id
        
        # Logging: rate-limited to prevent spam
        self._last_log_time = defaultdict(float)
        self._log_cooldown = 1.0  # seconds between logs for same ID
        
        # Statistics (for debugging)
        self.stats = {
            'valid_calls': 0,
            'invalid_calls': 0,
            'last_invalid_id': None,
            'last_invalid_trace': None
        }
    
    def _should_log(self, body_id: int) -> bool:
        """Rate-limit logging to avoid spam."""
        now = time.time()
        key = f"invalid_{body_id}"
        if now - self._last_log_time[key] > self._log_cooldown:
            self._last_log_time[key] = now
            return True
        return False
    
    def is_valid_body(self, body_id: Optional[int]) -> bool:
        """
        Check if body ID is valid without crashing.
        
        This is the fundamental validation primitive.
        Returns False for None or invalid IDs.
        """
        if body_id is None:
            return False
        
        try:
            # Use getBodyInfo as validation - it's lightweight
            p.getBodyInfo(body_id, physicsClientId=self.client_id)
            return True
        except:
            return False
    
    def safe_get_body_pose(self, body_id: Optional[int]) -> Optional[Tuple[List[float], List[float]]]:
        """
        Get body pose safely - returns None if invalid.
        
        This is the PRIMARY way to get pose in the codebase.
        Returns: (position, orientation) tuple or None
        
        CRITICAL: This validates AND fetches in ONE call.
        Eliminates TOCTOU window.
        """
        if body_id is None:
            return None
        
        try:
            pos, orn = p.getBasePositionAndOrientation(body_id, physicsClientId=self.client_id)
            self.stats['valid_calls'] += 1
            return (pos, orn)
            
        except Exception as e:
            # Invalid body ID - log and return None
            self.stats['invalid_calls'] += 1
            self.stats['last_invalid_id'] = body_id
            
            # STEP C: Notify callbacks for deferred self-healing
            self._notify_stale_body(body_id)
            
            if self._should_log(body_id):
                print(f"[SAFE_PB] ⚠️ Invalid body ID {body_id}")
                print(f"[SAFE_PB]    Error: {e}")
                
                # Capture stack trace for debugging
                trace = ''.join(traceback.format_stack()[:-1])  # Exclude this frame
                self.stats['last_invalid_trace'] = trace
                
                # Print abbreviated stack (last 5 frames)
                frames = traceback.format_stack()[:-1]
                print(f"[SAFE_PB]    Call stack (last 5 frames):")
                for frame in frames[-5:]:
                    print(f"[SAFE_PB]      {frame.strip()}")
            
            return None
    
    def safe_add_debug_text(
        self,
        text: str,
        position: Tuple[float, float, float],
        color: Tuple[float, float, float] = (1, 1, 1),
        size: float = 1.0,
        lifetime: float = 0,
        parent_body_id: Optional[int] = None,
        replace_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Add debug text safely - handles invalid parent body IDs.
        
        If parent_body_id is invalid, degrades to world-space text (no parenting).
        This prevents crashes from stale parent IDs.
        """
        # Validate parent body if provided
        if parent_body_id is not None and not self.is_valid_body(parent_body_id):
            if self._should_log(parent_body_id):
                print(f"[SAFE_PB] ⚠️ Invalid parent body ID {parent_body_id} for debug text - using world space")
            parent_body_id = None  # Degrade to world-space text
        
        try:
            result = p.addUserDebugText(
                text=text,
                textPosition=position,
                textColorRGB=color,
                textSize=size,
                lifeTime=lifetime,
                parentObjectUniqueId=parent_body_id if parent_body_id is not None else -1,
                replaceItemUniqueId=replace_id if replace_id is not None else -1,
                physicsClientId=self.client_id
            )
            return result
        except Exception as e:
            print(f"[SAFE_PB] ⚠️ Failed to add debug text: {e}")
            return None
    
    def get_stats(self) -> dict:
        """Return statistics for debugging."""
        return self.stats.copy()
    
    def print_stats(self):
        """Print statistics summary."""
        print(f"[SAFE_PB] Statistics:")
        print(f"  Valid calls:   {self.stats['valid_calls']}")
        print(f"  Invalid calls: {self.stats['invalid_calls']}")
        if self.stats['last_invalid_id'] is not None:
            print(f"  Last invalid ID: {self.stats['last_invalid_id']}")
    
    def register_stale_body_callback(self, callback):
        """
        STEP C: Register callback for deferred self-healing.
        
        When an invalid body ID is detected, the callback will be invoked
        with the body_id. This allows subsystems to clean up stale state.
        
        Args:
            callback: Function(body_id: int) -> None
        """
        if not hasattr(self, '_stale_callbacks'):
            self._stale_callbacks = []
        self._stale_callbacks.append(callback)
    
    def _notify_stale_body(self, body_id: int):
        """Notify registered callbacks about stale body ID."""
        if hasattr(self, '_stale_callbacks'):
            for callback in self._stale_callbacks:
                try:
                    callback(body_id)
                except Exception as e:
                    print(f"[SAFE_PB] ⚠️ Stale body callback failed: {e}")


# Global instance (initialized by simulator)
_safe_pb: Optional[SafePyBullet] = None


def init_safe_pybullet(physics_client_id: int = 0):
    """Initialize global safe PyBullet instance."""
    global _safe_pb
    _safe_pb = SafePyBullet(physics_client_id)


def get_safe_pb() -> SafePyBullet:
    """Get global safe PyBullet instance."""
    if _safe_pb is None:
        raise RuntimeError("SafePyBullet not initialized - call init_safe_pybullet() first")
    return _safe_pb


# Convenience functions (use these throughout codebase)

def is_valid_body(body_id: Optional[int]) -> bool:
    """Check if body ID is valid."""
    return get_safe_pb().is_valid_body(body_id)


def safe_get_pose(body_id: Optional[int]) -> Optional[Tuple[List[float], List[float]]]:
    """Get body pose safely - returns None if invalid."""
    return get_safe_pb().safe_get_body_pose(body_id)


def safe_debug_text(
    text: str,
    position: Tuple[float, float, float],
    color: Tuple[float, float, float] = (1, 1, 1),
    size: float = 1.0,
    lifetime: float = 0,
    parent_body_id: Optional[int] = None,
    replace_id: Optional[int] = None
) -> Optional[int]:
    """Add debug text safely."""
    return get_safe_pb().safe_add_debug_text(
        text, position, color, size, lifetime, parent_body_id, replace_id
    )

