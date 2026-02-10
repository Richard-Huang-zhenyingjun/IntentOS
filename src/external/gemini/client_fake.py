"""
Fake Gemini client for deterministic testing.
Allows precise control over responses, failures, and timing.
"""
import time
from typing import Optional, List
import numpy as np
from src.external.gemini.client import GeminiClientBase
from src.external.gemini.types import GeminiRawResponse


class FakeGeminiClient(GeminiClientBase):
    """
    Test-only Gemini client with full scenario control.
    
    Usage:
        fake = FakeGeminiClient()
        fake.set_response('{"proposal_type": "CLEAN_TABLE", "object_ids": [5]}')
        
        # Simulate failures:
        fake.set_exception(TimeoutError("Simulated timeout"))
        fake.set_latency(5.0)  # Slow response
    """
    
    def __init__(self):
        self._available = True
        self._response_text: str = '{"proposal_type": "NONE"}'
        self._exception: Optional[Exception] = None
        self._persistent_exception: bool = False
        self._latency_sec: float = 0.01
        
        # Tracking
        self._call_count: int = 0
        self._call_log: List[dict] = []
        self._last_scene_text: Optional[str] = None
        self._last_image: Optional[np.ndarray] = None
    
    def analyze(
        self,
        scene_text: str,
        image: Optional[np.ndarray] = None
    ) -> GeminiRawResponse:
        """Return configured response or raise configured exception"""
        self._call_count += 1
        self._last_scene_text = scene_text
        self._last_image = image
        
        self._call_log.append({
            'call_num': self._call_count,
            'scene_text_len': len(scene_text),
            'has_image': image is not None,
            'timestamp': time.time(),
        })
        
        # Simulate latency
        if self._latency_sec > 0:
            time.sleep(self._latency_sec)
        
        # Simulate failure
        if self._exception is not None:
            exc = self._exception
            if not self._persistent_exception:
                self._exception = None  # One-shot by default
            raise exc
        
        return GeminiRawResponse(
            raw_text=self._response_text,
            model="fake-gemini",
            latency_ms=self._latency_sec * 1000,
        )
    
    def is_available(self) -> bool:
        return self._available
    
    # === Test Control Methods ===
    
    def set_response(self, raw_json: str):
        """Set the raw text response for next call(s)"""
        self._response_text = raw_json
    
    def set_exception(self, exc: Exception, persistent: bool = False):
        """
        Set exception to raise on next call.
        If persistent=False, only raises once then resets.
        """
        self._exception = exc
        self._persistent_exception = persistent
    
    def set_available(self, available: bool):
        self._available = available
    
    def set_latency(self, seconds: float):
        self._latency_sec = seconds
    
    # === Test Inspection Methods ===
    
    def get_call_count(self) -> int:
        return self._call_count
    
    def get_last_scene_text(self) -> Optional[str]:
        return self._last_scene_text
    
    def get_last_image(self) -> Optional[np.ndarray]:
        return self._last_image
    
    def get_call_log(self) -> List[dict]:
        return self._call_log
    
    def reset(self):
        """Reset all state"""
        self._call_count = 0
        self._call_log = []
        self._exception = None
        self._persistent_exception = False
        self._response_text = '{"proposal_type": "NONE"}'
        self._latency_sec = 0.01
        self._available = True


