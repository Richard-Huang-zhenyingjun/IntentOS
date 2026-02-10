"""
Gemini response types — internal to the integration layer.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class GeminiRawResponse:
    """
    Captures everything about a Gemini API call for debugging.
    Stored in event logs (truncated).
    """
    raw_text: str
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    truncated: bool = False
    
    def truncated_text(self, max_chars: int = 2000) -> str:
        """Return truncated raw text for logging"""
        if len(self.raw_text) <= max_chars:
            return self.raw_text
        return self.raw_text[:max_chars] + f"... [TRUNCATED, total={len(self.raw_text)}]"


